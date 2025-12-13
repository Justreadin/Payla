import httpx
import logging
from app.core.config import settings
from firebase_admin import firestore
from datetime import datetime, timezone
from app.routers.payment_router import create_notification

logger = logging.getLogger("payla")
db = firestore.client()


async def initiate_payout(user_id: str, amount_ngn: float, reference: str):
    logger.info(f"Attempting payout → {reference} | ₦{amount_ngn:,.0f}")

    try:
        user_doc = db.collection("users").document(user_id).get()
        if not user_doc.exists:
            logger.error(f"User not found: {user_id}")
            return

        user = user_doc.to_dict()

        # SAFE access fields
        account_name = user.get("payout_account_name")
        account_number = user.get("payout_account_number")
        bank_code = user.get("payout_bank")

        # Ensure required fields exist
        if not account_name or not account_number or not bank_code:
            logger.error(f"Missing payout details for user {user_id}")
            
            # Mark transaction as failed
            db.collection("paylink_transactions").document(reference).update({
                "payout_status": "failed",
                "last_update": datetime.utcnow()
            })

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
            db.collection("paylink_transactions").document(reference).update({
                "payout_status": "held",
                "last_update": datetime.utcnow()
            })
            return

        # Resolve recipient code
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
                db.collection("paylink_transactions").document(reference).update({
                    "payout_status": "failed",
                    "last_update": datetime.utcnow()
                })
                return

        # Create transfer
        success, tr_ref, error_msg = await create_transfer(recipient_code, amount_ngn, reference)

        if success:
            db.collection("payouts").document(reference).set({
                "user_id": user_id,
                "amount": amount_ngn,
                "status": "success",
                "reference": reference,
                "paid_at": datetime.utcnow()
            })

            db.collection("paylink_transactions").document(reference).update({
                "payout_status": "success",
                "last_update": datetime.utcnow()
            })
        else:
            logger.error(f"Transfer failed: {error_msg}")
            db.collection("paylink_transactions").document(reference).update({
                "payout_status": "failed",
                "last_update": datetime.utcnow()
            })

    except Exception as e:
        logger.error(f"Payout failed → {reference}: {e}", exc_info=True)
        db.collection("paylink_transactions").document(reference).update({
            "payout_status": "failed",
            "last_update": datetime.utcnow()
        })


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
            logger.debug(f"Recipient creation response: {data}")
            if data.get("status"):
                return data["data"]["recipient_code"]
            return None
        except Exception as e:
            logger.error(f"Recipient HTTP error: {e}")
            return None


async def create_transfer(recipient_code: str, amount_ngn: float, reason: str):
    url = "https://api.paystack.co/transfer"
    payload = {
        "source": "balance",
        "amount": int(amount_ngn * 100),
        "recipient": recipient_code,
        "reason": f"Payla Instant Payout - {reason}"
    }
    headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
            data = resp.json()
            logger.debug(f"Transfer response: {data}")
            if data.get("status"):
                return True, data["data"]["reference"], ""
            return False, "", data.get("message") or "Unknown transfer error"
        except Exception as e:
            logger.error(f"Transfer HTTP error: {e}")
            return False, "", str(e)
