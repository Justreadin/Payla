# app/tasks/reminder_dispatcher.py
import asyncio
import logging
from datetime import datetime, timezone
from firebase_admin import firestore
from app.services.reminder_service import send_if_allowed
from app.services.reminder_service import get_layla_whatsapp, get_layla_sms, get_layla_email

db = firestore.client()
logger = logging.getLogger("payla.reminders")

CHECK_INTERVAL = 60  # seconds


def extract_invoice_id(reminder_invoice_id: str):
    """
    Extract base invoice ID from reminder.invoice_id.
    Handles draft_* and inv_* suffixes with timestamps.
    """
    if not reminder_invoice_id:
        return None
    parts = reminder_invoice_id.split("_")
    if len(parts) >= 2:
        return "_".join(parts[:2])
    return reminder_invoice_id


async def get_invoice(loop, invoice_id: str):
    """
    Fetch invoice document from Firestore. Try fallback ID if not found.
    """
    doc = await loop.run_in_executor(None, lambda: db.collection("invoices").document(invoice_id).get())
    if doc.exists:
        return doc
    # fallback: remove prefix
    if invoice_id.startswith("draft_") or invoice_id.startswith("inv_"):
        fallback_id = invoice_id.split("_")[1]  # numeric part only
        doc = await loop.run_in_executor(None, lambda: db.collection("invoices").document(fallback_id).get())
        if doc.exists:
            return doc
    return None


async def reminder_dispatcher_loop():
    loop = asyncio.get_event_loop()

    while True:
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        try:
            pending_docs = await loop.run_in_executor(
                None,
                lambda: list(
                    db.collection("reminders")
                    .where("status", "==", "pending")
                    .where("next_send", "<=", now)
                    .stream()
                )
            )

            if pending_docs:
                logger.info(f"Found {len(pending_docs)} pending reminders to send.")

            for doc in pending_docs:
                reminder = doc.to_dict()
                raw_invoice_id = reminder.get("invoice_id")

                if not raw_invoice_id:
                    logger.warning(f"Reminder {doc.id} has no invoice_id. Skipping.")
                    continue

                invoice_id = extract_invoice_id(raw_invoice_id)

                # await get_invoice properly
                invoice_doc = await get_invoice(loop, invoice_id)

                if not invoice_doc or not invoice_doc.exists:
                    logger.warning(
                        f"Invoice not found for reminder {doc.id}. Tried {invoice_id} and fallback."
                    )
                    continue

                invoice = invoice_doc.to_dict()

                context = {
                    "name": invoice.get("client_name", "there").split()[0],
                    "amount": f"₦{invoice.get('amount', 0):,}",
                    "due_date": invoice.get("due_date").strftime("%b %d") if invoice.get("due_date") else "N/A",
                    "link": invoice.get("invoice_url", ""),
                    "business_name": invoice.get("sender_business_name", "Payla user"),
                    "invoice_id": invoice_id
                }

                whatsapp_msg = get_layla_whatsapp("gentle_nudge", context)
                sms_msg = get_layla_sms("gentle", context)
                email_html = get_layla_email("reminder", context)
                email_subject = f"Reminder: {context['amount']} due on {context['due_date']}"

                await send_if_allowed(
                    [reminder["method"]],
                    invoice,
                    whatsapp_msg=whatsapp_msg,
                    sms_msg=sms_msg,
                    email_subject=email_subject,
                    email_html=email_html
                )

                await loop.run_in_executor(
                    None,
                    lambda: doc.reference.update({
                        "status": "sent",
                        "last_sent": datetime.utcnow().replace(tzinfo=timezone.utc)
                    })
                )
                logger.info(f"Reminder {doc.id} sent successfully.")

        except Exception as e:
            logger.exception(f"Reminder dispatcher failed: {e}")

        await asyncio.sleep(CHECK_INTERVAL)
