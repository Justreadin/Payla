# app/tasks/pending_payouts.py
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from celery import shared_task
from app.core.firebase import db
from app.tasks.payout import initiate_payout

logger = logging.getLogger("payla")


async def _run_firestore_stream(query):
    """Run Firestore .stream() in a thread to avoid blocking."""
    return await asyncio.to_thread(lambda: list(query.stream()))


async def sync_pending_paylink_transactions():
    """
    Mirror pending paylink_transactions to payments.
    Hold payouts below threshold.
    """
    logger.info("Syncing pending paylink transactions...")
    query = db.collection("paylink_transactions").where("status", "==", "pending")
    pending_docs = await _run_firestore_stream(query)

    synced_count = 0
    for doc in pending_docs:
        tx = doc.to_dict()
        ref = tx["paystack_reference"]

        payment_doc = await asyncio.to_thread(lambda: db.collection("payments").document(ref).get())
        if not payment_doc.exists:
            payment_data = {
                "_id": ref,
                "user_id": tx["user_id"],
                "paylink_id": tx.get("paylink_id"),
                "invoice_id": None,
                "paystack_reference": ref,
                "amount": tx.get("amount") or tx.get("amount_requested") or 0,
                "currency": "NGN",
                "status": "success",
                "channel": "paylink",
                "client_phone": tx.get("payer_phone", ""),
                "fee_payer": "client",
                "paid_at": datetime.now(timezone.utc),
                "created_at": tx.get("created_at", datetime.now(timezone.utc)),
                "raw_event": tx
            }
            await asyncio.to_thread(lambda: db.collection("payments").document(ref).set(payment_data))
            synced_count += 1

            if payment_data["amount"] < 1000:
                db.collection("paylink_transactions").document(ref).update({
                    "payout_status": "held",
                    "last_update": datetime.now(timezone.utc)
                })

    if synced_count > 0:
        logger.info(f"Synced {synced_count} pending paylink transactions.")


# -------------------------
# Celery Payout Task
# -------------------------
@shared_task(bind=True, max_retries=5, default_retry_delay=600)
def payout_task(self, user_id: str, amount: float, reference: str):
    """
    Celery task to initiate a payout with retries and backoff.
    """
    try:
        asyncio.run(initiate_payout(user_id, amount, reference))
        logger.info(f"Payout succeeded: {reference} → ₦{amount:,.0f} to {user_id}")
    except Exception as exc:
        logger.error(f"Payout failed: {reference}, retrying...", exc_info=True)
        raise self.retry(exc=exc)


@shared_task(bind=True)
def process_pending_payouts(self):
    """
    Main task to find pending payouts and enqueue them as Celery tasks.
    """
    async def _process():
        await sync_pending_paylink_transactions()

        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        query = db.collection("payments") \
                  .where("status", "==", "success") \
                  .where("paid_at", ">=", cutoff)
        payment_docs = await _run_firestore_stream(query)

        queued_count = 0
        for payment_doc in payment_docs:
            payment = payment_doc.to_dict()
            ref = payment_doc.id
            user_id = payment["user_id"]
            amount = payment["amount"]

            payout_check = await asyncio.to_thread(lambda: db.collection("payouts").document(ref).get())
            if payout_check.exists:
                continue

            last_attempt = payment.get("last_payout_attempt")
            if last_attempt and (datetime.now(timezone.utc) - last_attempt).seconds < 600:
                continue

            await asyncio.to_thread(lambda: db.collection("payments").document(ref).update({
                "last_payout_attempt": datetime.now(timezone.utc)
            }))

            # Enqueue the Celery payout task
            payout_task.delay(user_id, amount, ref)
            queued_count += 1

        logger.info(f"Queued {queued_count} pending payouts.")

    try:
        asyncio.run(_process())
    except Exception as exc:
        logger.error(f"process_pending_payouts task failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)
