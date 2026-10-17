
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
from app.services.subscription_webhooks import handle_subscription_event


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
    link: str = "/dashboard",
):
    notif = {
        "user_id": user_id,
        "title": title,
        "message": message,
        "type": type,
        "link": link,
        "read": False,
        "created_at": datetime.now(timezone.utc),
    }

    db.collection("notifications").add(notif)


# ========================================
# PAYSTACK WEBHOOK — SUBACCOUNT OPTIMIZED
# ========================================
@router.post("/paystack", status_code=status.HTTP_200_OK)
async def paystack_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):
    body = await request.body()
    signature = request.headers.get("x-paystack-signature")

    # 1. Validate Paystack's HMAC SHA512 signature.
    if not signature or not hmac.compare_digest(
        hmac.new(
            settings.PAYSTACK_SECRET_KEY.encode(),
            body,
            hashlib.sha512,
        ).hexdigest(),
        signature,
    ):
        logger.warning("Invalid Paystack webhook signature")
        raise HTTPException(
            status_code=400,
            detail="Invalid signature",
        )

    # 2. Parse the JSON payload.
    try:
        event_data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.error("Invalid JSON in Paystack webhook")
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON",
        )

    if not isinstance(event_data, dict):
        raise HTTPException(
            status_code=400,
            detail="Invalid webhook payload",
        )

    event = event_data.get("event")
    data = event_data.get("data", {}) or {}

    if not isinstance(data, dict):
        raise HTTPException(
            status_code=400,
            detail="Invalid event data",
        )

    metadata = data.get("metadata", {}) or {}

    # 3. Process subscriptions before generic payment handling.
    if handle_subscription_event(event, data):
        return {"status": "success"}

    # ========================================
    # 4. HANDLE ORDINARY CHARGE EVENTS
    # ========================================
    if event in ("charge.success", "charge.failed"):
        ref = data.get("reference")

        if not ref:
            return {"status": "ignored"}

        # Idempotency guard for ordinary payment records.
        payment_doc_ref = db.collection("payments").document(ref)
        existing_payment = payment_doc_ref.get()

        if (
            existing_payment.exists
            and existing_payment.to_dict().get("status") == "success"
        ):
            logger.info(
                "Webhook already processed for %s",
                ref,
            )
            return {"status": "already_done"}

        amount_total_kobo = data.get("amount", 0)
        amount_total = amount_total_kobo / 100

        status_str = (
            "success"
            if event == "charge.success"
            else "failed"
        )

        user_id = metadata.get("user_id")
        paylink_id = metadata.get("paylink_id")
        invoice_id = metadata.get("invoice_id")

        if not user_id:
            logger.warning(
                "Webhook missing user_id: %s",
                ref,
            )
            return {"status": "ignored"}

        # ----------------------------------------
        # SUBACCOUNT SPLIT LOGIC
        # ----------------------------------------
        subaccount_data = data.get("subaccount") or {}
        user_share = amount_total

        if subaccount_data:
            user_share_kobo = subaccount_data.get(
                "amount",
                amount_total_kobo,
            )
            user_share = user_share_kobo / 100

        customer = data.get("customer") or {}

        payer_email = (
            customer.get("email")
            or metadata.get("payer_email")
            or "client@payla.ng"
        )
        payer_name = metadata.get("payer_name", "Anonymous")
        payer_phone = metadata.get("payer_phone", "")

        amount_str = f"₦{user_share:,.2f}"

        # ----------------------------------------
        # SAVE PAYMENT RECORD
        # ----------------------------------------
        payment = Payment(
            _id=ref,
            user_id=user_id,
            invoice_id=invoice_id or None,
            paylink_id=paylink_id or None,
            paystack_reference=ref,
            amount=amount_total,
            user_share=user_share,
            currency="NGN",
            status=status_str,
            channel=data.get("channel"),
            client_phone=payer_phone,
            fee_payer="client",
            paid_at=(
                datetime.now(timezone.utc)
                if status_str == "success"
                else None
            ),
            created_at=datetime.now(timezone.utc),
            raw_event=event_data,
        )

        # ========================================
        # SUCCESS — ATOMIC SUBACCOUNT UPDATES
        # ========================================
        if status_str == "success":
            logger.info(
                "Subaccount payment SUCCESS: %s | User share: %s",
                ref,
                amount_str,
            )

            batch = db.batch()

            # 1. Record the payment.
            batch.set(
                payment_doc_ref,
                payment.dict(by_alias=True),
            )

            # 2. Update lifetime user earnings.
            user_ref = db.collection("users").document(user_id)

            batch.update(user_ref, {
                "total_earned": firestore.Increment(user_share),
                "updated_at": datetime.now(timezone.utc),
            })

            # 3. Handle Paylink updates.
            if paylink_id:
                pt_ref = db.collection(
                    "paylink_transactions"
                ).document(ref)

                batch.update(pt_ref, {
                    "amount_paid": user_share,
                    "status": "success",
                    "paid_at": datetime.now(timezone.utc),
                })

                pl_ref = db.collection("paylinks").document(paylink_id)

                batch.update(pl_ref, {
                    "total_received": firestore.Increment(user_share),
                    "total_transactions": firestore.Increment(1),
                    "last_payment_at": datetime.now(timezone.utc),
                })

            # 4. Handle invoice updates.
            elif invoice_id:
                inv_ref = db.collection(
                    "invoices"
                ).document(invoice_id)

                batch.update(inv_ref, {
                    "status": "paid",
                    "paid_at": datetime.now(timezone.utc),
                    "paystack_reference": ref,
                })

            batch.commit()

            # Notifications.
            create_notification(
                user_id=user_id,
                title="Payment Received!",
                message=(
                    f"{amount_str} from {payer_name}\n"
                    "Settlement is being processed to your bank account."
                ),
                type="payment",
                link="/dashboard/payments",
            )

            # Paystack handles settlement through subaccounts.
            # No manual payout task is triggered here.

        # ========================================
        # FAILURE
        # ========================================
        else:
            logger.warning(
                "Payment FAILED: %s",
                ref,
            )

            payment_doc_ref.set(
                payment.dict(by_alias=True)
            )

            create_notification(
                user_id=user_id,
                title="Payment Attempt Failed",
                message=(
                    f"A client tried to pay {amount_str}, "
                    "but the payment failed."
                ),
                type="warning",
            )

    # Subscription events are handled exclusively by
    # app.services.subscription_webhooks.

    return {"status": "success"}
