# tasks/reminder_worker.py
from datetime import datetime, timezone
from app.core.firebase import db
from app.models.reminder_model import Reminder
from app.services.channels import send_via_whatsapp, send_via_sms, send_via_email

async def process_pending_reminders():
    now = datetime.utcnow()
    docs = db.collection("reminders").where("status", "==", "pending").where("next_send", "<=", now).stream()
    for doc in docs:
        rem = Reminder(**doc.to_dict())
        invoice_doc = db.collection("invoices").document(rem.invoice_id).get()
        if not invoice_doc.exists:
            continue
        invoice = invoice_doc.to_dict()
        methods = [rem.method]

        for method in methods:
            try:
                if method == "whatsapp" and invoice.get("client_phone"):
                    await send_via_whatsapp(invoice["client_phone"], rem.message)
                elif method == "sms" and invoice.get("client_phone"):
                    await send_via_sms(invoice["client_phone"], rem.message)
                elif method == "email" and invoice.get("client_email"):
                    await send_via_email(invoice["client_email"], "Invoice Reminder", rem.message)
                db.collection("reminders").document(rem.id).update({
                    "status": "sent",
                    "sent_at": datetime.utcnow()
                })
            except Exception as e:
                print(f"Failed to send reminder {rem.id}: {e}")
