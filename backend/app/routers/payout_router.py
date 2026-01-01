## routers/payout.py → FULLY INTEGRATED SUBACCOUNT VERSION
import asyncio
import logging
import httpx
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, validator
from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.auth import get_current_user
from app.models.user_model import User
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
    subaccount_code: Optional[str] = None
    is_verified: bool = True
    updated_at: datetime

class DeleteResponse(BaseModel):
    message: str = "Payout account removed successfully"

# ==================== Paystack Helpers ====================

async def resolve_account_name(bank_code: str, account_number: str) -> dict:
    url = "https://api.paystack.co/bank/resolve"
    headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
    params = {"account_number": account_number, "bank_code": bank_code}

    async with httpx.AsyncClient(timeout=12.0) as client:
        try:
            resp = await client.get(url, headers=headers, params=params)
            data = resp.json()
            
            if resp.status_code == 200 and data.get("status"):
                account_name = data["data"]["account_name"]
                # Paystack sometimes doesn't return bank_name in the resolve endpoint
                bank_name = data["data"].get("bank_name")
                
                # FALLBACK: If bank_name is missing, fetch the bank list to find the name
                if not bank_name:
                    banks_resp = await client.get("https://api.paystack.co/bank", headers=headers)
                    if banks_resp.status_code == 200:
                        all_banks = banks_resp.json().get("data", [])
                        # Match the bank_code to get the name
                        matched_bank = next((b for b in all_banks if b["code"] == bank_code), None)
                        if matched_bank:
                            bank_name = matched_bank["name"]

                return {
                    "account_name": account_name,
                    "bank_name": bank_name or "Unknown Bank"
                }
            
            msg = data.get("message", "Invalid account or bank")
            raise HTTPException(status_code=400, detail=msg)
        except httpx.RequestError as e:
            logger.error(f"Paystack resolve failed: {e}")
            raise HTTPException(status_code=502, detail="Bank verification unavailable")

