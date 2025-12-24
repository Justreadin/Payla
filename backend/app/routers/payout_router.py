# routers/payout.py → FULLY INTEGRATED VERSION
import asyncio
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, validator
from typing import Optional
from app.core.auth import get_current_user
from app.models.user_model import User
import httpx
from firebase_admin import firestore
from datetime import datetime, timezone
from app.tasks.payout import initiate_payout
import logging
from app.tasks.payout_celery import payout_task

from app.core.config import settings

router = APIRouter(prefix="/payout", tags=["Payout Settings"])
logger = logging.getLogger("payla")
db = firestore.client()

# ==================== Models ====================
class PayoutAccountIn(BaseModel):
    bank_code: str = Field(..., description="Paystack bank code")
    account_number: str = Field(
        ...,
        min_length=10,
        max_length=10,
        pattern=r"^\d{10}$",
        description="10-digit bank account number"
    )

    @validator("account_number")
    def validate_account(cls, v):
        if not v.isdigit():
            raise ValueError("Account number must contain only digits")
        return v

class PayoutAccountOut(BaseModel):
    bank_code: str
    account_number: str
    account_name: str
    bank_name: str
    is_verified: bool = True
    updated_at: datetime

class DeleteResponse(BaseModel):
    message: str = "Payout account removed successfully"

# ==================== Paystack Resolve Helper ====================
async def resolve_account_name(bank_code: str, account_number: str) -> dict:
    url = "https://api.paystack.co/bank/resolve"
    headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
    params = {"account_number": account_number, "bank_code": bank_code}

    async with httpx.AsyncClient(timeout=12.0) as client:
        try:
            resp = await client.get(url, headers=headers, params=params)
            data = resp.json()
            if resp.status_code == 200 and data.get("status"):
                return {
                    "account_name": data["data"]["account_name"],
                    "bank_name": data["data"].get("bank_name", "Unknown Bank")
                }
            else:
                msg = data.get("message", "Invalid account or bank")
                raise HTTPException(status_code=400, detail=msg)
        except httpx.RequestError as e:
            logger.error(f"Paystack resolve failed: {e}")
            raise HTTPException(status_code=502, detail="Bank verification temporarily unavailable")

# ==================== ROUTES ====================

# ------------------- Payout Account -------------------
@router.post("/account", response_model=PayoutAccountOut)
async def save_payout_account(payload: PayoutAccountIn, current_user: User = Depends(get_current_user)):
    user_id = current_user.id
    user_ref = db.collection("users").document(user_id)
    user_doc = user_ref.get()
    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="User not found")

    resolved = await resolve_account_name(payload.bank_code, payload.account_number)
    update_data = {
        "payout_bank": payload.bank_code,
        "payout_account_number": payload.account_number,
        "payout_account_name": resolved["account_name"],
        "payout_bank_name": resolved["bank_name"],
        "updated_at": datetime.now(timezone.utc)
    }
    user_ref.update(update_data)
    logger.info(f"Payout account updated for {user_id}: {resolved['account_name']}")
    return PayoutAccountOut(bank_code=payload.bank_code, account_number=payload.account_number,
                            account_name=resolved["account_name"], bank_name=resolved["bank_name"],
                            updated_at=datetime.now(timezone.utc))

@router.get("/account", response_model=Optional[PayoutAccountOut])
async def get_payout_account(current_user: User = Depends(get_current_user)):
    doc = db.collection("users").document(current_user.id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="User not found")
    data = doc.to_dict()
    if not data.get("payout_account_number"):
        return None
    return PayoutAccountOut(
        bank_code=data.get("payout_bank", ""),
        account_number=data.get("payout_account_number", ""),
        account_name=data.get("payout_account_name", ""),
        bank_name=data.get("payout_bank_name", "Unknown Bank"),
        updated_at=data.get("updated_at", datetime.now(timezone.utc))
    )


@router.delete("/account", response_model=DeleteResponse)
async def remove_payout_account(current_user: User = Depends(get_current_user)):
    ref = db.collection("users").document(current_user.id)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="User not found")
    if not doc.to_dict().get("payout_account_number"):
        raise HTTPException(status_code=400, detail="No payout account to remove")
    ref.update({
        "payout_bank": firestore.DELETE_FIELD,
        "payout_account_number": firestore.DELETE_FIELD,
        "payout_account_name": firestore.DELETE_FIELD,
        "payout_bank_name": firestore.DELETE_FIELD,
        "updated_at": datetime.now(timezone.utc)
    })
    logger.info(f"Payout account removed for {current_user.id}")
    return DeleteResponse()

