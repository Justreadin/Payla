# routers/paylink.py
import logging
from datetime import datetime
from typing import Literal
import uuid
import time
from app.models.user_model import User
from fastapi import APIRouter, HTTPException, Depends, status
from google.cloud.firestore_v1.base_query import FieldFilter
from app.models.paylink_model import PaylinkCreate, Paylink, CreatePaylinkTransactionRequest
from app.core.firebase import db
from app.core.auth import get_current_user
from app.core.config import settings
from app.utils.crm import sync_client_to_crm 
from app.core.paystack import create_permanent_payment_page
from app.core.notifications import create_notification
from app.core.analytics import (
    increment_daily_metric,
    increment_paylink_metric,
    log_paylink_event
)
from app.core.subscription import can_access_silver_features

from fastapi import BackgroundTasks
from app.routers.payout_router import queue_payout

#from app.tasks.payout import initiate_payout
import asyncio
#from app.tasks.payout_celery import payout_task

from app.core.subscription import require_silver  # ← Subscription enforcement

logger = logging.getLogger("payla")
router = APIRouter(prefix="/paylinks", tags=["Paylinks"])


# --------------------------------------------------------------
# Helper: Ensure Paystack page exists (Subaccount Version)
# --------------------------------------------------------------
async def ensure_paystack_page(paylink: dict) -> dict:
    """
    Checks if a permanent Paystack page exists. If not, it fetches the 
    user's subaccount_code and creates a split-payment page.
    """
    # If page already exists, we are good
    if paylink.get("paystack_page_url") and paylink.get("paystack_reference"):
        return paylink

    username = paylink["username"]
    display_name = paylink["display_name"]
    user_id = paylink.get("user_id")

    try:
        # 1. Fetch user's subaccount code from their profile
        user_doc = db.collection("users").document(user_id).get()
        if not user_doc.exists:
            logger.error(f"User {user_id} not found while creating page")
            return paylink
            
        user_data = user_doc.to_dict()
        subaccount_code = user_data.get("paystack_subaccount_code")

        if not subaccount_code:
            logger.warning(f"⚠️ User {user_id} has no subaccount_code. Split payment page creation skipped.")
            return paylink

        # 2. Create permanent payment page linked to the subaccount
        # This ensures money is split automatically at source
        page_data = await create_permanent_payment_page(
            username, 
            display_name, 
            subaccount_code
        )

        update_payload = {
            "paystack_page_url": page_data["url"],
            "paystack_reference": page_data["reference"],
            "paystack_subaccount_code": subaccount_code, # Track which subaccount is linked
            "updated_at": datetime.utcnow()
        }

        # 3. Persist to Paylinks collection
        paylink.update(update_payload)
        db.collection("paylinks").document(user_id).update(update_payload)

        logger.info(f"✅ Paystack split-page created for @{username} (Subaccount: {subaccount_code})")

    except Exception as e:
        logger.error(f"❌ Failed to create Paystack page for @{username}: {e}")

    return paylink


