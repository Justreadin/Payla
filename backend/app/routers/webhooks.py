# routers/webhook_router.py
from fastapi import APIRouter, Request, Header, HTTPException
from firebase_admin import firestore
import hmac
import hashlib
import logging
from app.core.config import settings
from datetime import datetime, timezone, timedelta

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
logger = logging.getLogger("payla")
db = firestore.client()

@router.post("/paystack")
async def paystack_webhook(
    request: Request, 
    x_paystack_signature: str = Header(None)
):
    # 1. Security Verification (Critical for Production)
    payload = await request.body()
    secret = settings.PAYSTACK_SECRET_KEY.encode('utf-8')
    computed_hmac = hmac.new(secret, payload, hashlib.sha512).hexdigest()

    if computed_hmac != x_paystack_signature:
        logger.warning("Invalid webhook signature received")
        raise HTTPException(status_code=401, detail="Invalid signature")

    data = await request.json()
    event = data.get("event")
    event_data = data.get("data", {})
    reference = event_data.get("reference")
    metadata = event_data.get("metadata", {})

    if not reference:
        return {"status": "ignored"}

    # --- CASE A: CHARGE SUCCESS (Invoices OR Subscriptions) ---
    if event == "charge.success":
        
        # A1. Handle Invoice Payments
        invoice_id = metadata.get("invoice_id")
        if invoice_id:
            logger.info(f"✅ Webhook: Invoice {invoice_id} paid")
            inv_ref = db.collection("invoices").document(invoice_id)
            doc = inv_ref.get()
            
            if doc.exists and doc.to_dict().get("status") != "paid":
                now = datetime.now(timezone.utc)
                inv_ref.update({
                    "status": "paid",
                    "paid_at": now,
                    "updated_at": now,
                    "transaction_reference": reference,
                    "payer_email": event_data.get("customer", {}).get("email")
                })
                # Note: Payout logic can be triggered here via background task

        # A2. Handle Subscription Payments (Silver/Renewals)
        elif metadata.get("type") == "subscription_initial" or "plan_code" in metadata:
            user_id = metadata.get("user_id")
            plan_code = metadata.get("plan_code")
            billing_cycle = metadata.get("billing_cycle", "monthly")
            
            if user_id:
                logger.info(f"💳 Webhook: Activation for {plan_code} - User: {user_id}")
                
                # Calculate new expiry date based on plan
                # Monthly = 30 days, Yearly = 365 days
                days_to_add = 365 if billing_cycle == "yearly" else 30
                new_expiry = datetime.now(timezone.utc) + timedelta(days=days_to_add)
                
                user_ref = db.collection("users").document(user_id)
                user_ref.update({
                    "plan": "silver", # Or target plan from metadata
                    "is_active": True,
                    "subscription_end": new_expiry,
                    "billing_cycle": billing_cycle,
                    "last_payment_ref": reference,
                    "subscription_id": str(event_data.get("id")), # Paystack Trans ID
                    "billing_nudge_status": "active",  # <--- CRITICAL: Reset the nudge state
                    "last_nudge_date": None,
                    "updated_at": datetime.now(timezone.utc)
                })
                
                # Clean up the pending record to keep DB tidy
                db.collection("pending_subscriptions").document(reference).delete()

    # --- CASE B: PAYLA SENT MONEY TO A USER (Payouts) ---
    elif event == "transfer.success":
        payout_ref = db.collection("payouts").document(reference)
        
        # Run in a transaction or check state to prevent double processing
        doc = payout_ref.get()
        if doc.exists and doc.to_dict().get("status") == "processing":
            payout_ref.update({
                "status": "success",
                "completed_at": datetime.now(timezone.utc),
                "gateway_response": "Successful",
                "paystack_transfer_id": event_data.get("id")
            })
            logger.info(f"💰 Payout Confirmed: {reference}")

    elif event in ["transfer.failed", "transfer.reversed"]:
        reason = event_data.get("reason", "Bank reversal")
        logger.error(f"❌ Webhook: Payout failed for {reference} - {reason}")
        db.collection("payouts").document(reference).update({
            "status": "failed",
            "error": reason,
            "failed_at": datetime.now(timezone.utc)
        })

    return {"status": "success"}