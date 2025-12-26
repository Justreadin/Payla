# routers/auth.py
from typing import Optional
from app.utils.firebase import firestore_run
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, RedirectResponse
from firebase_admin import auth
from datetime import datetime, timedelta, timezone
from google.cloud.firestore_v1.base_query import FieldFilter
from pydantic import BaseModel, EmailStr
from app.services.email_service import send_verification_email, send_reset_password_email
import uuid
from app.tasks.user_verify import delete_unverified_user
from app.models.user_model import User
from app.models.auth_model import LoginRequest, ProfileUpdate, AuthResponse
from app.core.firebase import db
from app.core.auth import get_current_user
from app.core.notifications import create_notification
from app.core.config import settings
from app.utils.security import generate_otp

import logging

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

# Pydantic models to add at the top of the file
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

# ADD TO /auth_router.py
@router.post("/check-email")
async def check_email(data: CheckEmailRequest):
    email = data.email.lower().strip()
    user_doc = await firestore_run(
        db.collection("users").where("email", "==", email).get  # <- note: no ()
    )
    exists = len(user_doc) > 0
    waitlist_doc = await firestore_run(db.collection("waitlist").document(email).get)
    return {"exists": exists, "waitlist": waitlist_doc.exists}


@router.post("/signup-email")
async def signup_email(data: SignupRequest):
    email = data.email.lower().strip()
    password = data.password
    full_name = data.full_name

    logger.info(f"🚀 Signup attempt started for email: {email}")

    try:
        now = datetime.now(timezone.utc)
        trial_end = now + timedelta(days=14)
        # ----------------------------
        # Step 1: Create Firebase Auth user
        # ----------------------------
        logger.info(f"🔹 Creating Firebase Auth user for {email}")
        fb_user = auth.create_user(
            email=email,
            password=password,
            display_name=full_name
        )
        logger.info(f"✅ Firebase Auth user created: {fb_user.uid}")

        # ----------------------------
        # Step 2: Create verification token
        # ----------------------------
        verify_token = str(uuid.uuid4())
        logger.info(f"🔹 Verification token generated: {verify_token}")

        # ----------------------------
        # Step 3: Save user in Firestore marked as unverified
        # ----------------------------
        new_user = User(
            _id=fb_user.uid,
            firebase_uid=fb_user.uid,
            full_name=full_name,
            email=email,
            email_verified=False,
            verify_token=verify_token,
            plan="free",  # Defaulting to silver
            plan_start_date=now,         # Set this!
            trial_end_date=trial_end,    # Set this!
            subscription_end=trial_end,   # Trial is the first "end" date
            created_at=now,
            updated_at=now
        )
        await firestore_run(
            db.collection("users").document(fb_user.uid).set,
            new_user.dict(by_alias=True)
        )
        logger.info(f"✅ Firestore user document created for {email}")

        # ------------------------------------------------------------
        # NEW STEP: Check for Presell Eligibility
        # ------------------------------------------------------------
        # We call this right after the user document is created.
        presell_granted = await auto_grant_presell_on_signup(fb_user.uid, email)
        
        if presell_granted:
            logger.info(f"🎁 Presell benefits applied for {email}")

        # ----------------------------
        # Step 4: Send verification email
        # ----------------------------
        send_verification_email(email, verify_token)
        logger.info(f"📨 Verification email sent to {email}")

        return {"message": "Verification email sent. Please check your inbox."}

    except auth.EmailAlreadyExistsError:
        logger.warning(f"⚠️ Signup failed: Email already in use - {email}")
        raise HTTPException(400, "Email already in use")
    except Exception as e:
        # 🔥 Detailed log with traceback
        import traceback
        tb = traceback.format_exc()
        logger.error(f"🔥 Signup failed for {email}: {str(e)}\nTraceback:\n{tb}")
        raise HTTPException(400, f"Signup failed: {str(e)}")


