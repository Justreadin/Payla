## routers/payout.py → FULLY INTEGRATED SUBACCOUNT VERSION
import asyncio
import logging
import httpx
from datetime import datetime, timezone, timedelta
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

# ==================== Paystack Helpers ====================
async def create_or_update_subaccount(
    user_id: str, 
    bank_code: str, 
    account_number: str, 
    payout_account_name: str
) -> str:
    """Creates/Updates Paystack subaccount using only the bank-verified account name."""
    url = "https://api.paystack.co/subaccount"
    headers = {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }
    
    # Check for existing subaccount code in DB to determine if we PUT or POST
    user_doc = db.collection("users").document(user_id).get()
    user_data = user_doc.to_dict() if user_doc.exists else {}
    sub_code = user_data.get("paystack_subaccount_code")

    # The payload now uses the resolved bank name for the 'business_name' field
    # strictly to satisfy Paystack's requirement for a subaccount label.
    payload = {
        "business_name": payout_account_name, 
        "settlement_bank": bank_code,
        "account_number": account_number,
        "percentage_charge": 0,
        "description": f"Payla Payouts: {user_id}"
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        if sub_code:
            # Update existing subaccount
            resp = await client.put(f"{url}/{sub_code}", json=payload, headers=headers)
        else:
            # Create new subaccount
            resp = await client.post(url, json=payload, headers=headers)
        
        data = resp.json()
        if resp.status_code in [200, 201] and data.get("status"):
            return data["data"]["subaccount_code"]
        
        logger.error(f"Paystack Subaccount Error: {data}")
        raise HTTPException(
            status_code=500, 
            detail="Could not link bank account with payment provider"
        )

# ==================== ROUTES ====================

@router.post("/account", response_model=PayoutAccountOut)
async def save_payout_account(payload: PayoutAccountIn, current_user: User = Depends(get_current_user)):
    user_id = current_user.id
    
    user_doc = db.collection("users").document(user_id).get()
    user_data = user_doc.to_dict() if user_doc.exists else {}
    
    existing_bank = user_data.get("payout_bank")
    existing_acc = user_data.get("payout_account_number")
    subaccount_code = user_data.get("paystack_subaccount_code")

    # Optimization: If details are identical, skip
    if existing_bank == payload.bank_code and existing_acc == payload.account_number and subaccount_code:
        return PayoutAccountOut(
            bank_code=user_data.get("payout_bank"),
            account_number=user_data.get("payout_account_number"),
            account_name=user_data.get("payout_account_name"),
            bank_name=user_data.get("payout_bank_name"),
            subaccount_code=subaccount_code,
            updated_at=user_data.get("updated_at", datetime.now(timezone.utc))
        )

    # 1. Resolve official bank info FIRST
    resolved = await resolve_account_name(payload.bank_code, payload.account_number)
    
    # 2. Register/Update with Paystack using the RESOLVED name
    new_subaccount_code = await create_or_update_subaccount(
        user_id, 
        payload.bank_code, 
        payload.account_number,
        resolved["account_name"] # <--- Pass the resolved name here
    )

    # 3. Update Firestore
    now = datetime.now(timezone.utc)
    update_data = {
        "payout_bank": payload.bank_code,
        "payout_account_number": payload.account_number,
        "payout_account_name": resolved["account_name"],
        "payout_bank_name": resolved["bank_name"],
        "paystack_subaccount_code": new_subaccount_code,
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
        subaccount_code=new_subaccount_code,
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
    # 1. Use the pre-calculated total from the User document
    total_earned = getattr(current_user, "total_earned", 0.0)
    
    # We use .get() or getattr() to handle cases where the field might be missing
    bank_name = getattr(current_user, "payout_bank_name", "your bank")

    return {
        "total_earnings": total_earned, 
        "available_for_payout": 0, # In T+1, everything is technically "processing"
        "display_available": "Automated (T+1)",
        "payout_method": bank_name,
        "next_payout": "Next working day",
        "is_automated": True,
        "fee_structure": "Your Clients Pay Fees"
    }

@router.get("/history")
async def payout_history(current_user: User = Depends(get_current_user)):
    user_id = current_user.id
    history = []

    # fetch only from the Payouts collection - this includes both Invoices and Paylinks now
    payout_docs = db.collection("payouts")\
        .where("user_id", "==", user_id)\
        .order_by("created_at", direction=firestore.Query.DESCENDING)\
        .limit(20).stream()

    for doc in payout_docs:
        d = doc.to_dict()
        
        # Determine a friendly description
        p_type = d.get("type", "paylink")
        description = "Invoice Payment" if p_type == "invoice" else "Paylink Payment"
        
        history.append({
            "reference": d.get("reference"),
            "amount": d.get("amount", 0),
            "status": d.get("status", "settled").capitalize(),
            "source_type": p_type,
            "created_at": d.get("created_at").isoformat() if d.get("created_at") else None,
            "description": description
        })

    # Sorting is already handled by the Firestore order_by, 
    # but we'll keep the list return format consistent
    return {"history": history, "payouts": history}


# ------------------- Helpers & Payout Status -------------------

async def queue_payout(
    user_id: str, 
    amount: float, 
    reference: str, 
    payout_type: str = "paylink", 
    manual_payout: bool = False
):
    """
    Handles recording and initiation of payouts for Subaccount splits.
    Updates unified dashboard stats for both Invoices and Paylinks.
    """
    payout_ref = db.collection("payouts").document(reference)
    
    # Avoid duplicate processing
    if payout_ref.get().exists:
        logger.info(f"ℹ️ Payout reference {reference} already exists. Skipping.")
        return

    now = datetime.now(timezone.utc)
    
    # --- T+1 Settlement Logic ---
    arrival_date = now + timedelta(days=1)
    if now.weekday() == 4: # Friday -> Monday
        arrival_date = now + timedelta(days=3)
    elif now.weekday() == 5: # Saturday -> Monday
        arrival_date = now + timedelta(days=2)

    # 1. Prepare payout record for the "Recent Payouts" list
    payout_entry = {
        "user_id": user_id,
        "reference": reference,
        "amount": amount,
        "type": payout_type, 
        "status": "settled" if not manual_payout else "pending",
        "created_at": now,
        "arrival_date": arrival_date,
        "paid_at": now if not manual_payout else None,
        "is_automated": not manual_payout
    }
    
    # 2. Prepare User Dashboard Updates
    user_ref = db.collection("users").document(user_id)
    user_updates = {
        "total_earned": firestore.Increment(amount),
        "last_payout_at": now,
        "updated_at": now
    }

    if payout_type == "invoice":
        user_updates["total_invoice_revenue"] = firestore.Increment(amount)
    else:
        user_updates["total_paylink_revenue"] = firestore.Increment(amount)

    try:
        batch = db.batch()
        
        # A. Add to Payouts Collection
        batch.set(payout_ref, payout_entry)
        
        # B. Update User Stats
        batch.update(user_ref, user_updates)
        
        # C. Update the Source Transaction (Invoice or Paylink)
        if payout_type == "invoice":
            # Search for invoice where transaction_reference matches Paystack reference
            # This is safer than document() because IDs vary
            inv_query = db.collection("invoices").where("transaction_reference", "==", reference).limit(1).get()
            
            if inv_query:
                # Update the specific invoice document found
                batch.update(inv_query[0].reference, {
                    "payout_status": "settled_by_paystack" if not manual_payout else "payout_pending",
                    "settled_at": now
                })
            else:
                # Fallback: Try document ID if query yields nothing
                batch.update(db.collection("invoices").document(reference), {
                    "payout_status": "settled_by_paystack" if not manual_payout else "payout_pending",
                    "settled_at": now
                }, merge=True)
        else:
            # For Paylinks, the reference is usually the document ID
            batch.update(db.collection("paylink_transactions").document(reference), {
                "payout_status": "settled_by_paystack" if not manual_payout else "payout_pending",
                "settled_at": now
            })
        
        batch.commit()
        logger.info(f"💰 Unified Payout Logged: {payout_type.upper()} | {user_id} | ₦{amount}")

    except Exception as e:
        logger.error(f"❌ Failed to process unified payout for {reference}: {e}")
        # Final safety fallback to at least record the payout entry
        try:
            payout_ref.set(payout_entry)
        except:
            pass


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