# services/reminder_service.py
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import logging
from app.models.reminder_model import Reminder, ReminderCreate
from app.core.firebase import db
from app.services.channels import send_via_whatsapp, send_via_sms, send_via_email
from app.utils.email import generate_email_content, get_sender
from app.utils.whatsapp_layla import WHATSAPP_MESSAGES
from app.utils.sms_layla import SMS_LAYLA

logger = logging.getLogger("payla")


def get_layla_whatsapp(key: str, context: Dict[str, Any]) -> str:
    return WHATSAPP_MESSAGES.get(key, WHATSAPP_MESSAGES["gentle_nudge"]).format(**context)


def get_layla_sms(key: str, context: Dict[str, Any]) -> str:
    return SMS_LAYLA.get(key, SMS_LAYLA["gentle"]).format(**context)[:160]


def get_layla_email(email_type: str, context: dict, use_html: bool = True) -> str:
    return generate_email_content(email_type, context, use_html=use_html)


def is_within_quiet_hours(now: datetime, start_hour: int = 22, end_hour: int = 7) -> bool:
    current_hour = now.hour
    return start_hour <= current_hour or current_hour < end_hour


async def send_if_allowed(
    methods: List[str],
    invoice: dict,
    whatsapp_msg: str,
    sms_msg: str,
    email_subject: str,
    email_html: str,
    email_type: str = "reminder"
):
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    if is_within_quiet_hours(now):
        logger.info("Currently in quiet hours – delaying immediate send.")
        return

    if "whatsapp" in methods and invoice.get("client_phone"):
        try:
            logger.info(f"Sending WhatsApp to {invoice['client_phone']}")
            await send_via_whatsapp(invoice["client_phone"], whatsapp_msg)
        except Exception as e:
            logger.error(f"WhatsApp send failed: {e}")

    if "sms" in methods and invoice.get("client_phone"):
        try:
            logger.info(f"Sending SMS to {invoice['client_phone']}")
            await send_via_sms(invoice["client_phone"], sms_msg)
        except Exception as e:
            logger.error(f"SMS send failed: {e}")

    if "email" in methods and invoice.get("client_email"):
        try:
            logger.info(f"Sending Email to {invoice['client_email']} with type '{email_type}'")
            result = await send_via_email(
                invoice["client_email"],
                email_subject,
                email_html,
                email_type=email_type
            )
            logger.info(f"Email send result: {result}")
        except Exception as e:
            logger.error(f"Email send failed: {e}")


async def schedule_reminders_for_invoice(
    invoice_id: str,
    payload: ReminderCreate,
    user_id: str
) -> List[Reminder]:
    """
    Elite reminder scheduling with Layla voice across WhatsApp/SMS/Email.
    Ensures published invoice is used (never draft).
    """

    # --------------------------------------------------------
    # 1. Load invoice FIRST
    # --------------------------------------------------------
    inv_doc = db.collection("invoices").document(invoice_id).get()
    if not inv_doc.exists:
        raise ValueError("Invoice not found")

    invoice = inv_doc.to_dict()

    # --------------------------------------------------------
    # 2. If invoice is still draft, wait for Firestore propagation
    # --------------------------------------------------------
    if invoice.get("status") == "draft":
        logger.warning(f"Invoice {invoice_id} still draft — waiting for published data...")
        await asyncio.sleep(0.5)

        # Reload after waiting
        invoice = db.collection("invoices").document(invoice_id).get().to_dict()

        if invoice.get("status") == "draft":
            raise ValueError("Cannot schedule reminders for draft invoice")

    # --------------------------------------------------------
    # Now invoice is guaranteed published — continue
    # --------------------------------------------------------

    # Normalize client email
    invoice["client_email"] = (
        invoice.get("client_email") or
        invoice.get("email") or
        invoice.get("clientEmail")
    )
    logger.info(f"Invoice email: {invoice['client_email']}")

    due_date = invoice["due_date"]
    if isinstance(due_date, datetime):
        due_date = due_date.replace(tzinfo=timezone.utc)

    client_name = (invoice.get("client_name") or "there").split()[0]
    amount = invoice.get("amount", 0)
    amount_str = f"₦{amount:,}"
    link = invoice["invoice_url"]
    business_name = invoice.get("business_name") or "Payla user"
    invoice_ref = invoice.get("invoice_id", invoice_id.split("_")[-1])

    # Load user settings
    settings_doc = db.collection("reminder_settings").document(user_id).get()
    settings = settings_doc.to_dict() if settings_doc.exists else {}
    methods = payload.method_priority or settings.get("methods", ["whatsapp", "sms", "email"])
    logger.info(f"Methods for sending: {methods}")

    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    triggers = []

    # Manual dates
    if payload.manual_dates:
        for dt_str in payload.manual_dates:
            try:
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00")).astimezone(timezone.utc)
                triggers.append(dt)
            except Exception as e:
                logger.warning(f"Invalid manual date {dt_str}: {e}")
    else:
        # Presets
        preset = payload.preset or settings.get("preset", "standard")
        if preset == "gentle":
            triggers.append(due_date - timedelta(days=3))
        elif preset == "aggressive":
            for i in range(5):
                triggers.append(due_date - timedelta(days=4 - i))
        else:
            triggers.extend([
                due_date - timedelta(days=3),
                due_date - timedelta(days=1),
                due_date,
                due_date + timedelta(days=1)
            ])

    reminders = []
    context_base = {
        "name": client_name,
        "amount": amount_str,
        "due_date": due_date.strftime("%b %d"),
        "link": link,
        "business_name": business_name,
        "invoice_id": invoice_ref
    }

    for trigger in triggers:
        if trigger < now - timedelta(days=30) or trigger > due_date + timedelta(days=7):
            continue

        days_until = (due_date - trigger).days
        days_over = (trigger - due_date).days

        # Select message type
        if days_over > 0:
            whatsapp_key = "few_days_over" if days_over >= 3 else "one_day_over"
            sms_key = "few_days_over" if days_over >= 3 else "one_day_over"
            email_type = "overdue_firm" if days_over >= 3 else "overdue_gentle"
        elif days_until == 0:
            whatsapp_key = "due_today_morning"
            sms_key = "due_today"
            email_type = "reminder_2"
        elif days_until == 1:
            whatsapp_key = "tomorrow"
            sms_key = "tomorrow"
            email_type = "reminder_2"
        else:
            whatsapp_key = "gentle_nudge"
            sms_key = "gentle"
            email_type = "reminder"

        context = context_base.copy()
        context["days"] = abs(days_over) if days_over > 0 else days_until

        whatsapp_msg = get_layla_whatsapp(whatsapp_key, context)
        sms_msg = get_layla_sms(sms_key, context)
        email_html = get_layla_email(email_type, context)
        email_subject = f"Reminder: {amount_str} due on {due_date.strftime('%b %d')}"

        # Save reminder
        rem = Reminder(
            _id=f"{invoice_id}_{int(trigger.timestamp())}",
            invoice_id=invoice_id,
            user_id=user_id,
            method=methods[0],
            message=sms_msg,
            next_send=trigger,
            status="pending",
            active=True,
            channel_used=None
        )
        db.collection("reminders").document(rem.id).set(rem.dict(by_alias=True))
        reminders.append(rem)

        # Immediate send if trigger is now/past
        if trigger <= now + timedelta(minutes=5):
            await send_if_allowed(methods, invoice, whatsapp_msg, sms_msg, email_subject, email_html)

    return reminders
