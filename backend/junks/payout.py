import httpx
import logging
from app.core.config import settings
from firebase_admin import firestore
from datetime import datetime, timezone
from app.routers.payment_router import create_notification

logger = logging.getLogger("payla")
db = firestore.client()

# ========================================
# HELPERS
# ========================================

def update_payout_status(reference: str, status: str):
    """Updates the payout status across collections (Paylinks or Invoices)."""
    # Try paylink first
    ref_pl = db.collection("paylink_transactions").document(reference)
    if ref_pl.get().exists:
        ref_pl.update({
            "payout_status": status,
            "last_update": datetime.now(timezone.utc)
        })
        return

    # Try invoice
    ref_inv = db.collection("invoices").document(reference)
    if ref_inv.get().exists:
        ref_inv.update({
            "payout_status": status,
            "updated_at": datetime.now(timezone.utc)
        })
        return

    logger.error(f"Payout reference not found anywhere: {reference}")


async def get_paystack_available_balance():
    """Checks the liquid 'Available Balance' in Paystack."""
    url = "https://api.paystack.co/balance"
    headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(url, headers=headers)
            data = resp.json()
            if resp.status_code == 200 and data.get("status"):
                for bal in data['data']:
                    if bal['currency'] == 'NGN':
                        return bal['balance'] / 100  # Convert Kobo to Naira
            return 0
        except Exception as e:
            logger.error(f"Balance check failed: {e}")
            return 0

# ========================================
# CORE PAYOUT TASK (WITH FLOAT LOGIC)
# ========================================

async def initiate_payout(user_id: str, amount_ngn: float, reference: str, task_instance=None):
    """
    Core payout logic. Accepts task_instance to allow Celery retries
    when Paystack float is low or settlement is pending.
    """
    logger.info(f"🚀 Payout Process Started → {reference} | ₦{amount_ngn:,.0f}")
    
    if reference.startswith("draft_"):
        return

    try:
        # 1. Check User & Business Eligibility
        user_doc = db.collection("users").document(user_id).get()
        if not user_doc.exists:
            logger.error(f"User not found: {user_id}")
            return
        
        user = user_doc.to_dict()
        if user.get("business_type") == "starter":
            update_payout_status(reference, "blocked")
            create_notification(user_id, "Payout Blocked", "Starter businesses cannot withdraw. Please upgrade.", type="error")
            return

        # 2. Check for Payout Details
        account_name = user.get("payout_account_name")
        account_number = user.get("payout_account_number")
        bank_code = user.get("payout_bank")

        if not all([account_name, account_number, bank_code]):
            update_payout_status(reference, "failed")
            create_notification(user_id, "Payout Failed", "Incomplete bank details.", type="warning")
            return

        # 3. FLOAT CHECK (THE "SECONDS" LOGIC)
        available_float = await get_paystack_available_balance()
        
        if available_float < amount_ngn:
            logger.warning(f"⏳ FLOAT LOW (Need ₦{amount_ngn}, Have ₦{available_float}).")
            
            # Update status to 'pending_settlement' for the frontend T+1 UI
            update_payout_status(reference, "pending_settlement")
            
            if task_instance:
                logger.info(f"Retrying {reference} in 4 hours...")
                raise task_instance.retry(countdown=14400)
            return

        # 4. TRANSACTIONAL LOCK (Prevent Double Payouts)
        payout_ref = db.collection("payouts").document(reference)
        payout_snap = payout_ref.get()
        if payout_snap.exists and payout_snap.to_dict().get("status") in ["success", "processing"]:
            logger.warning(f"Payout already processed/processing: {reference}")
            return

        payout_ref.set({
            "status": "processing",
            "user_id": user_id,
            "amount": amount_ngn,
            "locked_at": datetime.now(timezone.utc)
        }, merge=True)

        # 5. RECIPIENT & TRANSFER
        recipient_code = user.get("paystack_recipient_code")
        if not recipient_code:
            recipient_code = await create_recipient(account_number, bank_code, account_name)
            if recipient_code:
                db.collection("users").document(user_id).update({"paystack_recipient_code": recipient_code})
            else:
                update_payout_status(reference, "failed")
                return

        # 6. EXECUTE INSTANT TRANSFER
        success, tr_ref, error_msg = await create_transfer(recipient_code, amount_ngn, reference)

        if success:
            payout_ref.update({
                "status": "success",
                "reference": tr_ref,
                "paid_at": datetime.now(timezone.utc)
            })
            update_payout_status(reference, "success")
            logger.info(f"✅ Instant Payout Success: {reference}")
        else:
            # If Paystack specifically says 'balance' error, retry instead of failing
            if "balance" in error_msg.lower() and task_instance:
                update_payout_status(reference, "pending_settlement")
                raise task_instance.retry(countdown=14400)
            
            logger.error(f"❌ Transfer Failed: {error_msg}")
            update_payout_status(reference, "failed")
            payout_ref.update({
                "status": "failed",
                "error": error_msg, 
                "failed_at": datetime.now(timezone.utc)
            })

    except Exception as e:
        # Re-raise Celery Retry exceptions so the worker handles them
        if "retry" in str(type(e)).lower():
            raise e
        logger.error(f"Payout exception → {reference}: {e}", exc_info=True)
        update_payout_status(reference, "failed")

# ========================================
# PAYSTACK API WRAPPERS
# ========================================

async def create_recipient(account_number: str, bank_code: str, account_name: str):
    url = "https://api.paystack.co/transferrecipient"
    payload = {
        "type": "nuban",
        "name": account_name,
        "account_number": account_number,
        "bank_code": bank_code,
        "currency": "NGN"
    }
    headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}

    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
            data = resp.json()
            if data.get("status"):
                return data["data"]["recipient_code"]
            return None
        except Exception:
            return None

async def create_transfer(recipient_code: str, amount_ngn: float, reason: str):
    url = "https://api.paystack.co/transfer"
    
    # Calculate fee logic
    if amount_ngn <= 5000: payout_fee = 10
    elif amount_ngn <= 50000: payout_fee = 25
    else: payout_fee = 50

    actual_user_money = amount_ngn - payout_fee

    payload = {
        "source": "balance",
        "amount": int(actual_user_money * 100),
        "recipient": recipient_code,
        "reason": f"Payla Instant Payout - {reason}"
    }
    headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
            data = resp.json()
            if data.get("status"):
                return True, data["data"]["reference"], ""
            return False, "", data.get("message") or "Unknown error"
        except Exception as e:
            return False, "", str(e)