# --------------------------------------------------------------
# 1. CREATE OR UPDATE PAYLINK
# --------------------------------------------------------------
@router.post(
    "/",
    response_model=Paylink,
    status_code=status.HTTP_201_CREATED
)
async def create_or_update_paylink(
    payload: PaylinkCreate,
    current_user=Depends(get_current_user)
):
    user = current_user
    username = payload.username.lower().strip()

    # Validation
    if not username.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Username: letters, numbers, -, _ only")
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username too short")

    paylink_id = user.id  # We use user_id as the document ID for paylinks
    link_url = f"{settings.FRONTEND_URL}/@{username}"

    # Check for existing paylink
    doc_ref = db.collection("paylinks").document(paylink_id)
    doc = doc_ref.get()
    
    now = datetime.utcnow()

    if doc.exists:
        data = doc.to_dict()
        # Update logic: keep history, update link info
        paylink_data = Paylink(
            _id=paylink_id,
            user_id=user.id,
            username=username,
            display_name=data.get("display_name") or user.business_name or user.full_name,
            description=data.get("description") or user.tagline or "Fast, secure payments",
            currency=payload.currency,
            active=True,
            link_url=link_url,
            total_received=data.get("total_received", 0.0),
            total_transactions=data.get("total_transactions", 0),
            created_at=data.get("created_at"),
            updated_at=now
        )
    else:
        # Initial creation logic
        paylink_data = Paylink(
            _id=paylink_id,
            user_id=user.id,
            username=username,
            display_name=user.business_name or user.full_name,
            description=user.tagline or "Accept payments easily with Payla",
            currency=payload.currency,
            active=True,
            link_url=link_url,
            total_received=0.0,
            total_transactions=0,
            created_at=now,
            updated_at=now
        )

    # Save initial record (without Paystack URLs yet)
    doc_ref.set(paylink_data.dict(by_alias=True), merge=True)

    # 4. Trigger the Paystack Page creation with subaccount linkage
    updated_paylink_dict = await ensure_paystack_page(paylink_data.dict(by_alias=True))
    
    return Paylink(**updated_paylink_dict)


# routers/paylink.py - Add this endpoint
@router.post("/check-username")
async def check_username_availability(payload: dict):
    """
    Check if a username is available for new registration.
    This is for the pre-launch lock year functionality.
    """
    username = payload.get("username", "").lower().strip()
    
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    
    if not username.replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Username: letters, numbers, _ only")
    
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username too short")
    
    if len(username) > 20:
        raise HTTPException(status_code=400, detail="Username too long")
    
    # Check if username exists in paylinks
    paylink_query = db.collection("paylinks").where(filter=FieldFilter("username", "==", username)).limit(1).get()
    
    # Check if username exists in pending payments (lock year registrations)
    pending_query = db.collection("pending_payments").where(filter=FieldFilter("username", "==", username)).limit(1).get()
    
    # Check if username exists in confirmed users
    confirmed_query = db.collection("confirmed_users").where(filter=FieldFilter("username", "==", username)).limit(1).get()
    
    if paylink_query or pending_query or confirmed_query:
        return {
            "available": False,
            "message": f"@{username} is already taken"
        }
    
    # Check for reserved usernames (admin reserved)
    reserved_usernames = ["admin", "support", "payla", "help", "system"]
    if username in reserved_usernames:
        return {
            "available": False,
            "message": "This username is reserved"
        }
    
    # Check for inappropriate usernames
    inappropriate_words = ["fuck", "shit", "ass", "bitch", "nigga", "nigger", "cunt"]
    if any(word in username for word in inappropriate_words):
        return {
            "available": False,
            "message": "Username contains inappropriate content"
        }
    
    return {
        "available": True,
        "username": username,
        "message": f"@{username} is available!"
    }

# --------------------------------------------------------------
# 2. GET MY PAYLINK (no restriction)
# --------------------------------------------------------------
@router.get("/me", response_model=Paylink)
async def get_my_paylink(current_user=Depends(get_current_user)):
    user = current_user
    doc = db.collection("paylinks").document(user.id).get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Paylink not found. Create one first.")

    data = doc.to_dict()
    data["_id"] = doc.id

    # Preserve the original paylink display_name for the paylink page
    paylink_page_name = data.get("display_name")

    data = await ensure_paystack_page(data)

    data["display_name"] = user.business_name or user.full_names

    return Paylink(**data)


