
# routers/auth_router.py

from typing import Optional
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse
from firebase_admin import auth
from google.cloud.firestore_v1.base_query import FieldFilter
from pydantic import BaseModel, EmailStr

from app.utils.firebase import firestore_run
from app.services.email_service import (
    send_verification_email,
    send_reset_password_email,
)
from app.tasks.user_verify import delete_unverified_user
from app.models.user_model import User
from app.models.auth_model import LoginRequest, ProfileUpdate
from app.core.firebase import db
from app.core.auth import get_current_user
from app.core.notifications import create_notification
from app.core.config import settings
from app.utils.security import generate_otp

logger = logging.getLogger("payla.auth")

router = APIRouter(prefix="/auth", tags=["Auth"])


class CheckEmailRequest(BaseModel):
    email: EmailStr


class SignupRequest(BaseModel):
    email: str
    password: str
    full_name: str


class AuthResponse(BaseModel):
    user: User
    requires_verification: Optional[bool] = False
    message: Optional[str] = None


class ResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str
    confirm_password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordCodeRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str


class VerifyCodeRequest(BaseModel):
    email: EmailStr
    code: str


@router.post("/check-email")
async def check_email(data: CheckEmailRequest):
    email = str(data.email).lower().strip()

    user_docs = await firestore_run(
        db.collection("users")
        .where("email", "==", email)
        .get
    )

    exists = len(user_docs) > 0

    waitlist_doc = await firestore_run(
        db.collection("waitlist").document(email).get
    )

    return {
        "exists": exists,
        "waitlist": waitlist_doc.exists,
    }


@router.post("/signup-email")
async def signup_email(data: SignupRequest):
    email = data.email.lower().strip()
    password = data.password
    full_name = data.full_name

    logger.info("Signup attempt started for email: %s", email)

    try:
        now = datetime.now(timezone.utc)

        # Step 1: Create Firebase Authentication user.
        logger.info("Creating Firebase Auth user for %s", email)

        fb_user = auth.create_user(
            email=email,
            password=password,
            display_name=full_name,
        )

        logger.info("Firebase Auth user created: %s", fb_user.uid)

        # Step 2: Create email verification token.
        verify_token = str(uuid.uuid4())

        # Step 3: Create the user's permanent Free-tier account.
        new_user = User(
            _id=fb_user.uid,
            firebase_uid=fb_user.uid,
            full_name=full_name,
            email=email,
            email_verified=False,
            verify_token=verify_token,
            plan="free",
            subscription_status="inactive",
            plan_start_date=None,
            trial_end_date=None,
            subscription_end=None,
            next_billing_date=None,
            created_at=now,
            updated_at=now,
        )

        await firestore_run(
            db.collection("users").document(fb_user.uid).set,
            new_user.dict(by_alias=True),
        )

        logger.info("Firestore user document created for %s", email)

        # Step 4: Send verification email.
        send_verification_email(email, verify_token)

        logger.info("Verification email sent to %s", email)

        return {
            "message": "Verification email sent. Please check your inbox."
        }

    except auth.EmailAlreadyExistsError:
        logger.warning("Signup failed: email already in use - %s", email)
        raise HTTPException(
            status_code=400,
            detail="Email already in use",
        )

    except Exception as e:
        logger.exception("Signup failed for %s", email)

        raise HTTPException(
            status_code=400,
            detail=f"Signup failed: {str(e)}",
        )


