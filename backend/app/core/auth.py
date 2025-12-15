# core/auth.py
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
) -> User:
    """
    Returns the currently authenticated user.
    Raises 401 if token is missing or invalid.
    Auto-creates user in Firestore if not exists.
    """
    if not credentials:
        # No token provided
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    token = credentials.credentials
    try:
        decoded = auth.verify_id_token(token)
    except Exception as e:
        logger.warning(f"Token verification failed: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token")

    uid = decoded.get("uid")
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    user_doc = db.collection("users").document(uid).get()

    if not user_doc.exists:
        # Auto-create user in Firestore
        try:
            firebase_user = auth.get_user(uid)
            new_user_data = {
                "_id": uid,
                "firebase_uid": uid,
                "full_name": firebase_user.display_name or (firebase_user.email.split("@")[0] if firebase_user.email else ""),
                "email": firebase_user.email or "",
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
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create user")

    return User(**user_doc.to_dict())


# ------------------------------------------------------------
# Optional helper: Get user by UID (internal use)
# ------------------------------------------------------------
def get_user_by_uid(uid: str) -> Optional[User]:
    doc = db.collection("users").document(uid).get()
    return User(**doc.to_dict()) if doc.exists else None


async def onboarding_guard(user: User = Depends(get_current_user)):
    """
    Guard route for users with verified email and incomplete onboarding.
    """
    if not user.email_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email not verified")
    if getattr(user, "onboarding_complete", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Onboarding already completed")
    return user
