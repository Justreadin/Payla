import asyncio
from datetime import datetime, timezone
import logging
from app.core.firebase import db

logger = logging.getLogger("payla")

# --- PURGE LOGIC ---

async def purge_locked_and_old_reminders():
    """
    Specifically targets:
    1. Reminders where 'locked' is True.
    2. Reminders for invoices that are already PAID.
    3. Reminders where 'next_send' is in the past.
    """
    logger.info("🚀 Starting deep purge of reminders...")
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    
    deleted_count = 0
    batch = db.batch()
    batch_counter = 0

    # Pass 1: Handle Locked Reminders
    locked_reminders = db.collection("reminders").where("locked", "==", True).stream()
    for doc in locked_reminders:
        rem_data = doc.to_dict()
        invoice_id = rem_data.get("invoice_id")
        
        if invoice_id:
            inv_doc = db.collection("invoices").document(invoice_id).get()
            if inv_doc.exists:
                inv_status = inv_doc.to_dict().get("status", "").lower()
                if inv_status == "paid":
                    logger.info(f"Purging reminder {doc.id} (Invoice {invoice_id} is PAID)")
                else:
                    logger.info(f"Purging stuck locked reminder {doc.id} (Invoice {invoice_id} is {inv_status})")
            else:
                logger.info(f"Purging reminder {doc.id} (Invoice {invoice_id} no longer exists)")

        batch.delete(doc.reference)
        deleted_count += 1
        batch_counter += 1
        
        if batch_counter >= 400:
            batch.commit()
            batch = db.batch()
            batch_counter = 0

    # Pass 2: Final cleanup for ANY reminder older than 'now'
    old_reminders = db.collection("reminders").where("next_send", "<", now).stream()
    for doc in old_reminders:
        batch.delete(doc.reference)
        deleted_count += 1
        batch_counter += 1
        if batch_counter >= 400:
            batch.commit()
            batch = db.batch()
            batch_counter = 0

    if batch_counter > 0:
        batch.commit()

    logger.info(f"✅ Purge complete. Removed {deleted_count} total reminders.")
    return deleted_count

# --- REPEAT LOGIC ---

async def repeat_purge_forever():
    """Loop that runs once every 24 hours."""
    while True:
        try:
            await purge_locked_and_old_reminders()
        except Exception as e:
            logger.error(f"Error in background purge loop: {e}")
        
        # Wait 24 hours (86400 seconds)
        logger.info("Purge loop sleeping for 24 hours...")
        await asyncio.sleep(86400)