@router.post("/login-email", response_model=AuthResponse)
async def login(payload: LoginRequest):
    try:
        decoded = auth.verify_id_token(payload.id_token)

        logger.info(
            "Token verified successfully | UID: %s",
            decoded["uid"],
        )

    except auth.InvalidIdTokenError as e:
        logger.error("Invalid Firebase token: %s", e)
        raise HTTPException(
            status_code=401,
            detail="Invalid Firebase token",
        )

    except auth.ExpiredIdTokenError as e:
        logger.error("Expired Firebase token: %s", e)
        raise HTTPException(
            status_code=401,
            detail="Token expired",
        )

    except auth.RevokedIdTokenError as e:
        logger.error("Revoked Firebase token: %s", e)
        raise HTTPException(
            status_code=401,
            detail="Token revoked",
        )

    except auth.CertificateFetchError as e:
        logger.error("Failed to fetch Firebase certificates: %s", e)
        raise HTTPException(
            status_code=401,
            detail="Certificate fetch failed",
        )

    except Exception as e:
        logger.error(
            "Unexpected error verifying token: %s: %s",
            type(e).__name__,
            e,
        )
        raise HTTPException(
            status_code=401,
            detail="Token verification failed",
        )

    uid = decoded["uid"]

    user_doc = await firestore_run(
        db.collection("users").document(uid).get
    )

    if not user_doc.exists:
        raise HTTPException(
            status_code=401,
            detail="User not found. Please signup first.",
        )

    user = User(**user_doc.to_dict())

    if not user.email_verified:
        return AuthResponse(
            user=user,
            requires_verification=True,
            message="Email not verified. Please check your inbox.",
        )

    create_notification(
        user_id=user.id,
        title="Welcome Back!",
        message=(
            f"Hello {user.full_name or user.email}, "
            "you've successfully logged in."
        ),
        type="success",
        link="/dashboard",
    )

    return AuthResponse(user=user)


@router.get("/verify-email")
async def verify_email(token: str):
    """Verify the user's email and redirect to the next step."""

    users = await firestore_run(
        db.collection("users")
        .where("verify_token", "==", token)
        .stream
    )

    matched_user = None

    for user_snapshot in users:
        matched_user = user_snapshot
        break

    if not matched_user:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired token",
        )

    user_data = matched_user.to_dict()

    await firestore_run(
        db.collection("users").document(matched_user.id).update,
        {
            "email_verified": True,
            "verify_token": None,
            "updated_at": datetime.now(timezone.utc),
        },
    )

    onboarding_done = user_data.get("onboarding_complete", False)

    frontend_url = str(
        getattr(settings, "FRONTEND_URL", None) or "https://payla.ng"
    ).rstrip("/")

    if onboarding_done:
        redirect_url = f"{frontend_url}/dashboard"
    else:
        redirect_url = f"{frontend_url}/onboarding"

    return RedirectResponse(url=redirect_url)


@router.get("/confirm-email")
async def confirm_email(
    oobCode: str = Query(..., alias="oobCode"),
):
    """
    Verify Firebase's email action code and create the Firestore user
    record if it does not already exist.
    """

    try:
        email = auth.verify_oob_code(oobCode, "VERIFY_EMAIL")
        fb_user = auth.get_user_by_email(email)

        existing = await firestore_run(
            db.collection("users").document(fb_user.uid).get
        )

        if existing.exists:
            return JSONResponse(
                {
                    "message": "Already verified",
                    "redirect": "onboarding",
                }
            )

        now = datetime.now(timezone.utc)

        user = User(
            _id=fb_user.uid,
            firebase_uid=fb_user.uid,
            full_name=fb_user.display_name or email.split("@")[0],
            email=email.lower().strip(),
            email_verified=True,
            plan="free",
            subscription_status="inactive",
            plan_start_date=None,
            trial_end_date=None,
            subscription_end=None,
            next_billing_date=None,
            created_at=now,
            updated_at=now,
        )

        await firestore_run(
            db.collection("users").document(fb_user.uid).set,
            user.dict(by_alias=True),
        )

        return JSONResponse(
            {
                "message": "Email verified successfully",
                "redirect": "/onboarding",
            }
        )

    except Exception as e:
        logger.error("Email verification failed: %s", e)

        raise HTTPException(
            status_code=400,
            detail="Invalid or expired verification link.",
        )


@router.post("/resend-verification")
async def resend_verification(data: CheckEmailRequest):
    email = str(data.email).lower().strip()

    user_docs = await firestore_run(
        db.collection("users")
        .where("email", "==", email)
        .get
    )

    if not user_docs:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    user = User(**user_docs[0].to_dict())

    if user.email_verified:
        return {"message": "Email already verified"}

    verify_token = str(uuid.uuid4())

    await firestore_run(
        db.collection("users").document(user.id).update,
        {
            "verify_token": verify_token,
            "updated_at": datetime.now(timezone.utc),
        },
    )

    send_verification_email(email, verify_token)

    logger.info("Resent verification email to %s", email)

    return {"message": "Verification email resent"}


