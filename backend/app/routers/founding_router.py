# routers/founding_router.py
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, EmailStr, validator
from typing import Optional
import uuid
import logging
import re
from firebase_admin import auth
from google.cloud.firestore_v1.base_query import FieldFilter
from fastapi.responses import RedirectResponse

from app.core.firebase import db
from app.services.email_service import send_founding_verification_email
from app.models.user_model import User
from app.core.notifications import create_notification
from app.core.config import settings

logger = logging.getLogger("payla.founding")

router = APIRouter(prefix="/founding", tags=["Founding Members"])

# ===== PYDANTIC MODELS =====
class FoundingSignupRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    
    @validator('username')
    def validate_username(cls, v):
        v = v.lower().strip()
        if len(v) < 3:
            raise ValueError('Username must be at least 3 characters')
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Username can only contain letters, numbers, - and _')
        return v
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v

class FoundingSignupResponse(BaseModel):
    success: bool
    message: str
    requires_verification: bool = True
    email: str
    username: str

class ResendVerificationRequest(BaseModel):
    email: EmailStr

class FoundingStatusResponse(BaseModel):
    exists: bool
    verified: bool = False
    founding_member: bool = False
    plan: str = "free"
    username: Optional[str] = None
    message: Optional[str] = None

# ===== HELPER FUNCTIONS =====
async def check_username_available(username: str) -> bool:
    """Check if username is available in both users and paylinks collections"""
    username = username.lower().strip()
    
    # Check in users collection (existing users with this username)
    user_docs = db.collection("users") \
        .where(filter=FieldFilter("username", "==", username)) \
        .limit(1) \
        .stream()
    
    user_list = list(user_docs)
    if user_list:
        return False
    
    # Check in paylinks collection (active paylinks)
    paylink_docs = db.collection("paylinks") \
        .where(filter=FieldFilter("username", "==", username)) \
        .limit(1) \
        .stream()
    
    paylink_list = list(paylink_docs)
    return len(paylink_list) == 0

async def check_email_exists(email: str) -> tuple[bool, Optional[str]]:
    """Check if email exists in Firebase Auth or Firestore"""
    email = email.lower().strip()
    
    # Check Firebase Auth first
    try:
        fb_user = auth.get_user_by_email(email)
        if fb_user:
            return True, "Email already registered"
    except auth.UserNotFoundError:
        pass  # Email not in Firebase Auth, good
    
    # Check Firestore users collection as backup
    user_docs = db.collection("users") \
        .where(filter=FieldFilter("email", "==", email)) \
        .limit(1) \
        .stream()
    
    user_list = list(user_docs)
    if user_list:
        return True, "Email already registered"
    
    return False, None

async def grant_founding_member_benefits(user_id: str, email: str, username: str):
    """Grant 1-year free subscription after email verification"""
    try:
        now = datetime.now(timezone.utc)
        one_year_later = now + timedelta(days=365)
        
        # Update user with founding member benefits
        db.collection("users").document(user_id).update({
            "plan": "silver",
            "plan_start_date": now,
            "subscription_end": one_year_later,
            "trial_end_date": one_year_later,
            "next_billing_date": one_year_later,
            "founding_member": True,
            "founding_claimed_at": now,
            "founding_member_pending": False,
            "updated_at": now
        })
        
        # Activate the paylink
        db.collection("paylinks").document(user_id).update({
            "active": True,
            "is_active": True,
            "verified_at": now,
            "updated_at": now
        })
        
        logger.info(f"✅ Granted 1-year founding benefits to {email} (UID: {user_id})")
        
        # Create welcome notification
        create_notification(
            user_id=user_id,
            title="🎉 Welcome, Founding Creator!",
            message=f"Your account @{username} is now active with 1-year free access to Payla Silver.",
            type="success",
            link="/dashboard"
        )
        
        return True
    except Exception as e:
        logger.error(f"❌ Failed to grant founding benefits: {e}")
        return False

