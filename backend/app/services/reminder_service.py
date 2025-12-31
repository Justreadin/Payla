# services/reminder_service.py
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import logging
from app.models.reminder_model import Reminder, ReminderCreate
from app.core.firebase import db
from app.services.channels import send_via_whatsapp, send_via_sms, send_via_email
from app.utils.email import generate_email_content
from app.utils.whatsapp_layla import WHATSAPP_MESSAGES
from app.utils.sms_layla import SMS_LAYLA
from app.core.reminder_config import get_delivery_hour_utc, get_quiet_hours_utc

logger = logging.getLogger("payla")
logger.setLevel(logging.INFO)

DELIVERY_HOUR_UTC = get_delivery_hour_utc("WAT")
QUIET_START_UTC, QUIET_END_UTC = get_quiet_hours_utc("WAT")

# ---------------------------
# Template helpers
# ---------------------------
def get_layla_whatsapp(key: str, context: Dict[str, Any]) -> str:
    return WHATSAPP_MESSAGES.get(key, WHATSAPP_MESSAGES["gentle_nudge"]).format(**context)


def get_layla_sms(key: str, context: Dict[str, Any]) -> str:
    return SMS_LAYLA.get(key, SMS_LAYLA["gentle"]).format(**context)[:160]


def get_layla_email(email_type: str, context: dict, use_html: bool = True) -> str:
    return generate_email_content(email_type, context, use_html=use_html)


def is_within_quiet_hours(now: datetime, start_hour: int = None, end_hour: int = None) -> bool:
    """Check if current time is within quiet hours (uses WAT timezone by default)"""
    if start_hour is None:
        start_hour = QUIET_START_UTC
    if end_hour is None:
        end_hour = QUIET_END_UTC
    
    # Handle case where quiet hours span midnight
    if start_hour > end_hour:
        return now.hour >= start_hour or now.hour < end_hour
    else:
        return start_hour <= now.hour < end_hour

# ---------------------------
# Send messages with retry
# ---------------------------
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
        logger.info(f"[{now.isoformat()}] Quiet hours: delaying sends for invoice {invoice.get('invoice_id')}")
        return

    for method in methods:
        try:
            if method == "whatsapp" and invoice.get("client_phone"):
                logger.info(f"[{now.isoformat()}] Sending WhatsApp to {invoice['client_phone']}")
                await send_via_whatsapp(invoice["client_phone"], whatsapp_msg)

            elif method == "sms" and invoice.get("client_phone"):
                logger.info(f"[{now.isoformat()}] Sending SMS to {invoice['client_phone']}")
                await send_via_sms(invoice["client_phone"], sms_msg)

            elif method == "email" and invoice.get("client_email"):
                logger.info(f"[{now.isoformat()}] Sending Email to {invoice['client_email']} type: {email_type}")
                result = await send_via_email(invoice["client_email"], email_subject, email_html, email_type=email_type)
                logger.info(f"[{now.isoformat()}] Email send result: {result}")

        except Exception as e:
            logger.error(f"[{now.isoformat()}] Failed to send {method} for invoice {invoice.get('invoice_id')}: {e}")


