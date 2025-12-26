import httpx
import logging
from app.core.config import settings
from firebase_admin import firestore
from datetime import datetime, timezone
from app.routers.payment_router import create_notification
from app.core.celery_app import celery_app

logger = logging.getLogger("payla")
db = firestore.client()


def update_payout_status(reference: str, status: str):
    # Try paylink first
    ref = db.collection("paylink_transactions").document(reference)
    if ref.get().exists:
        ref.update({
            "payout_status": status,
            "last_update": datetime.now(timezone.utc)
        })
        return

    # Try invoice
    ref = db.collection("invoices").document(reference)
    if ref.get().exists:
        ref.update({
            "payout_status": status,
            "updated_at": datetime.now(timezone.utc)
        })
        return

    logger.error(f"Payout reference not found anywhere: {reference}")

@celery_app.task
async def initiate_payout(user_id: str, amount_ngn: float, reference: str):
    logger.info(f"Attempting payout → {reference} | ₦{amount_ngn:,.0f}")
    if reference.startswith("draft_"):
        logger.info(f"Skipping payout for draft invoice: {reference}")
        return


    try:
        user_doc = db.collection("users").document(user_id).get()
        if not user_doc.exists:
            logger.error(f"User not found: {user_id}")
            return

        user = user_doc.to_dict()
        
        if user.get("business_type") == "starter":
            logger.warning("Payout blocked — starter business")
            update_payout_status(reference, "blocked")

            create_notification(
                user_id,
                title="Payout Pending Upgrade",
                message="Your payment was received, but payouts require a registered business. Upgrade to enable withdrawals."
            )
            return

        # SAFE access fields
        account_name = user.get("payout_account_name")
        account_number = user.get("payout_account_number")
        bank_code = user.get("payout_bank")

        # Ensure required fields exist
        if not account_name or not account_number or not bank_code:
            logger.error(f"Missing payout details for user {user_id}")
            
            # Mark transaction as failed
            update_payout_status(reference, "failed")
            logger.info(f"Payout {reference} marked as failed")

                # Notify user
            create_notification(
                user_id,
                title="Payout Failed",
                message="Your payout could not be processed because your bank account details are incomplete. Please update your payout settings."
            )

            return

        # Hold small payouts
        if amount_ngn < 1000:
            logger.info(f"Amount below ₦1000 → held")
            update_payout_status(reference, "held")
            return

       # --- 2025 TRANSACTIONAL LOCK ---
        payout_ref = db.collection("payouts").document(reference)
        payout_snap = payout_ref.get()
        
        # If it's already success OR currently being worked on, STOP.
        if payout_snap.exists:
            status = payout_snap.to_dict().get("status")
            if status in ["success", "processing"]:
                logger.warning(f"Payout already {status}: {reference}")
                return

        # Lock it immediately before calling Paystack
        payout_ref.set({
            "status": "processing",
            "user_id": user_id,
            "amount": amount_ngn,
            "locked_at": datetime.now(timezone.utc)
        }, merge=True)

        recipient_code = user.get("paystack_recipient_code")

        if not recipient_code:
            recipient_code = await create_recipient(
                account_number,
                bank_code,
                account_name
            )

            if recipient_code:
                db.collection("users").document(user_id).update({
                    "paystack_recipient_code": recipient_code
                })
            else:
                logger.error("Recipient creation failed.")
                update_payout_status(reference, "failed")
                logger.info(f"Payout {reference} marked as failed")
                return

        # Create transfer
        success, tr_ref, error_msg = await create_transfer(recipient_code, amount_ngn, reference)

        if success:
            db.collection("payouts").document(reference).set({
                "user_id": user_id,
                "amount": amount_ngn,
                "recipient_used": recipient_code,
                "status": "success",
                "reference": reference,
                "paid_at": datetime.now(timezone.utc)
            })

            update_payout_status(reference, "success")
            logger.info(f"Payout {reference} marked as success")
        else:
            logger.error(f"Transfer failed: {error_msg}")
            update_payout_status(reference, "failed")
            db.collection("payouts").document(reference).update({"error": error_msg, "failed_at": datetime.now(timezone.utc)})
            logger.info(f"Payout {reference} marked as failed")

    except Exception as e:
        logger.error(f"Payout failed → {reference}: {e}", exc_info=True)
        update_payout_status(reference, "failed")
        logger.info(f"Payout {reference} marked as failed")


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
            data = await resp.json()
            logger.debug(f"Recipient creation response: {data}")
            if data.get("status"):
                return data["data"]["recipient_code"]
            return None
        except Exception as e:
            logger.error(f"Recipient HTTP error: {e}")
            return None


async def create_transfer(recipient_code: str, amount_ngn: float, reason: str):
    url = "https://api.paystack.co/transfer"
    
    # 1. Identify the fee that was added by the frontend
    # (Matches your JS logic)
    if amount_ngn <= 5010: # 5000 + 10 fee
        payout_fee = 10
    elif amount_ngn <= 50025: # 50000 + 25 fee
        payout_fee = 25
    else:
        payout_fee = 50

    # 2. Subtract it so we only send the "Price" the user wanted
    actual_user_money = amount_ngn - payout_fee

    payload = {
        "source": "balance",
        "amount": int(actual_user_money * 100), # Send the 'Price', leave the 'Fee' for Paystack
        "recipient": recipient_code,
        "reason": f"Payla Instant Payout - {reason or 'No reference'}"
    }
    headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
            data = await resp.json()
            logger.debug(f"Transfer response: {data}")
            if data.get("status"):
                return True, data["data"]["reference"], ""
            return False, "", data.get("message") or "Unknown transfer error"
        except Exception as e:
            logger.error(f"Transfer HTTP error: {e}")
            return False, "", str(e)
