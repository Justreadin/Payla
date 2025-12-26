# routers/onboarding.py → FINAL
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Literal
from app.core.auth import get_current_user, onboarding_guard
from app.core.firebase import db
from app.models.user_model import User
from datetime import datetime, timedelta, timezone
from app.routers.payout_router import resolve_account_name
from app.services.layla_service import LaylaOnboardingService
from google.cloud.firestore_v1.base_query import FieldFilter

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])

class OnboardingPayload(BaseModel):
    username: str
    payout_bank: str
    payout_account_number: str
    business_name: str = ""
    plan: Literal["silver", "gold", "opal", "presell", "free"] = "silver"


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
    user: User = Depends(onboarding_guard)
):
    if getattr(user, "onboarding_complete", False):
        raise HTTPException(status_code=400, detail="Onboarding already completed")

    username = payload.username.lower().strip()
    now = datetime.now(timezone.utc) # Single aware timestamp

    # 1. Validate username format & availability
    if not username.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Username: letters, numbers, -, _ only")
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username too short")
    
    username_check = db.collection("paylinks").where(filter=FieldFilter("username", "==", username)).get()
    if username_check:
        raise HTTPException(status_code=400, detail="Username already taken")

    # 2. 🔐 RE-VERIFY payout account
    try:
        resolved = await resolve_account_name(
            payload.payout_bank,
            payload.payout_account_number
        )
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid payout account details"
        )

    # 3. Build Update Data
    update_data = {
        "username": username,
        "payout_bank": payload.payout_bank,
        "payout_account_number": payload.payout_account_number,
        "payout_account_name": resolved["account_name"],
        "payout_bank_name": resolved.get("bank_name", "Unknown Bank"),
        "payout_verified": True,
        "business_name": (payload.business_name or user.full_name).title(),
        "onboarding_complete": True,
        "updated_at": now
    }

    # 4. Plan & Subscription Logic Sync
    if payload.plan == "presell":
        update_data.update({
            "plan": "presell",
            "presell_end_date": now + timedelta(days=365),
            "trial_end_date": None
        })
    elif payload.plan == "free":
        update_data.update({
            "plan": "silver", 
            "trial_end_date": now + timedelta(days=14), 
            "presell_end_date": None
        })
    else:  # Fixed: Ensure "silver/gold/opal" selection from UI also works
        update_data.update({
            "plan": payload.plan,
            "trial_end_date": None,
            "presell_end_date": None
        })

    # 5. Database Operations
    db.collection("users").document(user.id).update(update_data)

    # Create paylink with Luxury Tagline
    paylink_data = {
        "user_id": user.id,
        "username": username,
        "display_name": update_data["business_name"],
        "description": "Your unique payment identity. Get paid instantly.", 
        "currency": "NGN",
        "active": True,
        "link_url": f"https://payla.ng/@{username}",
        "total_received": 0.0,
        "total_transactions": 0,
        "created_at": now,
        "updated_at": now
    }
    db.collection("paylinks").document(user.id).set(paylink_data)

    # 6. Return fresh user
    updated_doc = db.collection("users").document(user.id).get()
    user_data = updated_doc.to_dict()
    user_data["_id"] = user.id # Critical for Pydantic alias
    
    fresh_user = User(**user_data)
    
    # 7. Background Service
    layla = LaylaOnboardingService()
    layla.send_immediate_welcome(fresh_user)

    return fresh_user


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
    existing = db.collection("paylinks").where(filter=FieldFilter("username", "==", username)).get()
    if existing:
        return {"available": False, "message": "Username already taken"}

    return {"available": True, "message": "Username is available"}