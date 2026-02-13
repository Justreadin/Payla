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
from app.core.paystack import create_paystack_subaccount # Add this
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
    now = datetime.now(timezone.utc)

    # 1. Validate username format
    if not username.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Username: letters, numbers, -, _ only")
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username too short")
    
    # 2. Check if username is taken by ANOTHER user (not the current user)
    # Check in users collection (excluding current user)
    user_docs = db.collection("users") \
        .where(filter=FieldFilter("username", "==", username)) \
        .limit(2) \
        .get()
    
    for doc in user_docs:
        if doc.id != user.id:  # If another user has this username
            raise HTTPException(status_code=400, detail="Username already taken by another user")

    # Check in paylinks collection (excluding current user's paylink)
    paylink_docs = db.collection("paylinks") \
        .where(filter=FieldFilter("username", "==", username)) \
        .limit(2) \
        .get()
    
    for doc in paylink_docs:
        doc_data = doc.to_dict()
        if doc_data.get("user_id") != user.id:  # If another user's paylink has this username
            raise HTTPException(status_code=400, detail="Username already taken")

    # 3. 🔐 RE-VERIFY payout account
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

    # 4. Build Update Data
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

    # 5. Plan & Subscription Logic Sync
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
    else:
        update_data.update({
            "plan": payload.plan,
            "trial_end_date": None,
            "presell_end_date": None
        })

    # 6. Create Paystack Subaccount
    subaccount_code = await create_paystack_subaccount(
        business_name=resolved["account_name"], 
        bank_code=payload.payout_bank,
        account_number=payload.payout_account_number
    )
    
    if subaccount_code:
        update_data["paystack_subaccount_code"] = subaccount_code

    # 7. Update user document
    db.collection("users").document(user.id).update(update_data)

    # 8. Create/Update paylink
    # First check if paylink already exists
    existing_paylink = db.collection("paylinks").document(user.id).get()
    
    paylink_data = {
        "user_id": user.id,
        "username": username,
        "display_name": update_data["business_name"],
        "paystack_subaccount_code": subaccount_code,
        "description": "One Link. Instant Payments. Zero Hassle.", 
        "currency": "NGN",
        "active": True,
        "link_url": f"https://payla.ng/@{username}",
        "total_received": 0.0,
        "total_transactions": 0,
        "created_at": now if not existing_paylink.exists else existing_paylink.to_dict().get("created_at", now),
        "updated_at": now
    }
    
    if existing_paylink.exists:
        db.collection("paylinks").document(user.id).update(paylink_data)
    else:
        db.collection("paylinks").document(user.id).set(paylink_data)

    # 9. Return fresh user
    updated_doc = db.collection("users").document(user.id).get()
    user_data = updated_doc.to_dict()
    user_data["_id"] = user.id
    
    fresh_user = User(**user_data)
    
    # 10. Background Service
    layla = LaylaOnboardingService()
    layla.send_immediate_welcome(fresh_user)

    return fresh_user

@router.get("/validate-username")
async def validate_username(
    username: str = Query(...), 
    current_user_id: str = Query(None, description="Current user ID to exclude from check")
):
    """
    Checks if the username is already taken by another user.
    - If no current_user_id (landing page): strict check - must be completely available
    - If current_user_id provided (onboarding): exclude this user's own records
    Returns { "available": true/false }.
    """
    username = username.lower().strip()
    
    # Validate format
    if len(username) < 3:
        return {"available": False, "message": "Username must be at least 3 characters"}
    
    if not username.replace("-", "").replace("_", "").isalnum():
        return {"available": False, "message": "Username can only contain letters, numbers, - and _"}

    # CASE 1: Landing page check (no user ID)
    if not current_user_id:
        # Strict check - must be completely available
        user_docs = db.collection("users") \
            .where(filter=FieldFilter("username", "==", username)) \
            .limit(1) \
            .get()
        
        if user_docs:
            return {"available": False, "message": "Username already taken"}
        
        paylink_docs = db.collection("paylinks") \
            .where(filter=FieldFilter("username", "==", username)) \
            .limit(1) \
            .get()
        
        if paylink_docs:
            return {"available": False, "message": "Username already taken"}
            
        return {"available": True, "message": "Username is available"}
    
    # CASE 2: Onboarding check (with user ID)
    else:
        # Check in users collection (excluding current user)
        user_docs = db.collection("users") \
            .where(filter=FieldFilter("username", "==", username)) \
            .limit(2) \
            .get()
        
        # If any user OTHER than current has this username
        for doc in user_docs:
            if doc.id != current_user_id:
                return {"available": False, "message": "Username already taken by another user"}

        # Check in paylinks collection (excluding current user's paylink)
        paylink_docs = db.collection("paylinks") \
            .where(filter=FieldFilter("username", "==", username)) \
            .limit(2) \
            .get()
        
        for doc in paylink_docs:
            doc_data = doc.to_dict()
            # If this paylink belongs to someone else
            if doc_data.get("user_id") != current_user_id:
                return {"available": False, "message": "Username already taken"}

        # If we get here, username is available for this user
        return {"available": True, "message": "Username is available"}