@router.post("/login-email", response_model=AuthResponse)
async def login(payload: LoginRequest):
    #logger.info(f"🔑 Attempting to verify ID token for payload: {payload.dict()}")
    
    try:
        decoded = auth.verify_id_token(payload.id_token)
        logger.info(f"✅ Token verified successfully | UID: {decoded['uid']} | Email: {decoded.get('email')}")
    except auth.InvalidIdTokenError as e:
        logger.error(f"❌ Invalid ID token: {e}")
        raise HTTPException(status_code=401, detail="Invalid Firebase token")
    except auth.ExpiredIdTokenError as e:
        logger.error(f"❌ Expired ID token: {e}")
        raise HTTPException(status_code=401, detail="Token expired")
    except auth.RevokedIdTokenError as e:
        logger.error(f"❌ Revoked ID token: {e}")
        raise HTTPException(status_code=401, detail="Token revoked")
    except auth.CertificateFetchError as e:
        logger.error(f"❌ Failed to fetch certificates: {e}")
        raise HTTPException(status_code=401, detail="Certificate fetch failed")
    except Exception as e:
        logger.error(f"❌ Unexpected error verifying token: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=401, detail="Token verification failed")

    uid = decoded["uid"]
    fb_user = auth.get_user(uid)
    email = fb_user.email.lower()

    user_doc = await firestore_run(db.collection("users").document(uid).get)
    if not user_doc.exists:
        raise HTTPException(401, "User not found. Please signup first.")
    
    # We check if they are already upgraded to avoid redundant database writes.
    user_data = user_doc.to_dict()
    if not user_data.get("presell_claimed"):
        # If they haven't claimed it yet, check eligibility now
        was_granted = await auto_grant_presell_on_signup(uid, email)
        if was_granted:
            # Refresh user_doc so the AuthResponse contains the updated 'silver' plan
            user_doc = await firestore_run(db.collection("users").document(uid).get)
            user_data = user_doc.to_dict()
            logger.info(f"🎁 Presell benefits applied for {email} during login")

    user = User(**user_doc.to_dict())

    if not user.email_verified:
        return AuthResponse(
            user=user,
            requires_verification=True,
            message="Email not verified. Please check your inbox."
        )

    create_notification(
        user_id=user.id,
        title="Welcome Back!",
        message=f"Hello {user.full_name or user.email}, you've successfully logged in.",
        type="success",
        link="/dashboard"
    )

    return AuthResponse(user=user)

@router.get("/verify-email")
async def verify_email(token: str):
    """Verify user's email and redirect to the next step."""
    users = await firestore_run(
        db.collection("users").where("verify_token", "==", token).stream
    )
    matched_user = None
    for u in users:
        matched_user = u
        break

    if not matched_user:
        raise HTTPException(400, "Invalid or expired token")

    # Update Firestore: mark email verified and clear token
    user_data = matched_user.to_dict()
    await firestore_run(
        db.collection("users").document(matched_user.id).update,
        {"email_verified": True, "verify_token": None}
    )

    # Decide redirect based on onboarding
    onboarding_done = user_data.get("onboarding_complete", False)
    if onboarding_done:
        redirect_url = f"{settings.FRONTEND_URL}dashboard"
    else:
        redirect_url = f"{settings.FRONTEND_URL}onboarding"

    return RedirectResponse(url=redirect_url)

    
@router.get("/confirm-email")
async def confirm_email(oobCode: str = Query(..., alias="oobCode")):
    """
    Verifies the Firebase OOB code, confirms email,
    and creates the Firestore user record.
    """
    try:
        # Verify OOB code via Firebase
        email = auth.verify_oob_code(oobCode, "VERIFY_EMAIL")

        # Fetch Firebase user
        fb_user = auth.get_user_by_email(email)

        # Prevent duplicates
        existing = await firestore_run(db.collection("users").document(fb_user.uid).get)
        if existing.exists:
            return JSONResponse({"message": "Already verified", "redirect": "onboarding"})

        # Create Firestore user now
        user = User(
            _id=fb_user.uid,
            firebase_uid=fb_user.uid,
            full_name=fb_user.display_name or email.split("@")[0],
            email=email,
            email_verified=True,
            plan="free",  # Change silver to free
            trial_end_date=datetime.now(timezone.utc) + timedelta(days=14), # Add this
            created_at=datetime.now(timezone.utc)
        )

        await firestore_run(
            db.collection("users").document(fb_user.uid).set,
            user.dict(by_alias=True)
        )

        return JSONResponse({
            "message": "Email verified successfully",
            "redirect": "/onboarding"
        })

    except Exception as e:
        logger.error(f"❌ Email verification failed: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid or expired verification link.")



@router.post("/resend-verification")
async def resend_verification(data: CheckEmailRequest):
    email = data.email.lower().strip()

    # Fetch the user from Firestore
    user_doc = await firestore_run(db.collection("users").where("email", "==", email).get)
    if not user_doc:
        raise HTTPException(404, "User not found")

    user = User(**user_doc[0].to_dict())

    if user.email_verified:
        return {"message": "Email already verified"}

    # Generate a new verification token
    verify_token = str(uuid.uuid4())
    
    await firestore_run(
        db.collection("users").document(user.id).update, 
        {"verify_token": verify_token}
    )

    # Send verification email via SMTP
    send_verification_email(email, verify_token)
    logger.info(f"📨 Resent verification email to {email}")

    return {"message": "Verification email resent"}

# Check email verification status for frontend polling
@router.get("/check-email-verified")
async def check_email_verified(email: EmailStr = Query(...)):
    """Returns whether the user's email is verified and onboarding status."""
    email = email.lower().strip()
    user_docs = await firestore_run(db.collection("users").where("email", "==", email).get)
    if not user_docs:
        raise HTTPException(404, "User not found")

    user = User(**user_docs[0].to_dict())
    return {
        "verified": user.email_verified,
        "onboarding_complete": getattr(user, "onboarding_complete", False)
    }

    
@router.get("/me", response_model=User)
async def get_me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=User)
async def update_profile(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user)
):
    update_data = payload.dict(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Username validation
    if "username" in update_data:
        username = update_data["username"].lower().strip()
        if not username.replace("-", "").replace("_", "").isalnum():
            raise HTTPException(status_code=400, detail="Username: letters, numbers, -, _ only")
        if len(username) < 3:
            raise HTTPException(status_code=400, detail="Username too short")
        existing_username = await firestore_run(
            db.collection("paylinks").where("username", "==", username).get
        )
        if existing_username:
            raise HTTPException(status_code=400, detail="Username taken")
        update_data["username"] = username

    update_data["updated_at"] = datetime.utcnow()
    await firestore_run(db.collection("users").document(user.id).update(update_data))

    # Notify user of profile update
    create_notification(
        user_id=user.id,
        title="Profile Updated",
        message="Your profile details have been successfully updated.",
        type="info",
        link="/dashboard/profile"
    )

    updated = await firestore_run(db.collection("users").document(user.id).get)
    return User(**updated.to_dict())


@router.post("/forgot-password")
async def forgot_password(data: ForgotPasswordRequest):
    email = data.email.lower().strip()

    # Check if user exists
    user_docs = await firestore_run(db.collection("users").where("email", "==", email).get)
    if not user_docs:
        raise HTTPException(404, "No account found with this email")

    user = User(**user_docs[0].to_dict())

    # Generate 6-digit OTP
    code = generate_otp()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    # Store reset code
    await firestore_run(
        db.collection("password_resets").document(user.id).set,
        {
            "user_id": user.id,
            "email": email,
            "code": code,
            "expires_at": expires_at,
            "used": False,
            "created_at": datetime.utcnow()
        }
    )

    # Email the code to the user
    send_reset_password_email(email, code)  # your email service

    return {
        "message": "Verification code sent",
        "expires_in": 600  # 10 minutes
    }



@router.post("/reset-password")
async def reset_password_with_code(req: ResetPasswordCodeRequest):
    docs = await firestore_run(db.collection("password_resets") \
             .where("email", "==", req.email) \
             .where("code", "==", req.code) \
             .get)

    if not docs:
        raise HTTPException(400, "Invalid reset code")

    data = docs[0].to_dict()

    expires_at = data["expires_at"]

    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(400, "Code expired")

    # Update Firebase password
    fb_user = auth.get_user_by_email(req.email)
    auth.update_user(fb_user.uid, password=req.new_password)

    # Mark code as used
    await firestore_run(
        db.collection("password_resets")
            .document(docs[0].id)
            .update,
        {
            "used": True,
            "used_at": datetime.utcnow()
        }
    )


    return {"message": "Password reset successful"}


@router.post("/verify-reset-code")
async def verify_reset_code(req: VerifyCodeRequest):
    docs = await firestore_run(db.collection("password_resets") \
             .where("email", "==", req.email) \
             .where("code", "==", req.code) \
             .get)

    if not docs:
        raise HTTPException(400, "Invalid code")

    data = docs[0].to_dict()

    expires_at = data["expires_at"]

    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)

    if now > expires_at:
        raise HTTPException(400, "Code expired")

    # SUCCESS RESPONSE — THIS WAS MISSING
    return {
        "valid": True,
        "message": "Code verified"
    }


