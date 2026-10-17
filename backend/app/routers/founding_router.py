# routers/founding_router.py
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from firebase_admin import auth
from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.config import settings
from app.core.constants import FOUNDING_TRIAL_DAYS
from app.core.firebase import db
from app.core.notifications import create_notification
from app.models.founding_model import (
    FoundingSignupRequest,
    FoundingSignupResponse,
    ResendVerificationRequest,
    FoundingStatusResponse,
)
from app.core.constants import (
    INAPPROPRIATE_WORDS,
    RESERVED_USERNAMES,
    USERNAME_PATTERN,
)
from app.models.user_model import User
from app.services.email_service import send_founding_verification_email
from app.core.payla_urls import paylink_url as _paylink_url

logger = logging.getLogger("payla.founding")

router = APIRouter(prefix="/founding", tags=["Founding Members"])


# ===== HELPERS =====

async def check_username_available(username: str) -> bool:
    """Check username in both users and paylinks collections."""
    username = username.lower().strip()

    user_docs = (
        db.collection("users")
        .where(filter=FieldFilter("username", "==", username))
        .limit(1)
        .stream()
    )
    if list(user_docs):
        return False

    paylink_docs = (
        db.collection("paylinks")
        .where(filter=FieldFilter("username", "==", username))
        .limit(1)
        .stream()
    )
    return len(list(paylink_docs)) == 0


async def check_email_exists(email: str) -> tuple[bool, Optional[str]]:
    """Check Firebase Auth first, then Firestore users as a backup."""
    email = email.lower().strip()

    try:
        auth.get_user_by_email(email)
        return True, "Email already registered"
    except auth.UserNotFoundError:
        pass
    except Exception:
        # Do not fail signup because Firebase Auth lookup errored.
        # Fall through to the Firestore check.
        logger.exception("Firebase Auth email lookup failed")

    user_docs = (
        db.collection("users")
        .where(filter=FieldFilter("email", "==", email))
        .limit(1)
        .stream()
    )
    if list(user_docs):
        return True, "Email already registered"

    return False, None


# ===== ENDPOINTS =====

@router.post("/signup", response_model=FoundingSignupResponse)
async def founding_signup(request: FoundingSignupRequest):
    """
    Founding member signup with one year of free Silver access upon
    email verification.
    """
    email = request.email.lower().strip()
    username = request.username.lower().strip()

    logger.info(f"Founding signup attempt: {email} | @{username}")

    try:
        if not await check_username_available(username):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "username_taken",
                    "message": (
                        f"@{username} is already taken. "
                        f"Please try another."
                    ),
                },
            )

        email_exists, _ = await check_email_exists(email)
        if email_exists:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "email_exists",
                    "message": (
                        "This email is already registered. "
                        "Please log in instead."
                    ),
                },
            )

        fb_user = auth.create_user(
            email=email,
            password=request.password,
            display_name=username,
        )
        logger.info(f"Firebase user created: {fb_user.uid}")

        verify_token = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        new_user = User(
            _id=fb_user.uid,
            firebase_uid=fb_user.uid,
            full_name=username,
            email=email,
            username=username,
            email_verified=False,
            verify_token=verify_token,
            plan="free",
            trial_end_date=None,
            created_at=now,
            updated_at=now,
            onboarding_complete=False,
        )

        db.collection("users").document(fb_user.uid).set(
            new_user.dict(by_alias=True)
        )

        db.collection("paylinks").document(fb_user.uid).set({
            "user_id": fb_user.uid,
            "username": username,
            "display_name": username,
            "description": "Your Payment Identity.",
            "currency": "NGN",
            "active": False,
            "is_active": False,
            "link_url": paylink_url(username),
            "preferred_domain": "ng",
            "total_received": 0.0,
            "total_transactions": 0,
            "created_at": now,
            "updated_at": now,
        })

        logger.info(f"Firestore user created for {email} with @{username}")

        # Pass the username so the verification email shows the
        # user-chosen name, not the email prefix.
        send_founding_verification_email(
            email, verify_token, username=username
        )
        logger.info(f"Verification email sent to {email}")

        return FoundingSignupResponse(
            success=True,
            message=(
                "Verification email sent. Please check your inbox "
                "to activate your one year of complimentary Silver."
            ),
            requires_verification=True,
            email=email,
            username=username,
        )

    except HTTPException:
        raise

    except auth.EmailAlreadyExistsError:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "email_exists",
                "message": (
                    "This email is already registered. "
                    "Please log in instead."
                ),
            },
        )

    except Exception:
        logger.exception("Founding signup failed")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "server_error",
                "message": "Signup failed. Please try again later.",
            },
        )


