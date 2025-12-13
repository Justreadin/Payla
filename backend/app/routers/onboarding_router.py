# routers/onboarding.py → FINAL
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Literal
from app.core.auth import get_current_user, onboarding_guard
from app.core.firebase import db
from app.models.user_model import User
from datetime import datetime, timedelta

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])

class OnboardingPayload(BaseModel):
    username: str
    payout_bank: str
    payout_account_number: str
    business_name: str = ""
    plan: Literal["silver", "gold", "opal"] = "silver"


@router.get("/me", response_model=User)
async def get_current_onboarding_user(user: User = Depends(get_current_user)):
    """
    Return user's onboarding info.
    If user has a presell entry, include the pre-chosen username.
    """
    # If user already has a username, return as-is
    if user.username:
        return user

    # Otherwise, check presell collection
    presell_doc = db.collection("presell_emails").document(user.email).get()
    if presell_doc.exists:
        presell_data = presell_doc.to_dict()
        user.username = presell_data.get("username", "")
    
    return user


@router.post("/", response_model=User)
async def complete_onboarding(
    payload: OnboardingPayload,
    user: User = Depends(onboarding_guard)  # protected
):
    if getattr(user, "onboarding_complete", False):
        raise HTTPException(status_code=400, detail="Onboarding already completed")

    username = payload.username.lower().strip()

    # Validate username
    if not username.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Username: letters, numbers, -, _ only")
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username too short")
    if db.collection("paylinks").where("username", "==", username).get():
        raise HTTPException(status_code=400, detail="Username taken")
    
    username_check = db.collection("paylinks").where("username", "==", username).get()
    if username_check:
        raise HTTPException(status_code=400, detail="Username already taken")

    now = datetime.utcnow()
    update_data = {
        "username": username,
        "payout_bank": payload.payout_bank,
        "payout_account_number": payload.payout_account_number,
        "business_name": payload.business_name or user.full_name,
        "onboarding_complete": True,
        "updated_at": now
    }

    # PLAN LOGIC
    if payload.plan == "presell":
        update_data.update({
            "plan": "presell",
            "presell_end_date": now + timedelta(days=365),
            "trial_end_date": None
        })
    elif payload.plan == "free-trial":
        update_data.update({
            "plan": "silver",
            "trial_end_date": now + timedelta(days=7),
            "presell_end_date": None
        })
    else:  # monthly
        update_data.update({
            "plan": "silver",
            "trial_end_date": None,
            "presell_end_date": None
        })

    db.collection("users").document(user.id).update(update_data)

    # Create paylink
    paylink_data = {
        "user_id": user.id,
        "username": username,
        "display_name": payload.business_name or user.full_name,
        "description": "Fast, secure payments via Payla",
        "currency": "NGN",
        "active": True,
        "link_url": f"https://payla.ng/@{username}",
        "total_received": 0.0,
        "total_transactions": 0,
        "created_at": now,
        "updated_at": now
    }
    db.collection("paylinks").document(user.id).set(paylink_data)

    updated_doc = db.collection("users").document(user.id).get()
    return User(**updated_doc.to_dict())


@router.get("/validate-username")
async def validate_username(username: str = Query(...)):
    """
    Checks if the username is already taken.
    Returns { "available": true/false }.
    """
    username = username.lower().strip()
    if len(username) < 3 or not username.replace("-", "").replace("_", "").isalnum():
        return {"available": False, "message": "Invalid username format"}

    # Check if username exists in paylinks collection
    existing = db.collection("paylinks").where("username", "==", username).get()
    if existing:
        return {"available": False, "message": "Username already taken"}

    return {"available": True, "message": "Username is available"}