@router.post("/logout")
async def logout():
    """
    Logout endpoint: frontend should also clear Firebase and localStorage.
    """
    return {"message": "Logged out successfully"}



# ============================================================
# 5. AUTO-GRANT ON SIGNUP (call this in your signup endpoint)
# ============================================================
async def auto_grant_presell_on_signup(user_id: str, email: str):
    """
    Call this function RIGHT AFTER creating a new user or during login.
    Automatically grants 1-year subscription if they paid presell.
    """
    try:
        email = email.lower().strip()
        
        # 1. Check eligibility from the master presell collection
        presell_doc = await firestore_run(db.collection("presell_emails").document(email).get)
        
        if not presell_doc.exists:
            logger.info(f"User {email} did not pay for presell")
            return False
        
        presell_data = presell_doc.to_dict()
        
        # 2. Check if verification was successful (must match what verify-payment sets)
        if not presell_data.get("payment_verified"):
            logger.warning(f"User {email} presell record exists but payment_verified is False")
            return False
        
        # 3. Calculate 1 year from NOW
        now = datetime.now(timezone.utc)
        one_year_later = now + timedelta(days=365)
        
        # 4. Atomic update to user plan
        await firestore_run(
            db.collection("users").document(user_id).update,
            {
                "plan": "silver", 
                "plan_start_date": now,
                "subscription_end": one_year_later,
                "presell_end_date": one_year_later,
                "next_billing_date": one_year_later,
                "presell_claimed": True,
                "presell_eligible": True,
                "presell_id": presell_data.get("presell_id", "founding_creator"),
                "updated_at": now
            }
        )
        
        logger.info(f"✅ Auto-granted 1-year subscription to {email} (UID: {user_id})")
        
        # 5. In-app notification
        create_notification(
            user_id=user_id,
            title="Welcome, Founding Creator! 🎉",
            message="Your email was recognized! You've been upgraded to 1-Year Payla Silver.",
            type="success",
            link="/dashboard"
        )
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to auto-grant presell: {e}")
        return False