# ===== ENDPOINTS =====

@router.post("/signup", response_model=FoundingSignupResponse)
async def founding_signup(request: FoundingSignupRequest):
    """
    Founding member signup with 1-year free access upon email verification
    """
    email = request.email.lower().strip()
    username = request.username.lower().strip()
    
    logger.info(f"🚀 Founding signup attempt: {email} | @{username}")
    
    try:
        # 1. Check if username is available
        if not await check_username_available(username):
            raise HTTPException(
                status_code=400, 
                detail={
                    "error": "username_taken",
                    "message": f"@{username} is already taken. Please try another."
                }
            )
        
        # 2. Check if email already exists
        email_exists, email_message = await check_email_exists(email)
        if email_exists:
            raise HTTPException(
                status_code=400, 
                detail={
                    "error": "email_exists",
                    "message": "This email is already registered. Please log in instead."
                }
            )
        
        # 3. Create Firebase Auth user
        fb_user = auth.create_user(
            email=email,
            password=request.password,
            display_name=username
        )
        logger.info(f"✅ Firebase user created: {fb_user.uid}")
        
        # 4. Generate verification token
        verify_token = str(uuid.uuid4())
        
        # 5. Create user in Firestore (unverified)
        now = datetime.now(timezone.utc)
        trial_end = now + timedelta(days=365)
        
        new_user = User(
            _id=fb_user.uid,
            firebase_uid=fb_user.uid,
            full_name=username,
            email=email,
            username=username,
            email_verified=False,
            verify_token=verify_token,
            plan="free",
            trial_end_date=trial_end,
            created_at=now,
            updated_at=now,
            onboarding_complete=False
        )
        
        db.collection("users").document(fb_user.uid).set(
            new_user.dict(by_alias=True)
        )
        
        # Create initial paylink entry (inactive)
        db.collection("paylinks").document(fb_user.uid).set({
            "user_id": fb_user.uid,
            "username": username,
            "display_name": username,
            "description": "One Link. Instant Payments. Zero Hassle.",
            "currency": "NGN",
            "active": False,
            "is_active": False,
            "link_url": f"https://payla.ng/@{username}",
            "total_received": 0.0,
            "total_transactions": 0,
            "created_at": now,
            "updated_at": now
        })
        
        logger.info(f"✅ Firestore user created for {email} with username @{username}")
        
        # 6. Send verification email
        send_founding_verification_email(email, verify_token)
        logger.info(f"📨 Verification email sent to {email}")
        
        return FoundingSignupResponse(
            success=True,
            message="Verification email sent. Please check your inbox to activate your 1-year free access.",
            requires_verification=True,
            email=email,
            username=username
        )
        
    except HTTPException:
        raise
    except auth.EmailAlreadyExistsError:
        raise HTTPException(
            status_code=400, 
            detail={
                "error": "email_exists",
                "message": "This email is already registered. Please log in instead."
            }
        )
    except Exception as e:
        logger.error(f"🔥 Founding signup failed: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail={
                "error": "server_error",
                "message": "Signup failed. Please try again later."
            }
        )