# ---------------------------
# Map trigger → templates
# ---------------------------
def map_templates(trigger: datetime, due_date: datetime, context: dict, is_first: bool = False):
    """
    Maps a reminder trigger to specific Layla persona keys.
    """
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    
    # 1. INITIALIZE DEFAULTS (Prevents UnboundLocalError)
    whatsapp_key = "gentle_nudge"
    sms_key = "gentle"
    email_type = "reminder"

    # 2. IMMEDIATE FIRST CONTACT
    # Only send intro if it's the first reminder AND triggered within 10 mins of creation
    time_since_trigger = abs((now - trigger).total_seconds())
    if is_first and time_since_trigger < 600:
        return "first_invoice", "first", "first_contact"

    # Calculate date-based deltas
    # We use .date() to avoid hour/minute discrepancies
    trigger_date = trigger.date()
    due_date_only = due_date.date()
    
    days_diff = (due_date_only - trigger_date).days
    days_over = (trigger_date - due_date_only).days

    # 3. SPECIFIC LOGIC GATES
    if days_diff == 1:
        whatsapp_key, sms_key, email_type = "tomorrow", "tomorrow", "reminder_2"
        
    elif days_diff == 0:
        # Evening check-in after 3 PM WAT (14:00 UTC)
        whatsapp_key = "due_today_evening" if now.hour >= 14 else "due_today_morning"
        sms_key, email_type = "due_today", "due_today"
        
    elif days_over == 1:
        whatsapp_key, sms_key, email_type = "one_day_over", "one_day_over", "overdue_gentle"
        
    elif 3 <= days_over < 7:
        whatsapp_key, sms_key, email_type = "few_days_over", "few_days_over", "overdue_firm"
        
    elif days_over >= 7:
        whatsapp_key, sms_key, email_type = "few_days_over", "final_nudge", "overdue_firm"
        
    else:
        # FALLBACK: If it's 2 days before, 4 days before, etc.
        # This ensures the variables ALWAYS have a value.
        whatsapp_key, sms_key, email_type = "gentle_nudge", "gentle", "reminder"

    return whatsapp_key, sms_key, email_type

# ---------------------------
# Send reminder to all user-selected channels with retries
# ---------------------------
async def send_reminder_to_all_channels(rem: Reminder, invoice: dict, context: dict, channels: list):
    # --- STEP A: Determine if this is the first contact EVER for this client/business pair ---
    is_first_contact = False
    
    # 1. Get all reminders for this invoice to see if this is the 'Initial' one
    all_rem_docs = db.collection("reminders").where("invoice_id", "==", rem.invoice_id).get()
    reminders_list = sorted([d.to_dict() for d in all_rem_docs], key=lambda x: x['next_send'])
    
    if reminders_list and reminders_list[0]['id'] == rem.id:
        # 2. Check if this client has ever received a 'paid' or 'sent' invoice from THIS business before
        # This prevents repeat clients from getting the Layla intro every time.
        previous_invoices = db.collection("invoices")\
            .where("sender_id", "==", invoice.get("sender_id"))\
            .where("client_email", "==", invoice.get("client_email"))\
            .limit(2).get()
        
        # If count is 1, this is their first invoice from this business
        if len(previous_invoices) <= 1:
            is_first_contact = True

    # --- STEP B: Map Templates with the calculated is_first flag ---
    whatsapp_key, sms_key, email_type = map_templates(
        rem.next_send, 
        context.get("due_date_dt", datetime.utcnow()), 
        context,
        is_first=is_first_contact
    )

    async def try_send(ch: str):
        if ch in rem.channel_used:
            return

        retry_count = 0
        max_retries = 3
        success = False

        while not success and retry_count < max_retries:
            now = datetime.utcnow().replace(tzinfo=timezone.utc)
            if is_within_quiet_hours(now):
                await asyncio.sleep(60)
                continue

            try:
                if ch == "whatsapp" and invoice.get("client_phone"):
                    msg = rem.message or get_layla_whatsapp(whatsapp_key, context)
                    await send_via_whatsapp(invoice["client_phone"], msg)

                elif ch == "sms" and invoice.get("client_phone"):
                    msg = rem.message or get_layla_sms(sms_key, context)
                    await send_via_sms(invoice["client_phone"], msg)

                elif ch == "email" and invoice.get("client_email"):
                    # Dynamic Subject based on Layla's Meta
                    from app.utils.email import METADATA
                    subject = METADATA.get(email_type, {}).get("title", "Invoice Reminder")
                    html = rem.message or get_layla_email(email_type, context)
                    await send_via_email(invoice["client_email"], subject, html, email_type=email_type)

                success = True
                rem.channel_used.append(ch)
                db.collection("reminders").document(rem.id).update({
                    "channel_used": rem.channel_used,
                    "status": "sent" if set(rem.channel_used) == set(channels) else "pending",
                    "sent_at": datetime.utcnow().replace(tzinfo=timezone.utc)
                })

            except Exception as e:
                logger.error(f"Failed {ch} send: {e}")
                retry_count += 1
                await asyncio.sleep(5)

    await asyncio.gather(*(try_send(ch) for ch in channels))


