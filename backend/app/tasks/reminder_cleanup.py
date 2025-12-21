#!/usr/bin/env python3
"""
Reminder cleanup service - runs periodically to archive old reminders
Save this as: app/tasks/reminder_cleanup.py
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from firebase_admin import firestore

from app.core.firebase import db

logger = logging.getLogger("payla.cleanup")

# Configuration
ARCHIVE_AFTER_DAYS = 90  # Archive reminders older than 90 days
DELETE_AFTER_DAYS = 365  # Delete archived reminders after 1 year
BATCH_SIZE = 500
CLEANUP_INTERVAL_HOURS = 24  # Run cleanup once per day


async def archive_old_reminders():
    """
    Move old 'sent' reminders to an archive collection.
    This keeps your main reminders collection fast and queries efficient.
    """
    cutoff_date = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=ARCHIVE_AFTER_DAYS)
    
    logger.info(f"📦 Archiving reminders older than {cutoff_date}")
    
    # Get old sent reminders
    reminders = await asyncio.to_thread(
        lambda: list(
            db.collection("reminders")
            .where("status", "==", "sent")
            .where("sent_at", "<=", cutoff_date)
            .limit(BATCH_SIZE)
            .stream()
        )
    )
    
    archived_count = 0
    
    for doc in reminders:
        try:
            data = doc.to_dict()
            
            # Copy to archive collection
            await asyncio.to_thread(
                db.collection("reminders_archive").document(doc.id).set,
                {**data, "archived_at": datetime.utcnow().replace(tzinfo=timezone.utc)}
            )
            
            # Delete from main collection
            await asyncio.to_thread(
                db.collection("reminders").document(doc.id).delete
            )
            
            archived_count += 1
            
        except Exception as e:
            logger.error(f"Failed to archive reminder {doc.id}: {e}")
    
    logger.info(f"✅ Archived {archived_count} old reminders")
    return archived_count


async def delete_old_archives():
    """
    Permanently delete very old archived reminders (older than 1 year).
    """
    cutoff_date = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=DELETE_AFTER_DAYS)
    
    logger.info(f"🗑️  Deleting archived reminders older than {cutoff_date}")
    
    archives = await asyncio.to_thread(
        lambda: list(
            db.collection("reminders_archive")
            .where("archived_at", "<=", cutoff_date)
            .limit(BATCH_SIZE)
            .stream()
        )
    )
    
    deleted_count = 0
    
    for doc in archives:
        try:
            await asyncio.to_thread(
                db.collection("reminders_archive").document(doc.id).delete
            )
            deleted_count += 1
        except Exception as e:
            logger.error(f"Failed to delete archive {doc.id}: {e}")
    
    logger.info(f"✅ Deleted {deleted_count} old archives")
    return deleted_count


async def cleanup_failed_reminders():
    """
    Clean up reminders that are stuck in 'pending' state for too long.
    After 7 days, mark them as 'failed' so they don't clog up queries.
    """
    cutoff_date = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=7)
    
    logger.info(f"⚠️  Marking stale pending reminders as failed (older than {cutoff_date})")
    
    pending = await asyncio.to_thread(
        lambda: list(
            db.collection("reminders")
            .where("status", "==", "pending")
            .where("next_send", "<=", cutoff_date)
            .limit(BATCH_SIZE)
            .stream()
        )
    )
    
    failed_count = 0
    
    for doc in pending:
        try:
            await asyncio.to_thread(
                db.collection("reminders").document(doc.id).update,
                {
                    "status": "failed",
                    "active": False,
                    "failed_reason": "Reminder expired - not sent within 7 days",
                    "updated_at": datetime.utcnow().replace(tzinfo=timezone.utc)
                }
            )
            failed_count += 1
        except Exception as e:
            logger.error(f"Failed to update reminder {doc.id}: {e}")
    
    logger.info(f"✅ Marked {failed_count} stale reminders as failed")
    return failed_count


async def cleanup_reminders_for_paid_invoices():
    """
    Deactivate all pending reminders for invoices that have been paid.
    No need to send reminders for paid invoices!
    """
    logger.info("💰 Cleaning up reminders for paid invoices")
    
    # Get all paid invoices
    paid_invoices = await asyncio.to_thread(
        lambda: list(
            db.collection("invoices")
            .where("status", "==", "paid")
            .stream()
        )
    )
    
    cleaned_count = 0
    
    for inv_doc in paid_invoices:
        invoice_id = inv_doc.id
        
        # Find pending reminders for this invoice
        reminders = await asyncio.to_thread(
            lambda: list(
                db.collection("reminders")
                .where("invoice_id", "==", invoice_id)
                .where("status", "==", "pending")
                .stream()
            )
        )
        
        for rem_doc in reminders:
            try:
                await asyncio.to_thread(
                    db.collection("reminders").document(rem_doc.id).update,
                    {
                        "status": "cancelled",
                        "active": False,
                        "cancelled_reason": "Invoice paid",
                        "updated_at": datetime.utcnow().replace(tzinfo=timezone.utc)
                    }
                )
                cleaned_count += 1
            except Exception as e:
                logger.error(f"Failed to cancel reminder {rem_doc.id}: {e}")
    
    logger.info(f"✅ Cancelled {cleaned_count} reminders for paid invoices")
    return cleaned_count


async def cleanup_loop():
    """
    Main cleanup loop - runs daily
    """
    logger.info("🧹 Starting reminder cleanup service")
    
    # Wait a bit before first run to let the system stabilize
    await asyncio.sleep(60)
    
    while True:
        try:
            logger.info("🧹 Starting cleanup cycle...")
            
            # Run all cleanup tasks
            paid_count = await cleanup_reminders_for_paid_invoices()
            failed_count = await cleanup_failed_reminders()
            archived_count = await archive_old_reminders()
            deleted_count = await delete_old_archives()
            
            logger.info(
                f"✅ Cleanup cycle complete: "
                f"{paid_count} cancelled, {failed_count} marked failed, "
                f"{archived_count} archived, {deleted_count} deleted"
            )
            
        except Exception as e:
            logger.exception(f"❌ Cleanup error: {e}")
        
        # Run once per day
        await asyncio.sleep(CLEANUP_INTERVAL_HOURS * 60 * 60)


if __name__ == "__main__":
    # For standalone testing
    asyncio.run(cleanup_loop())