@router.get("/verify-email")
async def verify_founding_email(token: str):
    """
    Verify founding member's email and grant 1-year free access
    Redirect to frontend entry page after verification
    """
    try:
        # Find user by verification token
        users = db.collection("users") \
            .where(filter=FieldFilter("verify_token", "==", token)) \
            .limit(1) \
            .stream()
        
        user_list = list(users)
        if not user_list:
            logger.warning(f"Invalid verification token: {token}")
            # Redirect to entry with error param (optional)
            return RedirectResponse(
                url=f"{settings.FRONTEND_URL}/entry",
                status_code=302
            )
        
        user_doc = user_list[0]
        user_data = user_doc.to_dict()
        user_id = user_doc.id
        email = user_data.get("email")
        username = user_data.get("username")
        
        if not username:
            return RedirectResponse(
                url=f"{settings.FRONTEND_URL}/entry",
                status_code=302
            )
        
        # Check if already verified
        if user_data.get("email_verified"):
            return RedirectResponse(
                url=f"{settings.FRONTEND_URL}/entry",
                status_code=302
            )
        
        now = datetime.now(timezone.utc)
        one_year_later = now + timedelta(days=365)
        
        # Update user as verified and grant 1-year benefits
        db.collection("users").document(user_id).update({
            "email_verified": True,
            "verify_token": None,
            "plan": "silver",
            "plan_start_date": now,
            "subscription_end": one_year_later,
            "trial_end_date": one_year_later,
            "next_billing_date": one_year_later,
            "founding_member": True,
            "founding_claimed_at": now,
            "updated_at": now
        })
        
        # Activate paylink
        db.collection("paylinks").document(user_id).update({
            "active": True,
            "is_active": True,
            "verified_at": now,
            "updated_at": now
        })
        
        logger.info(f"✅ Founding member verified: {email} | 1-year free access granted for @{username}")
        
        # Create welcome notification
        create_notification(
            user_id=user_id,
            title="🎉 Welcome to Payla Silver!",
            message=f"Your email is verified and you now have 1-year free access. Start using payla.ng/@{username}",
            type="success",
            link="/onboarding"
        )
        
        # Redirect to entry page - this is the key fix!
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/entry",
            status_code=302
        )
        
    except Exception as e:
        logger.error(f"🔥 Verification failed: {str(e)}")
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/entry",
            status_code=302
        )


@router.post("/resend-verification")
async def resend_founding_verification(request: ResendVerificationRequest):
    """Resend verification email for founding member"""
    email = request.email.lower().strip()
    
    try:
        # Find user by email
        users = db.collection("users") \
            .where(filter=FieldFilter("email", "==", email)) \
            .limit(1) \
            .stream()
        
        user_list = list(users)
        if not user_list:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "user_not_found",
                    "message": "User not found with this email"
                }
            )
        
        user_doc = user_list[0]
        user_data = user_doc.to_dict()
        user_id = user_doc.id
        username = user_data.get("username")
        
        if user_data.get("email_verified"):
            return {
                "success": True, 
                "message": "Email already verified",
                "already_verified": True
            }
        
        # Generate new verification token
        new_token = str(uuid.uuid4())
        
        db.collection("users").document(user_id).update({
            "verify_token": new_token,
            "updated_at": datetime.now(timezone.utc)
        })
        
        # Send verification email with username
        try:
            from app.services.email_service import send_founding_verification_email
            send_founding_verification_email(email, new_token, username=username)
        except ImportError:
            # Fallback to regular verification email
            from app.services.email_service import send_verification_email
            send_verification_email(email, new_token)
            
        logger.info(f"📨 Resent verification email to {email}")
        
        return {
            "success": True, 
            "message": "Verification email resent successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Resend verification failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "resend_failed",
                "message": "Failed to resend verification email. Please try again."
            }
        )

@router.get("/status/{email}")
async def check_founding_status(email: str):
    """Check founding member signup status"""
    email = email.lower().strip()
    
    try:
        users = db.collection("users") \
            .where(filter=FieldFilter("email", "==", email)) \
            .limit(1) \
            .stream()
        
        user_list = list(users)
        if not user_list:
            return {
                "exists": False,
                "verified": False,
                "founding_member": False,
                "onboarding_complete": False,
                "username": None
            }
        
        user_data = user_list[0].to_dict()
        
        return {
            "exists": True,
            "verified": user_data.get("email_verified", False),
            "founding_member": user_data.get("founding_member", False),
            "onboarding_complete": user_data.get("onboarding_complete", False),
            "username": user_data.get("username"),
            "plan": user_data.get("plan", "free")
        }
        
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to check status")