# ---------------------------
# Schedule reminders for invoice (user-selected channels only)
# ---------------------------
async def schedule_reminders_for_invoice(invoice_id: str, payload: ReminderCreate, user_id: str) -> List[Reminder]:
    logger.info(f"[{datetime.utcnow().isoformat()}] Scheduling reminders for invoice {invoice_id}")

    inv_doc = db.collection("invoices").document(invoice_id).get()
    if not inv_doc.exists:
        logger.error(f"Invoice {invoice_id} not found in DB")
        raise ValueError("Invoice not found")
    invoice = inv_doc.to_dict()

    if invoice.get("status") == "draft":
        await asyncio.sleep(0.5)
        invoice = db.collection("invoices").document(invoice_id).get().to_dict()
        if invoice.get("status") == "draft":
            logger.warning(f"Cannot schedule reminders for draft invoice {invoice_id}")
            raise ValueError("Cannot schedule reminders for draft invoice")

    due_date = invoice["due_date"]
    if isinstance(due_date, str):
        due_date = datetime.fromisoformat(due_date).replace(tzinfo=timezone.utc)
    elif isinstance(due_date, datetime):
        due_date = due_date.replace(tzinfo=timezone.utc)

    phone = invoice.get("client_phone")
    email = invoice.get("client_email")

    # ---------------------------
    # Determine channels strictly from user selection
    # ---------------------------
    channels: List[str] = []
    if payload.method_priority:
        for ch in payload.method_priority:
            if ch in ["whatsapp", "sms"] and phone:
                channels.append(ch)
            elif ch == "email" and email:
                channels.append("email")

    if not channels:
        logger.warning(f"No valid channels selected for invoice {invoice_id}, skipping reminder scheduling.")
        return []

    # ---------------------------
    # 🔥 FIXED: Determine reminder triggers based on user selection
    # ---------------------------
    triggers: List[datetime] = []
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    triggers.append(now) 

    if payload.manual_dates:
        # User provided specific dates
        logger.info(f"Using manual dates: {payload.manual_dates}")
        for dt_str in payload.manual_dates:
            try:
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
                if dt > now:  # Only future dates
                    triggers.append(dt)
                else:
                    logger.warning(f"Manual date {dt_str} is in the past, skipping")
            except Exception as e:
                logger.warning(f"Invalid manual date {dt_str} for invoice {invoice_id}: {e}")
    else:
        # Use preset
        preset = payload.preset or "standard"
        logger.info(f"Using preset: {preset}")
        
        # Calculate time until due date
        days_until_due = (due_date.date() - now.date()).days
        
        if preset == "gentle":
            # Single reminder 3 days before (or ASAP if less than 3 days)
            if days_until_due >= 3:
                reminder_date = due_date - timedelta(days=3)
                reminder_date = reminder_date.replace(hour=DELIVERY_HOUR_UTC, minute=0, second=0, microsecond=0)
                triggers.append(reminder_date)
            else:
                # Invoice due soon, send immediately
                triggers.append(now + timedelta(minutes=1))
                
        elif preset == "aggressive":
            # Multiple reminders: 4, 3, 2, 1 days before, and on due date
            for days_before in [4, 3, 2, 1, 0]:
                reminder_date = due_date - timedelta(days=days_before)
                reminder_date = reminder_date.replace(hour=DELIVERY_HOUR_UTC, minute=0, second=0, microsecond=0)
                
                if reminder_date > now:
                    triggers.append(reminder_date)
                elif days_before == 0 and reminder_date.date() >= now.date():
                    # Due date is today but time has passed, send immediately
                    triggers.append(now + timedelta(minutes=1))
                    
        else:  # standard
            # 3 days before, 1 day before, due date, 1 day after
            standard_offsets = [3, 1, 0, -1]  # negative = days AFTER due
            
            for offset in standard_offsets:
                reminder_date = due_date - timedelta(days=offset)
                # Set to 10 AM WAT (9 AM UTC)
                reminder_date = reminder_date.replace(hour=DELIVERY_HOUR_UTC, minute=0, second=0, microsecond=0)
                
                # Only schedule if it's in the future
                if reminder_date > now:
                    triggers.append(reminder_date)
                elif offset <= 0 and reminder_date.date() >= now.date():
                    # Due date or overdue reminders - if today, send immediately
                    triggers.append(now + timedelta(minutes=1))

    # Remove duplicates and sort
    triggers = sorted(list(set(triggers)))
    
    if not triggers:
        logger.warning(f"No valid reminder triggers generated for invoice {invoice_id}")
        return []

    logger.info(f"Generated {len(triggers)} reminder triggers: {[t.isoformat() for t in triggers]}")
    logger.info(f"🕐 Reminders will be delivered at 10:00 AM WAT (9:00 AM UTC)")
    logger.info(f"🌙 Quiet hours: 10:00 PM - 7:00 AM WAT (9:00 PM - 6:00 AM UTC)")

    reminders: List[Reminder] = []
    client_name = (invoice.get("client_name") or "there").split()[0]
    amount_str = f"₦{invoice.get('amount', 0):,}"
    link = invoice.get("invoice_url")
    business_name = invoice.get("business_name") or "Payla user"

    context_base = {
        "name": client_name,
        "amount": amount_str,
        "due_date": due_date.strftime("%b %d"),
        "due_date_dt": due_date,
        "link": link,
        "business_name": business_name,
        "invoice_id": invoice.get("invoice_id", invoice_id)
    }

    # ---------------------------
    # Create reminders
    # ---------------------------
    for trigger in triggers:
        rem = Reminder(
            _id=f"{invoice_id}_{int(trigger.timestamp())}",
            invoice_id=invoice_id,
            user_id=user_id, 
            channels_selected=channels,
            channel_used=[],
            message=getattr(payload, "custom_message", "") or "",
            next_send=trigger,
            status="pending",
            active=True
        )

        # Save reminder
        db.collection("reminders").document(rem.id).set(rem.dict(by_alias=True))
        reminders.append(rem)

    logger.info(f"✅ Scheduled {len(reminders)} reminders for invoice {invoice_id} with channels: {channels}")
    return reminders