@router.get("/banks")
async def get_banks():
    url = "https://api.paystack.co/bank"
    headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        data = resp.json()
        if data.get("status"):
            return {"banks": data["data"]}
        raise HTTPException(status_code=502, detail="Failed to load banks")

@router.get("/resolve")
async def resolve_payout_account(bank: str, account: str, current_user: User = Depends(get_current_user)):
    if len(account) != 10 or not account.isdigit():
        raise HTTPException(status_code=400, detail="Invalid account number")
    resolved = await resolve_account_name(bank, account)
    return {"account_name": resolved["account_name"], "bank_name": resolved.get("bank_name", "Unknown Bank")}

# ------------------- Earnings & History -------------------
@router.get("/earnings")
async def earnings(current_user: User = Depends(get_current_user)):
    user_id = current_user.id
    total_earnings = 0
    available_for_payout = 0

    # Paylink transactions
    paylink_docs = db.collection("paylink_transactions").where("user_id", "==", user_id).stream()
    for doc in paylink_docs:
        d = doc.to_dict()
        if d.get("status") == "success":
            amt = d.get("amount_paid", d.get("amount", 0))
            total_earnings += amt
            if d.get("payout_status") in ["pending", "ready"]:
                available_for_payout += amt

    # Invoice payments
    invoice_docs = db.collection("invoices").where("sender_id", "==", user_id).where("status", "==", "paid").stream()
    for doc in invoice_docs:
        d = doc.to_dict()
        amt = d.get("amount", 0)
        total_earnings += amt
        if d.get("payout_status") in ["pending", "ready", None]:
            available_for_payout += amt

    next_payout_date = datetime.now(timezone.utc)  # Replace with real schedule logic
    return {"total_earnings": total_earnings, "available_for_payout": available_for_payout,
            "next_payout_date": next_payout_date.isoformat()}

@router.get("/history")
async def payout_history(current_user: User = Depends(get_current_user)):
    user_id = current_user.id
    payouts_ref = db.collection("payouts").where("user_id", "==", user_id)\
        .order_by("paid_at", direction=firestore.Query.DESCENDING).limit(10)
    docs = payouts_ref.stream()
    history = []
    for doc in docs:
        d = doc.to_dict()
        history.append({
            "amount": d.get("amount", 0),
            "status": d.get("status", "pending"),
            "type": d.get("type", "unknown"),
            "reference": d.get("reference"),
            "created_at": d.get("paid_at").isoformat() if d.get("paid_at") else None
        })
    return {"history": history}

# ------------------- Helper: Queue Payout -------------------


async def queue_payout(user_id: str, amount: float, reference: str, payout_type: str = "paylink"):
    """
    Queue a payout for a user (Paylink or Invoice).
    Only enqueues via Celery; does NOT trigger direct async payout.
    """
    # Reference in 'payouts' collection
    payout_ref = db.collection("payouts").document(reference)
    if payout_ref.get().exists:
        logger.info(f"Payout already queued: {reference}")
        return

    # Create payout entry
    payout_entry = {
        "user_id": user_id,
        "reference": reference,
        "amount": amount,
        "type": payout_type,
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
        "paid_at": None
    }
    payout_ref.set(payout_entry)
    logger.info(f"Payout queued → {reference} | ₦{amount:,.0f}")

    # Update source transaction status
    if payout_type == "paylink":
        try:
            db.collection("paylink_transactions").document(reference).update({"payout_status": "pending"})
        except Exception as e:
            logger.warning(f"Failed to update paylink transaction {reference}: {e}")
    elif payout_type == "invoice":
        try:
            db.collection("invoices").document(reference).update({"payout_status": "pending"})
        except Exception as e:
            logger.warning(f"Failed to update invoice {reference}: {e}")

    # Enqueue payout in Celery
    try:
        payout_task.delay(user_id, amount, reference)
        logger.info(f"Celery payout task enqueued → {reference}")
    except Exception as e:
        logger.error(f"Failed to enqueue payout task for {reference}: {e}", exc_info=True)


@router.get("/transaction/{reference}/payout_status")
async def get_payout_status(reference: str):
    # Check the central payouts collection first
    doc = db.collection("payouts").document(reference).get()
    
    if not doc.exists:
        # Fallback to check paylink_transactions if not in payouts yet
        doc = db.collection("paylink_transactions").document(reference).get()
        
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Transaction not found")
        
    data = doc.to_dict()
    # Return 'status' (from payouts) or 'payout_status' (from paylinks)
    return {"payout_status": data.get("status") or data.get("payout_status", "pending")}