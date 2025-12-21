# app/tasks/reminder_service_loop.py

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from firebase_admin import firestore

from app.services.reminder_service import (
    send_via_whatsapp,
    send_via_sms,
    send_via_email,
    get_layla_whatsapp,
    get_layla_sms,
    get_layla_email,
    map_templates,
)
from app.models.reminder_model import Reminder

db = firestore.client()
logger = logging.getLogger("payla.reminders")

CHECK_INTERVAL = 60
MAX_RETRIES = 3  # Reduced from 5
RETRY_INTERVAL = 5 * 60  # Reduced from 15 to 5 minutes
QUIET_START = 22
QUIET_END = 7

LOCK_TIMEOUT = timedelta(minutes=10)


def is_within_quiet_hours(now: datetime) -> bool:
    hour = now.hour
    return hour >= QUIET_START or hour < QUIET_END


def acquire_reminder_lock(reminder_id: str) -> bool:
    ref = db.collection("reminders").document(reminder_id)

    @firestore.transactional
    def txn(transaction):
        snap = ref.get(transaction=transaction)
        data = snap.to_dict() or {}

        locked = data.get("locked", False)
        locked_at = data.get("locked_at")

        if locked and locked_at:
            locked_at = locked_at.replace(tzinfo=timezone.utc)
            if datetime.utcnow().replace(tzinfo=timezone.utc) - locked_at < LOCK_TIMEOUT:
                return False

        transaction.update(ref, {
            "locked": True,
            "locked_at": datetime.utcnow().replace(tzinfo=timezone.utc),
        })
        return True

    transaction = db.transaction()
    return txn(transaction)


def release_reminder_lock(reminder_id: str):
    db.collection("reminders").document(reminder_id).update({
        "locked": False,
        "locked_at": None,
    })


async def send_single_channel(
    method: str,
    invoice: dict,
    msg: str,
    subject: str = None,
    html: str = None,
    email_type: str = "reminder",
    max_retries: int = MAX_RETRIES,
) -> bool:
    """
    Send via a single channel with retries.
    Non-blocking - returns False on failure instead of waiting forever.
    """
    attempt = 0

    while attempt < max_retries:
        now = datetime.utcnow().replace(tzinfo=timezone.utc)

        if is_within_quiet_hours(now):
            logger.info(f"[{method}] Quiet hours active, will retry later")
            await asyncio.sleep(60)  # Wait 1 min and check again
            continue

        try:
            if method == "whatsapp" and invoice.get("client_phone"):
                logger.info(f"[{method}] Attempt {attempt + 1}/{max_retries} | phone={invoice['client_phone']}")
                await send_via_whatsapp(invoice["client_phone"], msg)

            elif method == "sms" and invoice.get("client_phone"):
                logger.info(f"[{method}] Attempt {attempt + 1}/{max_retries} | phone={invoice['client_phone']}")
                await send_via_sms(invoice["client_phone"], msg)

            elif method == "email" and invoice.get("client_email"):
                logger.info(f"[{method}] Attempt {attempt + 1}/{max_retries} | email={invoice['client_email']}")
                await send_via_email(invoice["client_email"], subject, html, email_type=email_type)

            logger.info(f"[{method}] ✅ Success!")
            return True

        except Exception as e:
            attempt += 1
            logger.error(f"[{method}] ❌ Attempt {attempt}/{max_retries} failed: {e}")
            
            if attempt < max_retries:
                logger.info(f"[{method}] Waiting {RETRY_INTERVAL}s before retry...")
                await asyncio.sleep(RETRY_INTERVAL)
            else:
                logger.error(f"[{method}] All {max_retries} attempts failed, giving up")

    return False


async def send_channel_with_tracking(
    ch: str,
    rem: Reminder,
    invoice: dict,
    whatsapp_msg: str,
    sms_msg: str,
    email_subject: str,
    email_html: str,
    email_type: str,
    all_channels: list,
):
    """
    Send via one channel and update tracking in Firestore.
    Each channel runs independently in parallel.
    """
    if ch in rem.channel_used:
        logger.info(f"[{ch}] Already sent for reminder {rem.id}, skipping")
        return

    logger.info(f"[{ch}] Starting send for reminder {rem.id}")

    success = await send_single_channel(
        ch,
        invoice,
        whatsapp_msg if ch == "whatsapp" else sms_msg if ch == "sms" else "",
        email_subject,
        email_html if ch == "email" else None,
        email_type=email_type,
    )

    if success:
        # Update Firestore with this channel as sent
        try:
            ref = db.collection("reminders").document(rem.id)
            
            @firestore.transactional
            def update_channel(transaction):
                snap = ref.get(transaction=transaction)
                data = snap.to_dict()
                
                channel_used = data.get("channel_used", [])
                if ch not in channel_used:
                    channel_used.append(ch)
                
                status = "sent" if set(channel_used) == set(all_channels) else "pending"
                
                transaction.update(ref, {
                    "channel_used": channel_used,
                    "status": status,
                    "sent_at": datetime.utcnow().replace(tzinfo=timezone.utc),
                })
            
            transaction = db.transaction()
            await asyncio.to_thread(update_channel, transaction)
            
            logger.info(f"[{ch}] ✅ Marked as sent for reminder {rem.id}")
            
        except Exception as e:
            logger.error(f"[{ch}] Failed to update Firestore: {e}")
    else:
        logger.error(f"[{ch}] ❌ Failed to send for reminder {rem.id}")