# ---------------------------
# Payment success notification to the user
# ---------------------------
async def send_payment_success_notification(user: dict, invoice: dict):
    """
    Send payment success notification to the user (owner of the invoice)
    via WhatsApp and Email when a payment is received.
    """
    if not user:
        logger.warning("User info not provided, cannot send payment notification.")
        return

    name = user.get("name", "there")
    phone = user.get("phone")
    email = user.get("email")
    amount_str = f"₦{invoice.get('amount', 0):,}"
    invoice_id = invoice.get("invoice_id", "N/A")

    context = {
        "name": name,
        "amount": amount_str,
        "invoice_id": invoice_id
    }

    whatsapp_msg = get_layla_whatsapp("payment_received", context)
    sms_msg = get_layla_sms("paid", context)
    email_html = get_layla_email("payment_received", context)
    email_subject = f"Payment Received: {amount_str} for Invoice {invoice_id}"

    channels = []
    if phone:
        channels.append("whatsapp")
    if email:
        channels.append("email")

    if not channels:
        logger.warning(f"No valid channels for user {name}, skipping payment notification.")
        return

    logger.info(f"Sending payment success notification to user {name} for invoice {invoice_id}")
    
    # Send via each channel
    for method in channels:
        try:
            if method == "whatsapp":
                await send_via_whatsapp(phone, whatsapp_msg)
            elif method == "email":
                await send_via_email(email, email_subject, email_html, email_type="payment_received")
        except Exception as e:
            logger.error(f"Failed to send {method} payment notification: {e}")