# --------------------------------------------------------------
# 3. GET PAYLINK BY USERNAME (public)
# --------------------------------------------------------------
@router.get("/{username}", response_model=Paylink)
async def get_paylink_by_username(username: str):
    # 1. Clean the username input
    username_clean = username.lower().lstrip("@").strip()
    if not username_clean:
        raise HTTPException(status_code=404, detail="Invalid username")

    # 2. Query for the paylink document
    docs = db.collection("paylinks").where(filter=FieldFilter("username", "==", username_clean)).limit(1).get()

    if not docs:
        raise HTTPException(status_code=404, detail="Paylink not found or inactive")

    data = docs[0].to_dict()
    data["_id"] = docs[0].id
    owner_id = data.get("user_id")

    # 3. Check the OWNER'S subscription/trial/grace status
    user_doc = db.collection("users").document(owner_id).get()
    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="Paylink owner not found")

    user_data = user_doc.to_dict()
    
    # Initialize the User model with owner data to use the judge
    owner_user = User(**user_data)
    
    # Manually attach subscription_end for the logic in core/subscription.py
    if "subscription_end" in user_data:
        setattr(owner_user, "subscription_end", user_data["subscription_end"])

    # ENFORCEMENT: Check Hierarchy (Presell > Paid > Grace > Trial)
    if not can_access_silver_features(owner_user):
        logger.warning(f"Access denied for Paylink @{username_clean}: Owner subscription expired.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="This Paylink is currently unavailable. If you are the owner, please check your subscription status."
        )

    # 4. Check if the link is manually deactivated by the user
    if not data.get("active", True):
        raise HTTPException(status_code=404, detail="Paylink is currently inactive")

    # 5. Sync branding (Override display_name with current profile data)
    data["display_name"] = user_data.get("business_name") or user_data.get("full_name")
    
    # 6. Ensure Paystack connection is ready
    data = await ensure_paystack_page(data)

    return Paylink(**data)

# --------------------------------------------------------------
# 4. DEACTIVATE PAYLINK  ← Protected
# --------------------------------------------------------------
@router.patch("/me/deactivate")
async def deactivate_paylink(current_user=Depends(get_current_user)):
    ref = db.collection("paylinks").document(current_user.id)
    doc = ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="No paylink to deactivate")

    ref.update({"active": False, "updated_at": datetime.utcnow()})

    # Notification
    create_notification(
        user_id=current_user.id,
        title="Paylink Deactivated",
        message="Your Paylink has been deactivated. You won't receive payments until reactivated.",
        type="info",
        link="/dashboard/paylinks"
    )

    return {"message": "Paylink deactivated"}


# --------------------------------------------------------------
# 5. ACTIVATE PAYLINK  ← Protected
# --------------------------------------------------------------
@router.patch("/me/activate")
async def activate_paylink(current_user=Depends(get_current_user)):
    ref = db.collection("paylinks").document(current_user.id)
    doc = ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="No paylink to activate")

    ref.update({"active": True, "updated_at": datetime.utcnow()})

    # Notification
    create_notification(
        user_id=current_user.id,
        title="Paylink Activated",
        message="Your Paylink is now active. You can receive payments.",
        type="success",
        link="/dashboard/paylinks"
    )

    return {"message": "Paylink activated"}