async def create_or_update_subaccount(user: User, bank_code: str, account_number: str) -> str:
    """Creates/Updates a subaccount on Paystack for automated splitting (T+1 payouts)."""
    url = "https://api.paystack.co/subaccount"
    headers = {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "business_name": user.business_name or f"Merchant_{user.id[-6:]}",
        "settlement_bank": bank_code,
        "account_number": account_number,
        "percentage_charge": 0,  # Payla takes 0%; user gets full amount minus Paystack fees
        "description": f"Payla Merchant: {user.email}"
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        # If user already has a subaccount, we UPDATE it
        sub_code = getattr(user, "paystack_subaccount_code", None)
        
        if sub_code:
            resp = await client.put(f"{url}/{sub_code}", json=payload, headers=headers)
        else:
            resp = await client.post(url, json=payload, headers=headers)
        
        data = resp.json()
        if resp.status_code in [200, 201] and data.get("status"):
            return data["data"]["subaccount_code"]
        
        logger.error(f"Paystack Subaccount operation failed: {data}")
        raise HTTPException(status_code=500, detail="Provider failed to register bank account")

# ==================== ROUTES ====================

@router.post("/account", response_model=PayoutAccountOut)
async def save_payout_account(payload: PayoutAccountIn, current_user: User = Depends(get_current_user)):
    user_id = current_user.id
    
    # 1. Resolve Bank Info (Now with improved bank name matching)
    resolved = await resolve_account_name(payload.bank_code, payload.account_number)
    
    # 2. Register with Paystack
    subaccount_code = await create_or_update_subaccount(
        current_user, payload.bank_code, payload.account_number
    )

    # 3. Update Firestore
    now = datetime.now(timezone.utc)
    update_data = {
        "payout_bank": payload.bank_code, # Your screenshot shows "50515" (Moniepoint)
        "payout_account_number": payload.account_number,
        "payout_account_name": resolved["account_name"],
        "payout_bank_name": resolved["bank_name"], # This will now be "Moniepoint MFB"
        "paystack_subaccount_code": subaccount_code,
        "bank_verified": True,
        "payout_verified": True,
        "updated_at": now
    }
    
    db.collection("users").document(user_id).update(update_data)
    
    return PayoutAccountOut(
        bank_code=payload.bank_code,
        account_number=payload.account_number,
        account_name=resolved["account_name"],
        bank_name=resolved["bank_name"],
        subaccount_code=subaccount_code,
        updated_at=now
    )
@router.get("/account", response_model=Optional[PayoutAccountOut])
async def get_payout_account(current_user: User = Depends(get_current_user)):
    doc = db.collection("users").document(current_user.id).get()
    if not doc.exists: return None
    
    data = doc.to_dict()
    if not data.get("payout_account_number"): return None
    
    return PayoutAccountOut(
        bank_code=data.get("payout_bank", ""),
        account_number=data.get("payout_account_number", ""),
        account_name=data.get("payout_account_name", ""),
        bank_name=data.get("payout_bank_name", "Unknown Bank"),
        subaccount_code=data.get("paystack_subaccount_code"),
        updated_at=data.get("updated_at", datetime.now(timezone.utc))
    )

@router.delete("/account", response_model=DeleteResponse)
async def remove_payout_account(current_user: User = Depends(get_current_user)):
    ref = db.collection("users").document(current_user.id)
    # We remove the bank info but keep subaccount_code in history (optional)
    ref.update({
        "payout_bank": firestore.DELETE_FIELD,
        "payout_account_number": firestore.DELETE_FIELD,
        "payout_account_name": firestore.DELETE_FIELD,
        "payout_bank_name": firestore.DELETE_FIELD,
        "bank_verified": False,
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


@router.get("/earnings")
async def earnings(current_user: User = Depends(get_current_user)):
    # Total earned is what Paystack has split to the subaccount
    total_earned = getattr(current_user, "total_earned", 0.0)
    
    return {
        "total_earnings": total_earned, 
        "available_for_payout": total_earned, # Send as float to fix NaN
        "display_available": "Automated (T+1)",
        "payout_method": "Subaccount Transfer",
        "next_payout": "Next working day",
        "is_automated": True
    }

@router.get("/history")
async def payout_history(current_user: User = Depends(get_current_user)):
    user_id = current_user.id
    payouts_ref = db.collection("payouts")\
        .where(filter=FieldFilter("user_id", "==", user_id))\
        .order_by("created_at", direction=firestore.Query.DESCENDING)\
        .limit(20)
    
    docs = payouts_ref.stream()
    history = []
    for doc in docs:
        d = doc.to_dict()
        history.append({
            "amount": d.get("amount", 0),
            "status": d.get("status", "settled"),
            "type": d.get("type", "automated"),
            "reference": d.get("reference"),
            "created_at": d.get("created_at").isoformat() if d.get("created_at") else None
        })
    return {"history": history}

# ------------------- Helpers & Payout Status -------------------

# ------------------- Updated queue_payout Helper -------------------

async def queue_payout(
    user_id: str, 
    amount: float, 
    reference: str, 
    payout_type: str = "paylink", 
    manual_payout: bool = False
):
    """
    Handles the recording and/or initiation of a payout.
    - manual_payout=False: Used for Subaccount splits (Log only).
    - manual_payout=True: Used for legacy flows (Initiate Paystack Transfer).
    """
    payout_ref = db.collection("payouts").document(reference)
    if payout_ref.get().exists:
        return

    now = datetime.now(timezone.utc)
    
    # 1. Prepare the record for the User Dashboard
    payout_entry = {
        "user_id": user_id,
        "reference": reference,
        "amount": amount,
        "type": payout_type,
        "status": "settled" if not manual_payout else "pending",
        "created_at": now,
        "paid_at": now if not manual_payout else None,
        "is_automated": not manual_payout
    }
    
    # 2. IF MANUAL: This is where you'd call the Paystack Transfer API
    if manual_payout:
        # Note: You would implement your legacy httpx.post("https://api.paystack.co/transfer") here
        # For now, we just mark it as pending for manual review
        logger.info(f"🚨 Manual payout required for reference: {reference}")
        payout_entry["status"] = "pending_manual"
    else:
        # IF AUTOMATED: Just increment the user's total earnings in Firestore
        try:
            user_ref = db.collection("users").document(user_id)
            user_ref.update({"total_earned": firestore.Increment(amount)})
        except Exception as e:
            logger.error(f"Failed to increment total_earned for {user_id}: {e}")

    # 3. Save to history
    payout_ref.set(payout_entry)
    
    # 4. Update the source document (Invoice or Paylink)
    source_coll = "invoices" if payout_type == "invoice" else "paylink_transactions"
    try:
        db.collection(source_coll).document(reference).update({
            "payout_status": "settled_by_paystack" if not manual_payout else "payout_pending"
        })
    except Exception as e:
        logger.warning(f"Could not update source doc payout_status: {e}")

    logger.info(f"💰 Payout {'logged' if not manual_payout else 'queued'} for {user_id}: {amount}")

@router.get("/transaction/{reference}/payout_status")
async def get_payout_status(reference: str):
    # 1. Check the central payouts collection first
    doc = db.collection("payouts").document(reference).get()
    
    if doc.exists:
        data = doc.to_dict()
        return {"payout_status": data.get("status", "settled")}
        
    # 2. Fallback to check paylink_transactions if not in payouts history yet
    tx_doc = db.collection("paylink_transactions").document(reference).get()
    if tx_doc.exists:
        data = tx_doc.to_dict()
        return {"payout_status": data.get("payout_status", "processing")}
        
    # 3. Final fallback for Invoices
    inv_doc = db.collection("invoices").where("transaction_reference", "==", reference).limit(1).get()
    if inv_doc:
        data = inv_doc[0].to_dict()
        return {"payout_status": data.get("payout_status", "processing")}

    return {"payout_status": "processing"}