@router.get("/verify-email")
async def verify_founding_email(token: str):
    """
    Verify the founding member's email and grant one year of Silver.
    Redirects to the frontend entry page in every case.
    """
    entry_url = f"{settings.FRONTEND_URL}entry"

    try:
        users = (
            db.collection("users")
            .where(filter=FieldFilter("verify_token", "==", token))
            .limit(1)
            .stream()
        )

        user_list = list(users)
        if not user_list:
            logger.warning(f"Invalid verification token: {token}")
            return RedirectResponse(url=entry_url, status_code=302)

        user_doc = user_list[0]
        user_data = user_doc.to_dict() or {}
        user_id = user_doc.id
        email = user_data.get("email")
        username = user_data.get("username")

        if not username:
            logger.warning(
                f"Verification token belongs to user without username: "
                f"{user_id}"
            )
            return RedirectResponse(url=entry_url, status_code=302)

        if user_data.get("email_verified"):
            return RedirectResponse(url=entry_url, status_code=302)

        now = datetime.now(timezone.utc)
        subscription_end = now + timedelta(days=FOUNDING_TRIAL_DAYS)

        db.collection("users").document(user_id).update({
            "email_verified": True,
            "verify_token": None,
            "plan": "silver",
            "plan_start_date": now,
            "subscription_end": subscription_end,
            "next_billing_date": subscription_end,
            "founding_member": True,
            "founding_claimed_at": now,
            "updated_at": now,
        })

        db.collection("paylinks").document(user_id).update({
            "active": True,
            "is_active": True,
            "verified_at": now,
            "updated_at": now,
        })

        logger.info(
            f"Founding member verified: {email} | "
            f"one year of Silver granted for @{username}"
        )

        create_notification(
            user_id=user_id,
            title="Welcome to Payla Silver",
            message=(
                f"Your email is verified and you now have one year of "
                f"complimentary Silver. Start using "
                f"{paylink_url(username)}"
            ),
            type="success",
            link="/onboarding",
        )

        return RedirectResponse(url=entry_url, status_code=302)

    except Exception:
        logger.exception("Verification failed")
        return RedirectResponse(url=entry_url, status_code=302)


@router.post("/resend-verification")
async def resend_founding_verification(request: ResendVerificationRequest):
    """Resend the founding member verification email."""
    email = request.email.lower().strip()

    try:
        users = (
            db.collection("users")
            .where(filter=FieldFilter("email", "==", email))
            .limit(1)
            .stream()
        )

        user_list = list(users)
        if not user_list:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "user_not_found",
                    "message": "User not found with this email",
                },
            )

        user_doc = user_list[0]
        user_data = user_doc.to_dict() or {}
        user_id = user_doc.id
        username = user_data.get("username")

        if user_data.get("email_verified"):
            return {
                "success": True,
                "message": "Email already verified",
                "already_verified": True,
            }

        new_token = str(uuid.uuid4())

        db.collection("users").document(user_id).update({
            "verify_token": new_token,
            "updated_at": datetime.now(timezone.utc),
        })

        # Pass username so the resent email shows the correct handle.
        send_founding_verification_email(
            email, new_token, username=username
        )

        logger.info(f"Resent verification email to {email}")

        return {
            "success": True,
            "message": "Verification email resent successfully",
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception("Resend verification failed")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "resend_failed",
                "message": (
                    "Failed to resend verification email. "
                    "Please try again."
                ),
            },
        )


@router.get("/status/{email}", response_model=FoundingStatusResponse)
async def check_founding_status(email: str):
    """Check founding member signup status."""
    email = email.lower().strip()

    try:
        users = (
            db.collection("users")
            .where(filter=FieldFilter("email", "==", email))
            .limit(1)
            .stream()
        )

        user_list = list(users)
        if not user_list:
            return {
                "exists": False,
                "verified": False,
                "founding_member": False,
                "onboarding_complete": False,
                "username": None,
            }

        user_data = user_list[0].to_dict() or {}

        return {
            "exists": True,
            "verified": user_data.get("email_verified", False),
            "founding_member": user_data.get("founding_member", False),
            "onboarding_complete": user_data.get("onboarding_complete", False),
            "username": user_data.get("username"),
            "plan": user_data.get("plan", "free"),
        }

    except Exception:
        logger.exception("Status check failed")
        raise HTTPException(
            status_code=500, detail="Failed to check status"
        )