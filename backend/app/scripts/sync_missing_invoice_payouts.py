
# app/scripts/sync_missing_invoice_payouts.py

import asyncio
import logging
from datetime import datetime, timezone, timedelta

from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.firebase import db


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("payla_sync")


def expected_arrival_date(now: datetime) -> datetime:
    """Estimate the next working-day arrival date."""
    if now.weekday() == 4:  # Friday
        days_ahead = 3
    elif now.weekday() == 5:  # Saturday
        days_ahead = 2
    else:
        days_ahead = 1

    return now + timedelta(days=days_ahead)


async def sync_missing_invoice_payouts():
    logger.info("Starting invoice payout-history recovery")

    invoices = (
        db.collection("invoices")
        .where(
            filter=FieldFilter("status", "==", "paid")
        )
        .stream()
    )

    found_count = 0
    synced_count = 0
    skipped_count = 0
    failed_count = 0

    for invoice in invoices:
        found_count += 1
        data = invoice.to_dict()

        reference = data.get("transaction_reference")
        user_id = data.get("sender_id")
        amount = data.get("amount", 0)

        if not reference or not user_id:
            logger.warning(
                "Skipping invoice %s: missing transaction reference or sender_id",
                invoice.id,
            )
            skipped_count += 1
            continue

        payout_ref = db.collection("payouts").document(reference)
        user_ref = db.collection("users").document(user_id)

        transaction = db.transaction()

        @firestore.transactional
        def create_missing_record(transaction):
            # Check for an existing record inside the transaction.
            existing = payout_ref.get(transaction=transaction)

            if existing.exists:
                return "exists"

            # Confirm the user exists before creating the record.
            user_snapshot = user_ref.get(transaction=transaction)

            if not user_snapshot.exists:
                return "missing_user"

            user_data = user_snapshot.to_dict() or {}
            now = datetime.now(timezone.utc)

            # This is a recovered history record, not confirmation
            # that the funds have reached the recipient's bank.
            payout_entry = {
                "user_id": user_id,
                "reference": reference,
                "amount": amount,
                "type": "invoice",
                "status": "processing",
                "payout_status": "processing",
                "created_at": now,
                "arrival_date": expected_arrival_date(now),
                "is_automated": bool(
                    user_data.get("paystack_subaccount_code")
                ),
                "recovered": True,
            }

            transaction.set(payout_ref, payout_entry)

            return "created"

        try:
            result = create_missing_record(transaction)

            if result == "created":
                synced_count += 1
                logger.info(
                    "Recovered payout history for invoice %s "
                    "(reference=%s, amount=%s)",
                    invoice.id,
                    reference,
                    amount,
                )

            elif result == "exists":
                skipped_count += 1
                logger.info(
                    "Skipping invoice %s: payout record already exists",
                    invoice.id,
                )

            elif result == "missing_user":
                skipped_count += 1
                logger.warning(
                    "Skipping invoice %s: user %s does not exist",
                    invoice.id,
                    user_id,
                )

        except Exception:
            failed_count += 1
            logger.exception(
                "Failed to recover payout history for invoice %s",
                invoice.id,
            )

    logger.info("----- INVOICE RECOVERY SUMMARY -----")
    logger.info("Paid invoices found: %s", found_count)
    logger.info("Payout records created: %s", synced_count)
    logger.info("Records skipped: %s", skipped_count)
    logger.info("Failures: %s", failed_count)
    logger.info("Recovery finished")


if __name__ == "__main__":
    asyncio.run(sync_missing_invoice_payouts())
