# app/core/subscription.py
from fastapi import Depends, HTTPException, status
from app.core.auth import get_current_user
from app.models.user_model import User
from app.core.firebase import db
from datetime import datetime, timezone, timedelta

def parse_firestore_datetime(value):
    if isinstance(value, dict) and "_seconds" in value:
        return datetime.fromtimestamp(value["_seconds"], tz=timezone.utc)
    if isinstance(value, int) or isinstance(value, float):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, datetime):
        return value
    return None

def can_access_silver_features(user: User) -> bool:
    plan = (user.plan or "").lower()
    if plan in ["silver", "gold", "opal"]:
        return True

    trial_end = getattr(user, "trial_end_date", None)
    created_at = getattr(user, "created_at", datetime.now(timezone.utc))

    trial_end_dt = parse_firestore_datetime(trial_end)
    created_at_dt = parse_firestore_datetime(created_at)

    if trial_end_dt is None and isinstance(trial_end, int):
        trial_end_dt = created_at_dt + timedelta(days=trial_end)

    if trial_end_dt and trial_end_dt >= datetime.now(timezone.utc):
        return True

    return False

async def require_silver(user: User = Depends(get_current_user)):
    """
    Ensures access only for Silver/Gold/Opal subscribers or active trial.
    Returns a structured JSON error for free users who need to upgrade.
    """
    user_ref = db.collection("users").document(user.id)
    user_doc = user_ref.get()

    if not user_doc.exists:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    user_data = user_doc.to_dict()
    current_user = User(**user_data)

    if can_access_silver_features(current_user):
        return current_user

    # Structured upgrade response
    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail={
            "message": "Your free trial has ended or this feature requires Payla Silver.",
            "upgrade_to": "silver",
            "cta": "Upgrade now to continue using this feature.",
            "upgrade_url": "/subscription"
        }
    )
