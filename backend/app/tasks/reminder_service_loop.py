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
from app.core.config import settings  # Essential for settings.BACKEND_URL
from google.cloud.firestore import Transaction # Needed if you type-hint transactions
from app.models.reminder_model import Reminder
from app.utils.receipt_emails import generate_receipt_content
from app.utils.email import get_html_wrapper
from google.cloud.firestore_v1.base_query import FieldFilter

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
        # Define references
        reminder_ref = db.collection("reminders").document(rem.id)
        invoice_id = rem.invoice_id 

        # 1. Fetch Invoice
        invoice_doc = await asyncio.to_thread(db.collection("invoices").document(invoice_id).get)
        if not invoice_doc.exists:
            await asyncio.to_thread(reminder_ref.delete)
            return

        invoice = invoice_doc.to_dict()
        
        # 2. Status Check: Stop if paid
        if invoice.get("status") == "paid":
            logger.info(f"Invoice {invoice_id} paid. Deleting reminder {rem.id}")
            await asyncio.to_thread(reminder_ref.delete) 
            return

        # 3. Fetch User Branding
        sender_id = invoice.get("sender_id")
        user_doc = await asyncio.to_thread(db.collection("users").document(sender_id).get)
        user_data = user_doc.to_dict() if user_doc.exists else {}
        
        biz_display_name = (
            user_data.get("business_name") or 
            user_data.get("full_name") or 
            "Your Provider"
        )

        # 4. Data Sanitization & Context
        client_name = (invoice.get("client_name") or "there").split()[0]
        amount = f"₦{invoice.get('amount', 0):,}"
        raw_link = invoice.get("invoice_url", "")
        clean_link = raw_link if raw_link.startswith("http") else f"https://payla.ng/{raw_link.lstrip('/')}"

        due_date = invoice.get("due_date")
        if isinstance(due_date, str):
            due_date = datetime.fromisoformat(due_date).replace(tzinfo=timezone.utc)
        
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        due_str = due_date.strftime("%b %d") if due_date else "N/A"

        context = {
            "name": client_name,
            "amount": amount,
            "due_date": due_str,
            "link": clean_link,
            "business_name": biz_display_name,
            "day_of_week": now.strftime("%A"),
            "days": (now - due_date).days if due_date and now > due_date else 0
        }

        # 5. 🔥 Strategy Logic (Mapping to your SMS_LAYLA keys)
        is_intro_needed = rem.message == "INTRO_REQUIRED"
        
        if is_intro_needed:
            # Match your SMS_LAYLA["first"] and EMAIL_TEMPLATES["first_contact"]
            whatsapp_key, sms_key, email_type = "first_invoice", "first", "first_contact"
        else:
            # Match standard flow
            whatsapp_key, sms_key, email_type = map_templates(rem.next_send, due_date, context)
            
            # Prevent "first_contact" email for returning users
            if email_type == "first_contact":
                email_type = "reminder"

        # 6. Content Generation
        custom_msg = rem.message if rem.message not in ["INTRO_REQUIRED", "STANDARD_REMINDER"] else None
        
        # SMS Generation (Uses your SMS_LAYLA dict)
        # If it's the "first" contact, we append the link so they can actually pay!
        if sms_key == "first" and not custom_msg:
            from utils.sms import SMS_LAYLA # Assuming location
            sms_msg = SMS_LAYLA["first"].format(**context) + f" View invoice: {clean_link}"
        else:
            sms_msg = custom_msg or get_layla_sms(sms_key, context)

        whatsapp_msg = custom_msg or get_layla_whatsapp(whatsapp_key, context)

        # Email Generation (Uses your Elite HTML Wrapper)
        from app.utils.email import generate_email_content, METADATA
        if custom_msg:
            from utils.email import get_html_wrapper
            email_html = get_html_wrapper(
                title="Invoice Update",
                body_text=custom_msg.replace("\n", "<br>"),
                button_text="View & Pay",
                link=clean_link,
                business_name=biz_display_name
            )
            email_subject = f"Message from {biz_display_name}"
        else:
            email_html = generate_email_content(email_type, context, use_html=True)
            meta = METADATA.get(email_type, {"title": "Notification"})
            email_subject = f"{meta['title']} | {biz_display_name}"

        # 7. Dispatch
        selected_channels = rem.channels_selected or []
        final_channels = [ch for ch in selected_channels if (
            (ch in ["whatsapp", "sms"] and invoice.get("client_phone")) or 
            (ch == "email" and invoice.get("client_email"))
        )]

        if not final_channels:
            await asyncio.to_thread(reminder_ref.delete)
            return

        tasks = [
            send_channel_with_tracking(
                ch, rem, invoice, whatsapp_msg, sms_msg, 
                email_subject, email_html, email_type, final_channels
            )
            for ch in final_channels
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

        # 8. Cleanup Logic
        final_snap = await asyncio.to_thread(reminder_ref.get)
        if final_snap.exists:
            if final_snap.to_dict().get("status") == "sent":
                logger.info(f"🗑️ Deleting completed reminder {rem.id}")
                await asyncio.to_thread(reminder_ref.delete)

    except Exception as e:
        logger.exception(f"Error processing {rem.id}: {e}")
    finally:
        release_reminder_lock(rem.id)
        

async def process_payment_notification(invoice_doc):
    invoice = invoice_doc.to_dict()
    invoice_id = invoice.get("invoice_id")

    if invoice.get("payment_notified", False):
        return

    amount_str = f"₦{invoice.get('amount', 0):,}"
    client_email = invoice.get("client_email")
    user_email = invoice.get("user_email")
    
    base_context = {
        "amount": amount_str,
        "invoice_id": invoice_id,
        "date": datetime.utcnow().strftime("%b %d, %Y"),
        "business_name": invoice.get("sender_business_name") or "Payla Creator",
    }

    tasks = []

    # 1. SMS/WhatsApp to CLIENT (Luxury Celebration)
    if invoice.get("client_phone"):
        paid_msg = get_layla_sms("paid", base_context) # Now correctly indented
        tasks.append(send_via_sms(invoice["client_phone"], paid_msg))
        tasks.append(send_via_whatsapp(invoice["client_phone"], paid_msg))

    # 2. Receipt to CLIENT
    if client_email:
        client_context = {
            **base_context,
            "client_name": (invoice.get("client_name") or "there").split()[0],
            "receipt_link": f"{settings.BACKEND_URL}api/receipt/invoice/{invoice_id}.pdf",
        }
        client_html = generate_receipt_content("client_receipt", client_context)
        client_subject = f"Receipt: {amount_str} to {base_context['business_name']}"
        tasks.append(send_single_channel("email", invoice, "", client_subject, client_html, email_type="client_receipt"))

    # 3. Alert to USER (The Creator)
    if user_email:
        user_context = {
            **base_context,
            "user_name": (invoice.get("user_name") or "Creator").split()[0],
            "client_name": (invoice.get("client_name") or "A client"),
            "client_email": client_email,
            "invoice_link": invoice.get("invoice_url"),
        }
        user_html = generate_receipt_content("user_payment_alert", user_context)
        user_subject = f"💰 Payment Received: {amount_str}!"
        tasks.append(send_single_channel("email", {"client_email": user_email}, "", user_subject, user_html, email_type="payment_alert"))

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    await asyncio.to_thread(db.collection("invoices").document(invoice_id).update, {"payment_notified": True})


async def reminder_loop():
    logger.info("🚀 Reminder loop started")
    
    while True:
        now = datetime.utcnow().replace(tzinfo=timezone.utc)

        try:
            pending_docs = await asyncio.to_thread(
                lambda: list(
                    db.collection("reminders")
                    .where(filter=FieldFilter("status", "==", "pending"))
                    .where(filter=FieldFilter("active", "==", True))
                    .where(filter=FieldFilter("next_send", "<=", now))
                    .stream()
                )
            )

            logger.info(f"🔍 Found {len(pending_docs)} pending reminders")

            paid_docs = await asyncio.to_thread(
                lambda: list(
                    db.collection("invoices")
                    .where(filter=FieldFilter("status", "==", "paid"))
                    .where(filter=FieldFilter("payment_notified", "==", False))
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