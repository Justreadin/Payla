# tasks/reminder_scheduler.py
import httpx
import logging
from datetime import datetime
from app.core.firebase import db
from app.core.config import settings

logger = logging.getLogger("payla")

def send_reminder(reminder_doc):
    reminder = reminder_doc.to_dict()
    phone = reminder.get("client_phone")
    method = reminder.get("method")
    message = reminder.get("message")
    
    try:
        logger.info(f"Preparing to send {method} reminder to {reminder.get('client_name', phone)}")

        if method == "whatsapp":
            payload = {
                "messaging_product": "whatsapp",
                "to": phone,
                "type": "template",
                "template": {
                    "name": "payla_reminder",
                    "language": {"code": "en"},
                    "components": [{"type": "body", "parameters": [{"type": "text", "text": message}]}]
                }
            }
            response = httpx.post(
                f"https://graph.facebook.com/v18.0/{settings.WHATSAPP_PHONE_ID}/messages",
                json=payload,
                headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"}
            )
            logger.info(f"WhatsApp reminder sent to {phone}. Status: {response.status_code}, Response: {response.text}")

        elif method == "sms":
            response = httpx.post(
                "https://api.ng.termii.com/api/sms/send",
                json={
                    "to": phone,
                    "from": "Payla",
                    "sms": message,
                    "type": "plain",
                    "channel": "generic",
                    "api_key": settings.TERMII_API_KEY
                }
            )
            logger.info(f"SMS reminder sent to {phone}. Status: {response.status_code}, Response: {response.text}")

        elif method == "email":
            from app.utils.email import send_email
            context = {
                "name": reminder.get("client_name"),
                "amount": reminder.get("amount"),
                "due_date": reminder.get("due_date"),
                "link": reminder.get("payment_link"),
                "subject": f"Your invoice of {reminder.get('amount')} is due"
            }
            send_email(reminder.get("client_email"), email_type="reminder", context=context)
            logger.info(f"Email reminder sent to {reminder.get('client_email')}")

        # Mark as sent
        db.collection("reminders").document(reminder_doc.id).update({
            "last_sent": datetime.utcnow(),
            "active": False
        })
        logger.info(f"Reminder {reminder_doc.id} marked as sent.")

    except Exception as e:
        logger.error(f"Failed to send {method} reminder for {reminder_doc.id}: {e}")


def run_reminder_scheduler():
    now = datetime.utcnow()
    docs = (
        db.collection("reminders")
        .where("active", "==", True)
        .where("next_send", "<=", now)
        .stream()
    )

    count = 0
    for doc in docs:
        count += 1
        data = doc.to_dict()
        invoice_doc = db.collection("invoices").document(data.get("invoice_id")).get()
        if invoice_doc.to_dict().get("status") == "paid":
            db.collection("reminders").document(doc.id).update({"active": False})
            logger.info(f"Reminder {doc.id} skipped: invoice already paid.")
            continue

        send_reminder(doc)

    logger.info(f"Reminder scheduler run complete. {count} reminders processed.")
