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
    Return the currently authenticated user.

    Raises 401 if the token is missing or invalid.
    Auto-creates a free-tier user in Firestore if the document does not exist.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    token = credentials.credentials
    try:
        decoded = auth.verify_id_token(token)
    except Exception as e:
        logger.warning(f"Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )

    uid = decoded.get("uid")
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    user_doc = db.collection("users").document(uid).get()

    if not user_doc.exists:
        return await _auto_create_user(uid)

    return User(**user_doc.to_dict())


async def _auto_create_user(uid: str) -> User:
    """
    Create a minimal free-tier user document.

    The document is initialised with safe defaults for every field that
    subscription and onboarding logic reads, so downstream code never has
    to handle missing keys.
    """
    try:
        firebase_user = auth.get_user(uid)
    except Exception as e:
        logger.error(f"Failed to load Firebase user {uid}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load user account",
        )

    email = firebase_user.email or ""
    display_name = firebase_user.display_name or (
        email.split("@")[0] if email else ""
    )

    new_user_data = {
        "_id": uid,
        "firebase_uid": uid,

        # Identity
        "full_name": display_name,
        "email": email,
        "email_verified": firebase_user.email_verified,
        "phone_number": firebase_user.phone_number or "",

        # Profile (completed during onboarding)
        "business_name": "",
        "username": "",
        "tagline": "",
        "logo_url": "",
        "onboarding_complete": False,

        # Plan and subscription — free by default.
        "plan": "free",
        "subscription_status": "inactive",
        "subscription_end": None,
        "next_billing_date": None,
        "cancel_at_period_end": False,
        "manual_silver_override": False,

        # Earnings and balances
        "total_earned": 0.0,
        "total_invoice_revenue": 0.0,
        "total_paylink_revenue": 0.0,

        # Payout linkage
        "paystack_subaccount_code": None,

        # Bank confirmation (populated after payout setup)
        "bank_confirmation_status": "pending",
        "bank_confirmed_name": None,
        "bank_confirmed_bank_name": None,
        "bank_confirmed_account_last4": None,
        "bank_confirmed_at": None,
        "bank_confirmation_attempted_at": None,
        "bank_confirmation_retry_count": 0,

        # Invoice preferences
        "default_invoice_fee_payer": "merchant",
        "custom_invoice_colors": None,

        # Metadata
        "created_at": db.server_timestamp(),
        "updated_at": db.server_timestamp(),
    }

    try:
        db.collection("users").document(uid).set(new_user_data)
    except Exception as e:
        logger.error(f"Failed to auto-create user {uid}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user",
        )

    return User(**new_user_data)


# ------------------------------------------------------------
# Optional helper: get user by UID (internal use)
# ------------------------------------------------------------
def get_user_by_uid(uid: str) -> Optional[User]:
    doc = db.collection("users").document(uid).get()
    return User(**doc.to_dict()) if doc.exists else None


async def onboarding_guard(user: User = Depends(get_current_user)):
    """
    Guard route for users with verified email and incomplete onboarding.
    """
    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified",
        )
    if getattr(user, "onboarding_complete", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Onboarding already completed",
        )
    return user