async def process_reminder(rem: Reminder):
    if not acquire_reminder_lock(rem.id):
        logger.info(f"Reminder {rem.id} already locked, skipping")
        return

    try:
        invoice_doc = await asyncio.to_thread(
            db.collection("invoices").document(rem.invoice_id).get
        )

        if not invoice_doc.exists:
            logger.warning(f"Invoice {rem.invoice_id} not found for reminder {rem.id}")
            return

        invoice = invoice_doc.to_dict()

        if invoice.get("status") == "paid":
            logger.info(f"Invoice {rem.invoice_id} is paid, marking reminder {rem.id} as sent")
            await asyncio.to_thread(
                db.collection("reminders").document(rem.id).update,
                {"status": "sent", "active": False}
            )
            return

        client_name = (invoice.get("client_name") or "there").split()[0]
        amount = f"₦{invoice.get('amount', 0):,}"
        due_date = invoice.get("due_date")
        
        if isinstance(due_date, str):
            due_date = datetime.fromisoformat(due_date).replace(tzinfo=timezone.utc)
        elif hasattr(due_date, 'replace'):
            due_date = due_date.replace(tzinfo=timezone.utc)
            
        due_str = due_date.strftime("%b %d") if due_date else "N/A"

        context = {
            "name": client_name,
            "amount": amount,
            "due_date": due_str,
            "due_date_dt": due_date,
            "link": invoice.get("invoice_url", ""),
            "business_name": invoice.get("sender_business_name", "Payla user"),
            "invoice_id": rem.invoice_id,
        }

        whatsapp_key, sms_key, email_type = map_templates(rem.next_send, due_date, context)

        channels = rem.channels_selected or []

        if not channels:
            logger.warning(f"Reminder {rem.id} has no channels_selected, skipping")
            return

        whatsapp_msg = rem.message or get_layla_whatsapp(whatsapp_key, context)
        sms_msg = rem.message or get_layla_sms(sms_key, context)
        email_html = rem.message or get_layla_email(email_type, context)
        email_subject = f"Reminder: {amount} due on {due_str}"

        final_channels = []
        for ch in channels:
            if ch in ["whatsapp", "sms"] and invoice.get("client_phone"):
                final_channels.append(ch)
            elif ch == "email" and invoice.get("client_email"):
                final_channels.append(ch)

        if not final_channels:
            logger.warning(f"No valid channels for reminder {rem.id}")
            return

        logger.info(f"📤 Sending reminder {rem.id} via channels: {final_channels}")

        # 🔥 KEY FIX: Send all channels IN PARALLEL independently
        tasks = [
            send_channel_with_tracking(
                ch,
                rem,
                invoice,
                whatsapp_msg,
                sms_msg,
                email_subject,
                email_html,
                email_type,
                final_channels,
            )
            for ch in final_channels
        ]

        await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info(f"✅ Finished processing reminder {rem.id}")

    except Exception as e:
        logger.exception(f"Error processing reminder {rem.id}: {e}")
    finally:
        release_reminder_lock(rem.id)


async def process_payment_notification(invoice_doc):
    invoice = invoice_doc.to_dict()

    if invoice.get("payment_notified", False):
        return

    client_name = (invoice.get("client_name") or "there").split()[0]
    amount = f"₦{invoice.get('amount', 0):,}"

    context = {
        "name": client_name,
        "amount": amount,
        "invoice_id": invoice.get("invoice_id"),
    }

    whatsapp_msg = get_layla_whatsapp("payment_received", context)
    email_html = get_layla_email("payment_received", context)
    email_subject = f"Payment received: {amount}"

    tasks = []

    if invoice.get("user_phone"):
        tasks.append(
            send_single_channel(
                "whatsapp",
                {"client_phone": invoice["user_phone"]},
                whatsapp_msg,
            )
        )

    if invoice.get("user_email"):
        tasks.append(
            send_single_channel(
                "email",
                {"client_email": invoice["user_email"]},
                "",
                email_subject,
                email_html,
                email_type="payment_received",
            )
        )

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    await asyncio.to_thread(
        db.collection("invoices").document(invoice["invoice_id"]).update,
        {"payment_notified": True},
    )

    logger.info(f"Payment notification sent for invoice {invoice['invoice_id']}")


async def reminder_loop():
    logger.info("🚀 Reminder loop started")
    
    while True:
        now = datetime.utcnow().replace(tzinfo=timezone.utc)

        try:
            pending_docs = await asyncio.to_thread(
                lambda: list(
                    db.collection("reminders")
                    .where("status", "==", "pending")
                    .where("active", "==", True)
                    .where("next_send", "<=", now)
                    .stream()
                )
            )

            logger.info(f"🔍 Found {len(pending_docs)} pending reminders")

            paid_docs = await asyncio.to_thread(
                lambda: list(
                    db.collection("invoices")
                    .where("status", "==", "paid")
                    .where("payment_notified", "==", False)
                    .stream()
                )
            )

            tasks = []

            for doc in pending_docs:
                data = doc.to_dict()
                data["id"] = doc.id
                logger.info(f"📨 Processing reminder {doc.id} with channels: {data.get('channels_selected')}")
                tasks.append(process_reminder(Reminder(**data)))

            for doc in paid_docs:
                tasks.append(process_payment_notification(doc))

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
            logger.exception(f"❌ Reminder loop error: {e}")

        await asyncio.sleep(CHECK_INTERVAL)