from fastapi import APIRouter, Request, Header, HTTPException
from firebase_admin import firestore
import hmac
import hashlib
import logging
from app.core.config import settings
from datetime import datetime, timezone, timedelta
# Import the queue_payout helper
from app.routers.payout_router import queue_payout 

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
logger = logging.getLogger("payla")
db = firestore.client()

@router.post("/paystack")
async def paystack_webhook(
    request: Request, 
    x_paystack_signature: str = Header(None)
):
    # 1. Security Verification (HMAC SHA512)
    payload = await request.body()
    if not x_paystack_signature:
        raise HTTPException(status_code=401, detail="Missing signature")

    secret = settings.PAYSTACK_SECRET_KEY.encode('utf-8')
    computed_hmac = hmac.new(secret, payload, hashlib.sha512).hexdigest()

    if computed_hmac != x_paystack_signature:
        logger.warning("🚨 Invalid webhook signature received!")
        raise HTTPException(status_code=401, detail="Invalid signature")

    data = await request.json()
    event = data.get("event")
    event_data = data.get("data", {})
    reference = event_data.get("reference")
    metadata = event_data.get("metadata", {}) or {}

    if not reference:
        return {"status": "ignored", "reason": "no_reference"}

    # Determine if this was an automated split payment via Subaccount
    # If subaccount exists in event_data, Paystack handles the payout automatically.
    is_automated = event_data.get("subaccount") is not None
    payout_status = "settled_by_paystack" if is_automated else "pending_manual"

    # --- CASE A: CHARGE SUCCESS ---
    if event == "charge.success":
        # Get the original amount from metadata if available (the amount before fees were added)
        # Fallback to the actual paid amount / 100 if not provided
        amount_paid = event_data.get("amount", 0) / 100 
        original_amount = metadata.get("original_amount", amount_paid)
        
        user_id = metadata.get("user_id")
        now = datetime.now(timezone.utc)

        # A1. Handle Invoice Payments
        invoice_id = metadata.get("invoice_id")
        if invoice_id:
            inv_ref = db.collection("invoices").document(invoice_id)
            inv_doc = inv_ref.get()
            
            if inv_doc.exists:
                current_data = inv_doc.to_dict()
                if current_data.get("status") != "paid":
                    inv_ref.update({
                        "status": "paid",
                        "paid_at": now,
                        "updated_at": now,
                        "transaction_reference": reference,
                        "payout_status": payout_status,
                        "payer_email": event_data.get("customer", {}).get("email"),
                        "payment_channel": event_data.get("channel"),
                        "fees_covered_by_client": is_automated
                    })
                    logger.info(f"✅ Invoice {invoice_id} processed. Automated: {is_automated}")
                    
                    if user_id:
                        # Pass manual_payout=False so queue_payout doesn't trigger a transfer
                        await queue_payout(
                            user_id, 
                            original_amount, 
                            reference, 
                            payout_type="invoice", 
                            manual_payout=(not is_automated)
                        )
                else:
                    logger.info(f"ℹ️ Invoice {invoice_id} already marked as paid.")

        # A2. Handle Paylink Transactions
        elif metadata.get("type") == "paylink":
            tx_ref = db.collection("paylink_transactions").document(reference)
            tx_doc = tx_ref.get()
            
            if not tx_doc.exists or tx_doc.to_dict().get("status") != "success":
                tx_ref.set({
                    "status": "success",
                    "paid_at": now,
                    "payout_status": payout_status,
                    "user_id": user_id,
                    "amount": original_amount,
                    "total_collected": amount_paid, # Amount including fees
                    "customer_email": event_data.get("customer", {}).get("email"),
                    "channel": event_data.get("channel")
                }, merge=True)
                
                logger.info(f"✅ Paylink transaction {reference} processed. Automated: {is_automated}")
                if user_id:
                    await queue_payout(
                        user_id, 
                        original_amount, 
                        reference, 
                        payout_type="paylink", 
                        manual_payout=(not is_automated)
                    )
            else:
                logger.info(f"ℹ️ Paylink {reference} already successful.")

        # A3. Handle Subscription Payments (Main Account Only)
        elif metadata.get("type") in ["subscription_initial", "silver_plan"] or "plan_code" in metadata:
            billing_cycle = metadata.get("billing_cycle", "monthly")
            
            if user_id:
                days_to_add = 365 if billing_cycle == "yearly" else 30
                new_expiry = now + timedelta(days=days_to_add)
                
                user_ref = db.collection("users").document(user_id)
                user_ref.update({
                    "plan": "silver",
                    "is_active": True,
                    "subscription_end": new_expiry,
                    "billing_cycle": billing_cycle,
                    "updated_at": now
                })
                db.collection("pending_subscriptions").document(reference).delete()
                logger.info(f"💳 Subscription activated for user {user_id}")

    # --- CASE B: MANUAL TRANSFERS (Legacy/Direct) ---
    elif event == "transfer.success":
        payout_ref = db.collection("payouts").document(reference)
        if payout_ref.get().exists:
            payout_ref.update({
                "status": "success",
                "completed_at": datetime.now(timezone.utc)
            })
            logger.info(f"💰 Manual Transfer Confirmed: {reference}")

    # --- CASE C: FAILED PAYMENTS ---
    elif event == "charge.failed":
        logger.error(f"❌ Payment failed for reference {reference}: {event_data.get('gateway_response')}")

    return {"status": "success"}