# routers/paylink.py
import logging
from datetime import datetime
from typing import Literal
import uuid
import time
from app.models.user_model import User
from fastapi import APIRouter, HTTPException, Depends, status

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

from fastapi import BackgroundTasks
from app.routers.payout_router import queue_payout

from app.tasks.payout import initiate_payout
import asyncio
from app.tasks.payout_celery import payout_task

from app.core.subscription import require_silver  # ← Subscription enforcement

logger = logging.getLogger("payla")
router = APIRouter(prefix="/paylinks", tags=["Paylinks"])


# --------------------------------------------------------------
# Helper: Ensure Paystack page exists
# --------------------------------------------------------------
async def ensure_paystack_page(paylink: dict) -> dict:
    # If both page URL and reference exist, just return the paylink
    if paylink.get("paystack_page_url") and paylink.get("paystack_reference"):
        return paylink

    username = paylink["username"]
    display_name = paylink["display_name"]
    user_id = paylink.get("_id") or paylink.get("user_id")

    try:
        # Only 2 arguments now
        page_data = await create_permanent_payment_page(username, display_name)

        # Update the paylink dict
        paylink.update({
            "paystack_page_url": page_data["url"],
            "paystack_reference": page_data["reference"],
            "updated_at": datetime.utcnow()
        })

        # Persist to Firestore
        db.collection("paylinks").document(user_id).update({
            "paystack_page_url": page_data["url"],
            "paystack_reference": page_data["reference"],
            "updated_at": datetime.utcnow()
        })

        logger.info(f"Paystack page created for @{username}: {page_data['url']}")

    except Exception as e:
        logger.error(f"Failed to create Paystack page for @{username}: {e}")

    return paylink


