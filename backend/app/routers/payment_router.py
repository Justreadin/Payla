## routers/payment_router.py → FINAL ELITE 2025 (SUBACCOUNT EDITION)
from fastapi import APIRouter, Request, HTTPException, status, BackgroundTasks
from datetime import datetime, timezone
import hmac
import hashlib
import json
import logging
import asyncio

from app.core.firebase import db
from app.models.payment_model import Payment
from app.core.config import settings
from google.cloud import firestore

from app.routers.subscription_router import PLANS

router = APIRouter(prefix="/webhook", tags=["Webhook"])
logger = logging.getLogger("payla")

# ========================================
# LAYLA'S VOICE — NOTIFICATIONS
# ========================================
def create_notification(
    user_id: str,
    title: str,
    message: str,
    type: str = "info",
    link: str = "/dashboard"
):
    notif = {
        "user_id": user_id,
        "title": title,
        "message": message,
        "type": type,
        "link": link,
        "read": False,
        "created_at": datetime.now(timezone.utc)
    }
    db.collection("notifications").add(notif)


# ========================================
# PAYSTACK WEBHOOK — SUBACCOUNT OPTIMIZED
# ========================================
@router.post("/paystack", status_code=status.HTTP_200_OK)
async def paystack_webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()
    signature = request.headers.get("x-paystack-signature")

    # === 1. Validate Signature ===
    if not signature or not hmac.compare_digest(
        hmac.new(settings.PAYSTACK_SECRET_KEY.encode(), body, hashlib.sha512).hexdigest(),
        signature
    ):
        logger.warning("Invalid Paystack webhook signature")
        raise HTTPException(400, "Invalid signature")

    try:
        event_data = json.loads(body)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in Paystack webhook")
        raise HTTPException(400, "Invalid JSON")

    event = event_data.get("event")
    data = event_data.get("data", {})
    metadata = data.get("metadata", {})

    # ========================================
    # 2. Handle Charge Events (Split Payments)
    # ========================================
    if event in ("charge.success", "charge.failed"):
        ref = data.get("reference")
        if not ref:
            return {"status": "ignored"}

        # --- 🛑 2025 IDEMPOTENCY GUARD ---
        payment_doc_ref = db.collection("payments").document(ref)
        existing_payment = payment_doc_ref.get()
        if existing_payment.exists and existing_payment.to_dict().get("status") == "success":
            logger.info(f"♻️ Webhook already processed for {ref}")
            return {"status": "already_done"}

        amount_total_kobo = data.get("amount", 0)
        amount_total = amount_total_kobo / 100
        status_str = "success" if event == "charge.success" else "failed"

        user_id = metadata.get("user_id")
        paylink_id = metadata.get("paylink_id")
        invoice_id = metadata.get("invoice_id")

        if not user_id:
            logger.warning(f"Webhook missing user_id: {ref}")
            return {"status": "ignored"}

        # --- 💸 SUBACCOUNT SPLIT LOGIC ---
        # We extract how much went to the user (subaccount) vs how much we kept (fees)
        subaccount_data = data.get("subaccount", {})
        user_share = amount_total # Default to total if no split
        
        if subaccount_data:
            # If split happened, Paystack provides the subaccount share
            # Note: Paystack 'amount' in the subaccount object is usually the share
            user_share_kobo = subaccount_data.get("amount", amount_total_kobo)
            user_share = user_share_kobo / 100

        customer = data.get("customer", {})
        payer_email = customer.get("email") or metadata.get("payer_email", "client@payla.ng")
        payer_name = metadata.get("payer_name", "Anonymous")
        payer_phone = metadata.get("payer_phone", "")

        amount_str = f"₦{user_share:,.2f}"

        # === Save Payment Record ===
        payment = Payment(
            _id=ref,
            user_id=user_id,
            invoice_id=invoice_id or None,
            paylink_id=paylink_id or None,
            paystack_reference=ref,
            amount=amount_total,         # Total paid by client
            user_share=user_share,       # What user actually gets
            currency="NGN",
            status=status_str,
            channel=data.get("channel"),
            client_phone=payer_phone,
            fee_payer="client",
            paid_at=datetime.now(timezone.utc) if status_str == "success" else None,
            created_at=datetime.now(timezone.utc),
            raw_event=event_data
        )

        # ========================================
        # SUCCESS → ATOMIC SUBACCOUNT UPDATES
        # ========================================
        if status_str == "success":
            logger.info(f"✅ Subaccount Payment SUCCESS → {ref} | User Share: {amount_str}")

            batch = db.batch()
            
            # 1. Record the Payment
            batch.set(payment_doc_ref, payment.dict(by_alias=True))

            # 2. Update User Earnings (This represents their lifetime revenue)
            user_ref = db.collection("users").document(user_id)
            batch.update(user_ref, {
                "total_earned": firestore.Increment(user_share),
                "updated_at": datetime.now(timezone.utc)
            })

            # 3. Handle Paylink Updates
            if paylink_id:
                pt_ref = db.collection("paylink_transactions").document(ref)
                batch.update(pt_ref, {
                    "amount_paid": user_share,
                    "status": "success",
                    "paid_at": datetime.now(timezone.utc)
                })
                pl_ref = db.collection("paylinks").document(paylink_id)
                batch.update(pl_ref, {
                    "total_received": firestore.Increment(user_share),
                    "total_transactions": firestore.Increment(1),
                    "last_payment_at": datetime.now(timezone.utc)
                })
            
            # 4. Handle Invoice Updates
            elif invoice_id:
                inv_ref = db.collection("invoices").document(invoice_id)
                batch.update(inv_ref, {
                    "status": "paid",
                    "paid_at": datetime.now(timezone.utc),
                    "paystack_reference": ref
                })

            batch.commit()

            # --- 🔔 NOTIFICATIONS ---
            create_notification(
                user_id=user_id,
                title="Payment Received!",
                message=f"{amount_str} from {payer_name}\nSettlement is being processed to your bank account.",
                type="payment",
                link="/dashboard/payments"
            )

            # NOTE: With Subaccounts, Paystack handles the payout automatically (T+1).
            # We no longer trigger a manual Celery payout task unless you have a secondary logic.

        # ========================================
        # FAILURE
        # ========================================
        else:
            logger.warning(f"❌ Payment FAILED → {ref}")
            payment_doc_ref.set(payment.dict(by_alias=True))
            create_notification(
                user_id=user_id,
                title="Payment Attempt Failed",
                message=f"A client tried to pay {amount_str} but it failed.",
                type="warning"
            )

    # ========================================
    # 3. PAYLA SUBSCRIPTIONS (Main Account)
    # ========================================
    elif event == "subscription.create":
        sub_code = data["subscription_code"]
        customer_code = data["customer"]["customer_code"]
        user_id = metadata.get("user_id")
        plan_code = metadata.get("plan_code")

        if not user_id or not plan_code:
            return {"status": "ignored"}

        interval = "monthly" if "monthly" in plan_code else "yearly"
        next_bill = data["next_payment_date"]

        db.collection("users").document(user_id).update({
            "plan": "silver",
            "billing_cycle": interval,
            "subscription_id": sub_code,
            "paystack_customer_code": customer_code,
            "next_billing_date": next_bill,
            "trial_end_date": None,
            "upgraded_at": datetime.now(timezone.utc),
            "billing_nudge_status": "active"
        })

        create_notification(
            user_id=user_id,
            title="Welcome to Payla Silver!",
            message=f"You’re now on {PLANS.get(plan_code, {}).get('description', 'Silver Plan')}",
            type="success"
        )

    elif event == "charge.success" and data.get("subscription"):
        user_id = metadata.get("user_id")
        if user_id:
            next_bill = data["subscription"].get("next_payment_date")
            db.collection("users").document(user_id).update({
                "plan": "silver",
                "next_billing_date": next_bill
            })
            create_notification(
                user_id=user_id,
                title="Subscription Renewed",
                message=f"Your subscription was renewed successfully. Next billing: {next_bill}",
                type="info"
            )

    elif event in ("subscription.disable", "subscription.expire") \
        or (event == "charge.failed" and data.get("subscription")):
        user_id = metadata.get("user_id")
        if user_id:
            db.collection("users").document(user_id).update({
                "plan": "free",
                "subscription_id": None,
                "next_billing_date": None
            })
            create_notification(
                user_id=user_id,
                title="Subscription Expired",
                message="Your Silver access has ended. Resubscribe to continue using pro features.",
                type="warning",
                link="/subscription"
            )

    return {"status": "success"}