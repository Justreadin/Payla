# core/auth.py → FIXED VERSION
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth
from typing import Optional
import logging

from app.models.user_model import User
from app.core.firebase import db

logger = logging.getLogger("payla")
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)
) -> Optional[User]:
    if not credentials:
        return None  # ← Allow unauthenticated routes

    token = credentials.credentials
    try:
        decoded = auth.verify_id_token(token)
    except Exception as e:
        logger.warning(f"Token verification failed: {e}")
        return None

    uid = decoded["uid"]
    user_doc = db.collection("users").document(uid).get()

    if not user_doc.exists:
        # Auto-create user
        try:
            firebase_user = auth.get_user(uid)
            new_user_data = {
                "_id": uid,
                "firebase_uid": uid,
                "full_name": firebase_user.display_name or firebase_user.email.split("@")[0],
                "email": firebase_user.email,
                "email_verified": firebase_user.email_verified,
                "phone_number": firebase_user.phone_number or "",
                "business_name": "",
                "username": "",
                "plan": "silver",
                "total_earned": 0.0,
                "total_invoices": 0,
                "onboarding_complete": False,
                "created_at": db.server_timestamp()
            }
            db.collection("users").document(uid).set(new_user_data)
            return User(**new_user_data)
        except Exception as e:
            logger.error(f"Failed to auto-create user {uid}: {e}")
            return None

    return User(**user_doc.to_dict())


# ------------------------------------------------------------
# 2. OPTIONAL: Get user by UID (internal use)
# ------------------------------------------------------------
def get_user_by_uid(uid: str) -> Optional[User]:
    doc = db.collection("users").document(uid).get()
    return User(**doc.to_dict()) if doc.exists else None


async def onboarding_guard(user: User = Depends(get_current_user)):
    """Allow only users with verified email and incomplete onboarding"""
    if not user.email_verified:
        raise HTTPException(403, "Email not verified")
    if getattr(user, "onboarding_complete", False):
        raise HTTPException(403, "Onboarding already completed")
    return user