# --------------------------------------------------------------
# 1. CREATE OR UPDATE PAYLINK  ← Protected (Silver/trial)
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

    if not username.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Username: letters, numbers, -, _ only")
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username too short")

    paylink_id = user.id
    link_url = f"{settings.FRONTEND_URL}/@{username}"

    # Check if a paylink already exists
    doc = db.collection("paylinks").document(paylink_id).get()
    if doc.exists:
        data = doc.to_dict()
        # If it exists, only update username, link_url, currency, active
        display_name = user.business_name or user.full_name
        description = user.tagline or "Fast, secure payments via Payla"
        paylink_data = Paylink(
            _id=paylink_id,
            user_id=user.id,
            username=username,
            display_name=data.get("display_name"),  # preserve original
            description=data.get("description"),    # preserve original
            currency=payload.currency,
            active=True,
            link_url=link_url,
            total_received=data.get("total_received", 0.0),
            total_transactions=data.get("total_transactions", 0),
            created_at=data.get("created_at"),
            updated_at=datetime.utcnow()
        )
    else:
        # New paylink: create display_name from business_name/full_name, description from tagline
        display_name = user.business_name or user.full_name
        description = user.tagline or "Description/Tagline"
        paylink_data = Paylink(
            _id=paylink_id,
            user_id=user.id,
            username=username,
            display_name=display_name,
            description=description,
            currency=payload.currency,
            active=True,
            link_url=link_url,
            total_received=0.0,
            total_transactions=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

    db.collection("paylinks").document(paylink_id).set(
        paylink_data.dict(by_alias=True), merge=True
    )

    updated_paylink = await ensure_paystack_page(paylink_data.dict(by_alias=True))
    return Paylink(**updated_paylink)

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
    paylink_query = db.collection("paylinks").where("username", "==", username).limit(1).get()
    
    # Check if username exists in pending payments (lock year registrations)
    pending_query = db.collection("pending_payments").where("username", "==", username).limit(1).get()
    
    # Check if username exists in confirmed users
    confirmed_query = db.collection("confirmed_users").where("username", "==", username).limit(1).get()
    
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
    docs = db.collection("paylinks").where("username", "==", username_clean).limit(1).get()

    if not docs:
        raise HTTPException(status_code=404, detail="Paylink not found or inactive")

    data = docs[0].to_dict()
    data["_id"] = docs[0].id
    owner_id = data.get("user_id")

    # 3. Check the OWNER'S subscription (The "Paid Feature" Gatekeeper)
    # We fetch the owner's user record to see if they have Silver/Gold/Opal
    user_doc = db.collection("users").document(owner_id).get()
    
    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="Paylink owner not found")

    user_data = user_doc.to_dict()
    current_plan = user_data.get("plan", "free").lower()

    # If the owner is not on a paid plan, block public access
    if current_plan not in ["silver", "gold", "opal", "trial"]:
        raise HTTPException(
            status_code=403, 
            detail="This Paylink requires a Payla Silver subscription to be active."
        )

    # 4. Check if the link is manually deactivated
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
# 6. PUBLIC: CREATE PAYLINK TRANSACTION
# --------------------------------------------------------------
@router.post("/{username}/transaction")
async def create_paylink_transaction(username: str, req: CreatePaylinkTransactionRequest):
    paylink_docs = (
        db.collection("paylinks")
        .where("username", "==", username.lower().strip())
        .limit(1)
        .stream()
    )

    paylink = None
    for doc in paylink_docs:
        paylink = doc.to_dict()
        paylink["_id"] = doc.id
        break

    if not paylink:
        raise HTTPException(status_code=404, detail="Paylink not found")

    user_id = paylink["user_id"]
    reference = f"payla_{username}_{uuid.uuid4().hex[:12]}"

    transaction = {
        "paylink_id": paylink["_id"],
        "user_id": user_id,
        "paylink_username": username.lower(),
        "amount_requested": req.amount,
        "amount_paid": 0.0,
        "payer_email": req.payer_email,
        "payer_name": req.payer_name or "Anonymous",
        "payer_phone": req.payer_phone or "",
        "paystack_reference": reference,
        "status": "pending",
        "payout_status": "not_started",
        "last_update": datetime.utcnow(),
        "created_at": datetime.utcnow(),
        "metadata": {"type": "paylink", "notes": getattr(req, "notes", None)},
    }

    db.collection("paylink_transactions").document(reference).set(transaction)

    create_notification(
        user_id=user_id,
        title="New Paylink Transaction",
        message=f"{req.amount} requested via your Paylink",
        type="info",
        link="/dashboard/paylinks"
    )

    return {
        "reference": reference,
        "email": req.payer_email,
        "amount_kobo": int(req.amount * 100),
        "public_key": settings.PAYSTACK_PUBLIC_KEY,
        "metadata": {
            "user_id": user_id,
            "paylink_id": paylink["_id"],
            "paylink_username": username.lower(),
            "payer_name": req.payer_name or "Anonymous",
            "payer_phone": req.payer_phone or "",
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
    docs = db.collection("paylinks").where("username", "==", username).limit(1).get()
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
    docs = db.collection("paylinks").where("username", "==", username).limit(1).get()
    if not docs:
        raise HTTPException(status_code=404, detail="Paylink not found")

    paylink_id = docs[0].id

    increment_paylink_metric(paylink_id, "transfer_clicks")
    increment_daily_metric(paylink_id, "transfer_clicks")
    log_paylink_event(paylink_id, "transfer_click")

    return {"success": True}


@router.patch("/transaction/{reference}/status", include_in_schema=False)
async def update_paylink_transaction_status(
    reference: str,
    status: Literal["pending", "success", "failed"],
    background_tasks: BackgroundTasks
):
    doc_ref = db.collection("paylink_transactions").document(reference)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Transaction not found")

    txn = doc.to_dict()
    
    # Check for already processed to prevent double-counting in CRM
    if txn.get("status") == "success":
        return {"success": True, "message": "Already processed"}

    update_data = {
        "status": status,
        "last_update": datetime.utcnow()
    }

    if status == "success":
        amount = txn.get("amount_paid") or txn.get("amount_requested")
        
        # --- START CRM SYNC ---
        # We use await here to ensure the client is recorded 
        # before the function returns success.
        await sync_client_to_crm(
            merchant_id=txn["user_id"],
            email=txn["payer_email"],
            amount=float(amount)
        )
        # --- END CRM SYNC ---

        # Existing payout logic
        if txn.get("payout_status") != "queued":
            await queue_payout(
                user_id=txn["user_id"],
                amount=amount,
                reference=reference,
                payout_type="paylink"
            )
            update_data["payout_status"] = "queued"

    doc_ref.update(update_data)
    return {"success": True, "status": status}