# --------------------------------------------------------------
# 6. PUBLIC: CREATE PAYLINK TRANSACTION (Updated for Subaccounts)
# --------------------------------------------------------------
@router.post("/{username}/transaction")
async def create_paylink_transaction(username: str, req: CreatePaylinkTransactionRequest):
    # 1. Find the Paylink
    paylink_docs = (
        db.collection("paylinks")
        .where(filter=FieldFilter("username", "==", username.lower().strip()))
        .limit(1)
        .get() # Using .get() is more efficient than .stream() for a limit(1)
    )

    if not paylink_docs:
        raise HTTPException(status_code=404, detail="Paylink not found")

    paylink_doc = paylink_docs[0]
    paylink_data = paylink_doc.to_dict()
    user_id = paylink_data["user_id"]
    
    # 2. Fetch the Owner's Subaccount Code
    user_doc = db.collection("users").document(user_id).get()
    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="Owner profile not found")
    
    user_data = user_doc.to_dict()
    subaccount_code = user_data.get("paystack_subaccount_code")

    if not subaccount_code:
        raise HTTPException(
            status_code=400, 
            detail="This creator has not completed their settlement setup."
        )

    # 3. Handle Accurate Math
    # req.amount is the 'totalAmount' from paylink.js (e.g., 1229)
    # We calculate the user's intended share. 
    # If your frontend doesn't send 'amount_requested' yet, we reverse the logic
    # but the best way is to ensure your frontend sends the original base amount too.
    
    total_to_charge = float(req.amount)
    # Fallback: if frontend doesn't pass requested_amount, 
    # we assume a 3% total overhead as a safety estimate, 
    # but ideally, you should update your Request Model to include 'amount_requested'
    requested_amount = getattr(req, "amount_requested", total_to_charge / 1.025) 
    
    # The 'extra' buffer (The portion of the fee that stays with Payla)
    # This covers the gap between (Total - Paystack Fee) and the User's Target
    payla_buffer = total_to_charge - requested_amount

    reference = f"payla_{username}_{uuid.uuid4().hex[:12]}"

    # 4. Save Pending Transaction to Firestore
    transaction = {
        "paylink_id": paylink_doc.id,
        "user_id": user_id,
        "paylink_username": username.lower(),
        "amount_requested": requested_amount, # The "clean" amount for David
        "amount_paid": total_to_charge,        # The "gross" amount the client pays
        "payer_email": req.payer_email,
        "payer_name": req.payer_name or "Anonymous",
        "payer_phone": req.payer_phone or "",
        "paystack_reference": reference,
        "paystack_subaccount_code": subaccount_code,
        "status": "pending",
        "payout_status": "split_automated",
        "last_update": datetime.utcnow(),
        "created_at": datetime.utcnow(),
        "metadata": {
            "type": "paylink", 
            "requested_amount": requested_amount,
            "notes": getattr(req, "notes", None)
        },
    }

    db.collection("paylink_transactions").document(reference).set(transaction)

    # 5. Return data to Frontend
    return {
        "reference": reference,
        "email": req.payer_email,
        "amount_kobo": int(total_to_charge * 100),
        "public_key": settings.PAYSTACK_PUBLIC_KEY,
        "subaccount": subaccount_code, 
        "bearer": "subaccount",
        # This is the "Magic" field. It pulls the extra money to YOUR account
        # instead of letting David keep the extra ₦10.56
        "transaction_charge": int(payla_buffer * 100), 
        "metadata": {
            "user_id": user_id,
            "paylink_id": paylink_doc.id,
            "paylink_username": username.lower(),
            "requested_amount": requested_amount,
            "type": "paylink"
        }
    }
    
# --------------------------------------------------------------
# 7. PUBLIC: GET TRANSACTION STATUS
# --------------------------------------------------------------
@router.get("/{username}/transaction/{reference}")
async def get_paylink_transaction_status(username: str, reference: str):
    doc = db.collection("paylink_transactions").document(reference).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Transaction not found")

    txn = doc.to_dict()
    if txn["paylink_username"].lower() != username.lower():
        raise HTTPException(status_code=400, detail="Transaction does not belong to this username")

    return txn


# --------------------------------------------------------------
# 8. PUBLIC: Track page view
# --------------------------------------------------------------
@router.post("/{username}/analytics/view")
async def track_page_view(username: str):
    docs = db.collection("paylinks").where(filter=FieldFilter("username", "==", username)).limit(1).get()
    if not docs:
        raise HTTPException(status_code=404, detail="Paylink not found")

    paylink_id = docs[0].id

    increment_paylink_metric(paylink_id, "page_views")
    increment_daily_metric(paylink_id, "page_views")
    log_paylink_event(paylink_id, "page_view")

    return {"success": True}


# --------------------------------------------------------------
# 9. PUBLIC: Track transfer click
# --------------------------------------------------------------
@router.post("/{username}/analytics/transfer")
async def track_transfer_click(username: str):
    docs = db.collection("paylinks").where(filter=FieldFilter("username", "==", username)).limit(1).get()
    if not docs:
        raise HTTPException(status_code=404, detail="Paylink not found")

    paylink_id = docs[0].id

    increment_paylink_metric(paylink_id, "transfer_clicks")
    increment_daily_metric(paylink_id, "transfer_clicks")
    log_paylink_event(paylink_id, "transfer_click")

    return {"success": True}