@router.get("/check-email-verified")
async def check_email_verified(email: EmailStr = Query(...)):
    """Return email verification and onboarding status."""

    email = str(email).lower().strip()

    user_docs = await firestore_run(
        db.collection("users")
        .where("email", "==", email)
        .get
    )

    if not user_docs:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    user = User(**user_docs[0].to_dict())

    return {
        "verified": user.email_verified,
        "onboarding_complete": getattr(
            user,
            "onboarding_complete",
            False,
        ),
    }


@router.get("/me", response_model=User)
async def get_me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=User)
async def update_profile(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user),
):
    update_data = payload.dict(exclude_unset=True)

    if not update_data:
        raise HTTPException(
            status_code=400,
            detail="No fields to update",
        )

    # Username validation.
    if "username" in update_data:
        username = update_data["username"].lower().strip()

        if not username.replace("-", "").replace("_", "").isalnum():
            raise HTTPException(
                status_code=400,
                detail="Username: letters, numbers, -, _ only",
            )

        if len(username) < 3:
            raise HTTPException(
                status_code=400,
                detail="Username too short",
            )

        existing_username = await firestore_run(
            db.collection("paylinks")
            .where("username", "==", username)
            .get
        )

        if existing_username:
            raise HTTPException(
                status_code=400,
                detail="Username taken",
            )

        update_data["username"] = username

    update_data["updated_at"] = datetime.now(timezone.utc)

    await firestore_run(
        db.collection("users").document(user.id).update,
        update_data,
    )

    create_notification(
        user_id=user.id,
        title="Profile Updated",
        message="Your profile details have been successfully updated.",
        type="info",
        link="/dashboard/profile",
    )

    updated = await firestore_run(
        db.collection("users").document(user.id).get
    )

    return User(**updated.to_dict())


@router.post("/forgot-password")
async def forgot_password(data: ForgotPasswordRequest):
    email = str(data.email).lower().strip()

    user_docs = await firestore_run(
        db.collection("users")
        .where("email", "==", email)
        .get
    )

    if not user_docs:
        raise HTTPException(
            status_code=404,
            detail="No account found with this email",
        )

    user = User(**user_docs[0].to_dict())

    code = generate_otp()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    await firestore_run(
        db.collection("password_resets").document(user.id).set,
        {
            "user_id": user.id,
            "email": email,
            "code": code,
            "expires_at": expires_at,
            "used": False,
            "created_at": datetime.now(timezone.utc),
        },
    )

    send_reset_password_email(email, code)

    return {
        "message": "Verification code sent",
        "expires_in": 600,
    }


@router.post("/reset-password")
async def reset_password_with_code(req: ResetPasswordCodeRequest):
    email = str(req.email).lower().strip()

    docs = await firestore_run(
        db.collection("password_resets")
        .where("email", "==", email)
        .where("code", "==", req.code)
        .get
    )

    if not docs:
        raise HTTPException(
            status_code=400,
            detail="Invalid reset code",
        )

    data = docs[0].to_dict()

    if data.get("used", False):
        raise HTTPException(
            status_code=400,
            detail="Reset code has already been used",
        )

    expires_at = data["expires_at"]

    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(
            expires_at.replace("Z", "+00:00")
        )

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(
            status_code=400,
            detail="Code expired",
        )

    fb_user = auth.get_user_by_email(email)
    auth.update_user(fb_user.uid, password=req.new_password)

    await firestore_run(
        db.collection("password_resets").document(docs[0].id).update,
        {
            "used": True,
            "used_at": datetime.now(timezone.utc),
        },
    )

    return {"message": "Password reset successful"}


@router.post("/verify-reset-code")
async def verify_reset_code(req: VerifyCodeRequest):
    email = str(req.email).lower().strip()

    docs = await firestore_run(
        db.collection("password_resets")
        .where("email", "==", email)
        .where("code", "==", req.code)
        .get
    )

    if not docs:
        raise HTTPException(
            status_code=400,
            detail="Invalid code",
        )

    data = docs[0].to_dict()

    if data.get("used", False):
        raise HTTPException(
            status_code=400,
            detail="Code has already been used",
        )

    expires_at = data["expires_at"]

    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(
            expires_at.replace("Z", "+00:00")
        )

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(
            status_code=400,
            detail="Code expired",
        )

    return {
        "valid": True,
        "message": "Code verified",
    }


@router.post("/logout")
async def logout():
    """
    The frontend should also clear Firebase authentication and local state.
    """
    return {"message": "Logged out successfully"}
