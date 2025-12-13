# app/tasks/reminder_service_loop.py
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict
from firebase_admin import firestore
from app.services.reminder_service import send_if_allowed, get_layla_whatsapp, get_layla_sms, get_layla_email
from app.models.reminder_model import Reminder

db = firestore.client()
logger = logging.getLogger("payla.reminders")

CHECK_INTERVAL = 60  # seconds between reminder checks

async def reminder_loop():
    """
    Main async loop to process pending reminders.
    """
    while True:
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        try:
            # Fetch pending reminders that are due
            pending_docs = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: list(
                    db.collection("reminders")
                    .where("status", "==", "pending")
                    .where("next_send", "<=", now)
                    .stream()
                )
            )

            if pending_docs:
                logger.info(f"Found {len(pending_docs)} pending reminders.")

            for doc in pending_docs:
                rem_dict = doc.to_dict()
                rem = Reminder(**rem_dict)

                # Fetch invoice
                invoice_doc = db.collection("invoices").document(rem.invoice_id).get()
                if not invoice_doc.exists:
                    logger.warning(f"Invoice {rem.invoice_id} not found for reminder {rem.id}")
                    continue
                invoice = invoice_doc.to_dict()

                # Build context
                client_name = (invoice.get("client_name") or "there").split()[0]
                amount = f"₦{invoice.get('amount', 0):,}"
                due_date = invoice.get("due_date")
                due_str = due_date.strftime("%b %d") if due_date else "N/A"

                context = {
                    "name": client_name,
                    "amount": amount,
                    "due_date": due_str,
                    "link": invoice.get("invoice_url", ""),
                    "business_name": invoice.get("sender_business_name", "Payla user"),
                    "invoice_id": rem.invoice_id
                }

                # Generate messages
                whatsapp_msg = get_layla_whatsapp("gentle_nudge", context)
                sms_msg = get_layla_sms("gentle", context)
                email_html = get_layla_email("reminder", context)
                email_subject = f"Reminder: {amount} due on {due_str}"

                # Send messages async if allowed
                await send_if_allowed(
                    methods=[rem.method],
                    invoice=invoice,
                    whatsapp_msg=whatsapp_msg,
                    sms_msg=sms_msg,
                    email_subject=email_subject,
                    email_html=email_html
                )

                # Mark as sent
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: doc.reference.update({
                        "status": "sent",
                        "sent_at": datetime.utcnow().replace(tzinfo=timezone.utc)
                    })
                )
                logger.info(f"Reminder {rem.id} sent successfully.")

        except Exception as e:
            logger.exception(f"Reminder loop error: {e}")

        await asyncio.sleep(CHECK_INTERVAL)
