# app/tasks/reminder_cleanup.py
"""
Reminder cleanup worker.

Runs once per day. Performs four jobs:

  1. Cancels pending reminders whose invoice has been paid.
  2. Marks stale pending reminders (7+ days past due) as failed.
  3. Archives sent reminders older than ARCHIVE_AFTER_DAYS.
  4. Deletes archived reminders older than DELETE_AFTER_DAYS.

This module never deletes a reminder that might still be in flight.
The reminder loop's own lock and completion path is the only writer
for in-flight reminders.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.firebase import db

logger = logging.getLogger("payla.cleanup")

ARCHIVE_AFTER_DAYS = 90
DELETE_AFTER_DAYS = 365
STALE_PENDING_DAYS = 7
BATCH_SIZE = 500
CLEANUP_INTERVAL_HOURS = 24
INITIAL_DELAY_SECONDS = 300


def _utcnow() -> datetime:
    return datetime.utcnow().replace(tzinfo=timezone.utc)


async def cancel_reminders_for_paid_invoices() -> int:
    """
    Scan pending reminders once and cancel those whose invoice is
    paid. The previous approach iterated every paid invoice and
    queried reminders per invoice, which grows as O(invoices ×
    reminders).
    """
    logger.info("Cleaning up reminders for paid invoices")

    pending = await asyncio.to_thread(
        lambda: list(
            db.collection("reminders")
            .where(filter=FieldFilter("status", "==", "pending"))
            .limit(BATCH_SIZE)
            .stream()
        )
    )

    cancelled = 0

    for rem_doc in pending:
        rem = rem_doc.to_dict() or {}
        invoice_id = rem.get("invoice_id")
        if not invoice_id:
            continue

        try:
            inv_snap = await asyncio.to_thread(
                db.collection("invoices").document(invoice_id).get
            )
        except Exception:
            logger.exception(
                "Could not fetch invoice %s for reminder %s",
                invoice_id, rem_doc.id,
            )
            continue

        if not inv_snap.exists:
            continue

        if (inv_snap.to_dict() or {}).get("status") != "paid":
            continue

        try:
            await asyncio.to_thread(
                db.collection("reminders").document(rem_doc.id).update,
                {
                    "status": "cancelled",
                    "active": False,
                    "cancelled_reason": "Invoice paid",
                    "updated_at": _utcnow(),
                },
            )
            cancelled += 1
        except Exception:
            logger.exception(
                "Could not cancel reminder %s", rem_doc.id
            )

    logger.info("Cancelled %d reminders for paid invoices", cancelled)
    return cancelled


async def mark_stale_pending_as_failed() -> int:
    """
    Mark reminders pending for more than STALE_PENDING_DAYS past
    their scheduled send as failed. Records a reason so failures are
    auditable rather than silently disappearing.
    """
    cutoff = _utcnow() - timedelta(days=STALE_PENDING_DAYS)

    logger.info("Marking stale pending reminders as failed (before %s)", cutoff)

    stale = await asyncio.to_thread(
        lambda: list(
            db.collection("reminders")
            .where(filter=FieldFilter("status", "==", "pending"))
            .where(filter=FieldFilter("next_send", "<=", cutoff))
            .limit(BATCH_SIZE)
            .stream()
        )
    )

    marked = 0

    for doc in stale:
        try:
            await asyncio.to_thread(
                db.collection("reminders").document(doc.id).update,
                {
                    "status": "failed",
                    "active": False,
                    "failed_reason": (
                        f"Reminder expired, not sent within "
                        f"{STALE_PENDING_DAYS} days"
                    ),
                    "updated_at": _utcnow(),
                },
            )
            marked += 1
        except Exception:
            logger.exception(
                "Could not mark reminder %s as failed", doc.id
            )

    logger.info("Marked %d stale reminders as failed", marked)
    return marked


async def archive_old_reminders() -> int:
    """
    Move completed reminders to the archive collection. Only sent
    and cancelled reminders are archived — never pending or locked.
    """
    cutoff = _utcnow() - timedelta(days=ARCHIVE_AFTER_DAYS)

    logger.info("Archiving completed reminders older than %s", cutoff)

    archived = 0

    for status_value in ("sent", "cancelled"):
        docs = await asyncio.to_thread(
            lambda s=status_value: list(
                db.collection("reminders")
                .where(filter=FieldFilter("status", "==", s))
                .where(filter=FieldFilter("updated_at", "<=", cutoff))
                .limit(BATCH_SIZE)
                .stream()
            )
        )

        for doc in docs:
            try:
                data = doc.to_dict() or {}
                await asyncio.to_thread(
                    db.collection("reminders_archive")
                    .document(doc.id)
                    .set,
                    {**data, "archived_at": _utcnow()},
                )
                await asyncio.to_thread(
                    db.collection("reminders").document(doc.id).delete
                )
                archived += 1
            except Exception:
                logger.exception(
                    "Could not archive reminder %s", doc.id
                )

    logger.info("Archived %d old reminders", archived)
    return archived


async def delete_old_archives() -> int:
    """Permanently delete archives older than DELETE_AFTER_DAYS."""
    cutoff = _utcnow() - timedelta(days=DELETE_AFTER_DAYS)

    logger.info("Deleting archived reminders older than %s", cutoff)

    archives = await asyncio.to_thread(
        lambda: list(
            db.collection("reminders_archive")
            .where(filter=FieldFilter("archived_at", "<=", cutoff))
            .limit(BATCH_SIZE)
            .stream()
        )
    )

    deleted = 0

    for doc in archives:
        try:
            await asyncio.to_thread(
                db.collection("reminders_archive")
                .document(doc.id)
                .delete
            )
            deleted += 1
        except Exception:
            logger.exception("Could not delete archive %s", doc.id)

    logger.info("Deleted %d old archives", deleted)
    return deleted


async def cleanup_loop() -> None:
    """Run the cleanup cycle once per day. Never raises."""
    logger.info("Reminder cleanup service started")

    # Delay the first run so a dev reload or a fresh deploy does not
    # trigger a full pass on every restart.
    await asyncio.sleep(INITIAL_DELAY_SECONDS)

    while True:
        try:
            logger.info("Cleanup cycle starting")

            cancelled = await cancel_reminders_for_paid_invoices()
            failed = await mark_stale_pending_as_failed()
            archived = await archive_old_reminders()
            deleted = await delete_old_archives()

            logger.info(
                "Cleanup cycle complete: "
                "%d cancelled, %d marked failed, %d archived, %d deleted",
                cancelled, failed, archived, deleted,
            )

        except Exception:
            logger.exception("Cleanup cycle error")

        await asyncio.sleep(CLEANUP_INTERVAL_HOURS * 60 * 60)


if __name__ == "__main__":
    asyncio.run(cleanup_loop())