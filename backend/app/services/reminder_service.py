# app/services/reminder_service.py
"""
Reminder helpers shared by the reminder loop, the invoice router, and
the reminder router.

This module no longer sends reminders itself. All dispatch happens in
app/tasks/reminder_service_loop.py, which owns locking, channel
tracking, and quiet-hours deferral. This module provides:

  - Layla's message helpers for WhatsApp, SMS, and email.
  - map_templates(), which resolves a reminder trigger to the correct
    Layla stage.
  - schedule_reminders_for_invoice(), which creates the reminder
    documents when an invoice is published.

Public functions:
    get_layla_whatsapp, get_layla_sms, get_layla_email
    is_within_quiet_hours
    map_templates
    schedule_reminders_for_invoice
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from app.core.firebase import db
from app.core.reminder_config import (
    get_delivery_hour_utc,
    get_quiet_hours_utc,
)
from app.models.reminder_model import Reminder, ReminderCreate
from app.utils.invoice_reminder_templates import render_invoice_reminder
from app.utils.sms_layla import SMS_LAYLA
from app.utils.whatsapp_layla import WHATSAPP_MESSAGES

logger = logging.getLogger("payla")

DELIVERY_HOUR_UTC = get_delivery_hour_utc("WAT")
QUIET_START_UTC, QUIET_END_UTC = get_quiet_hours_utc("WAT")


# ---------------------------
# Layla's message helpers
# ---------------------------

def get_layla_whatsapp(key: str, context: Dict[str, Any]) -> str:
    template = WHATSAPP_MESSAGES.get(
        key, WHATSAPP_MESSAGES["gentle_nudge"]
    )
    try:
        return template.format(**context)
    except KeyError:
        return (
            f"Hi! Layla here. Your invoice for "
            f"{context.get('business_name', 'your project')} is ready: "
            f"{context.get('link', '')}"
        )


def get_layla_sms(key: str, context: Dict[str, Any]) -> str:
    """
    Render the SMS for a stage. Truncated to 160 characters to stay
    within a single GSM-7 segment.
    """
    template = SMS_LAYLA.get(key, SMS_LAYLA["gentle"])
    try:
        return template.format(**context)[:160]
    except KeyError:
        return (
            f"Hi, Layla from Payla. Your payment is due. "
            f"{context.get('link', '')}"
        )[:160]


def get_layla_email(email_type: str, context: dict) -> str:
    """
    Render a client-facing invoice reminder through the shared email
    design system. Returns a complete HTML document.
    """
    return render_invoice_reminder(email_type, context)


# ---------------------------
# Quiet hours
# ---------------------------

def is_within_quiet_hours(now: datetime) -> bool:
    """
    Return True when the given UTC time falls inside the configured
    quiet window. Hours come from app.core.reminder_config and are
    the single source of truth for the entire reminder system.
    """
    if QUIET_START_UTC > QUIET_END_UTC:
        return now.hour >= QUIET_START_UTC or now.hour < QUIET_END_UTC
    return QUIET_START_UTC <= now.hour < QUIET_END_UTC


# ---------------------------
# Stage mapping
# ---------------------------

def map_templates(
    trigger: datetime,
    due_date: datetime,
    context: dict,
    is_first: bool = False,
):
    """
    Resolve a reminder trigger to Layla's stage keys.

    Returns a tuple (whatsapp_key, sms_key, email_type).

    The stage depends on how far the trigger sits relative to the due
    date, and whether this is the first-ever reminder for a returning
    client. Every returned key exists in the corresponding template
    maps: WHATSAPP_MESSAGES, SMS_LAYLA, and invoice_reminder_templates.
    """
    now = datetime.utcnow().replace(tzinfo=timezone.utc)

    # Default stage. Prevents UnboundLocalError and gives every branch
    # a sane baseline.
    whatsapp_key = "gentle_nudge"
    sms_key = "gentle"
    email_type = "reminder"

    # First-ever contact for a new client, fired within ten minutes of
    # scheduling. Uses the intro copy.
    time_since_trigger = abs((now - trigger).total_seconds())
    if is_first and time_since_trigger < 600:
        return "first_invoice", "first", "first_contact"

    trigger_date = trigger.date()
    due_date_only = due_date.date()

    days_diff = (due_date_only - trigger_date).days
    days_over = (trigger_date - due_date_only).days

    if days_diff == 1:
        whatsapp_key = "tomorrow"
        sms_key = "tomorrow"
        email_type = "reminder_2"

    elif days_diff == 0:
        whatsapp_key = (
            "due_today_evening" if now.hour >= 14 else "due_today_morning"
        )
        sms_key = "due_today"
        email_type = "due_today"

    elif days_over == 1:
        whatsapp_key = "one_day_over"
        sms_key = "one_day_over"
        email_type = "overdue_gentle"

    elif 3 <= days_over < 7:
        whatsapp_key = "few_days_over"
        sms_key = "few_days_over"
        email_type = "overdue_firm"

    elif days_over >= 7:
        whatsapp_key = "few_days_over"
        sms_key = "final_nudge"
        email_type = "overdue_firm"

    else:
        # Any trigger 2, 4, 5, or 6 days out from the due date falls
        # back to the gentle stage.
        whatsapp_key = "gentle_nudge"
        sms_key = "gentle"
        email_type = "reminder"

    return whatsapp_key, sms_key, email_type


# ---------------------------
# Scheduling
# ---------------------------

async def schedule_reminders_for_invoice(
    invoice_id: str,
    payload: ReminderCreate,
    user_id: str,
) -> List[Reminder]:
    """
    Create reminder documents for an invoice.

    Offsets are relative to the invoice due date and set to the
    configured delivery hour. Only future triggers are kept. Each
    reminder carries an INTRO_REQUIRED or STANDARD_REMINDER flag in
    its message field so the loop knows whether to use Layla's intro.
    """
    logger.info(
        "[%s] Scheduling reminders for invoice %s",
        datetime.utcnow().isoformat(),
        invoice_id,
    )

    inv_doc = db.collection("invoices").document(invoice_id).get()
    if not inv_doc.exists:
        logger.error("Invoice %s not found", invoice_id)
        raise ValueError("Invoice not found")

    invoice = inv_doc.to_dict() or {}

    if invoice.get("status") == "draft":
        await asyncio.sleep(0.5)
        invoice = (
            db.collection("invoices").document(invoice_id).get().to_dict()
            or {}
        )
        if invoice.get("status") == "draft":
            logger.warning(
                "Cannot schedule reminders for draft invoice %s",
                invoice_id,
            )
            raise ValueError("Cannot schedule reminders for draft invoice")

    due_date = invoice.get("due_date")
    if isinstance(due_date, str):
        due_date = datetime.fromisoformat(due_date).replace(
            tzinfo=timezone.utc
        )
    elif isinstance(due_date, datetime):
        due_date = due_date.replace(tzinfo=timezone.utc)
    else:
        raise ValueError("Invoice has no valid due date")

    phone = invoice.get("client_phone")
    email = invoice.get("client_email")

    channels: List[str] = []
    if payload.method_priority:
        for ch in payload.method_priority:
            if ch in ("whatsapp", "sms") and phone:
                channels.append(ch)
            elif ch == "email" and email:
                channels.append("email")

    if not channels:
        logger.warning(
            "No valid channels selected for %s, skipping", invoice_id
        )
        return []

    # Return-client detection. If this sender has sent this client two
    # or more invoices before, they are returning.
    is_globally_new = True

    if email:
        existing = (
            db.collection("invoices")
            .where("sender_id", "==", user_id)
            .where("client_email", "==", email)
            .limit(2)
            .get()
        )
        if len(existing) > 1:
            is_globally_new = False
    elif phone:
        existing = (
            db.collection("invoices")
            .where("sender_id", "==", user_id)
            .where("client_phone", "==", phone)
            .limit(2)
            .get()
        )
        if len(existing) > 1:
            is_globally_new = False

    triggers: List[datetime] = []
    now = datetime.utcnow().replace(tzinfo=timezone.utc)

    if payload.manual_dates:
        logger.info("Using manual dates: %s", payload.manual_dates)
        for dt_str in payload.manual_dates:
            try:
                dt = datetime.fromisoformat(
                    dt_str.replace("Z", "+00:00")
                ).replace(tzinfo=timezone.utc)
                if dt > now:
                    triggers.append(dt)
            except Exception as exc:
                logger.warning("Invalid manual date %s: %s", dt_str, exc)
    else:
        preset = payload.preset or "standard"

        if preset == "gentle":
            offsets = [3, 0]
        elif preset == "aggressive":
            offsets = [4, 3, 2, 1, 0]
        else:
            offsets = [3, 1, 0, -1]

        for offset in offsets:
            reminder_date = due_date - timedelta(days=offset)
            reminder_date = reminder_date.replace(
                hour=DELIVERY_HOUR_UTC,
                minute=0,
                second=0,
                microsecond=0,
            )
            if reminder_date > now:
                triggers.append(reminder_date)

    triggers = sorted(set(triggers))

    if not triggers:
        logger.warning("No future reminder triggers for %s", invoice_id)
        return []

    reminders: List[Reminder] = []

    for trigger in triggers:
        intro_flag = (
            "INTRO_REQUIRED"
            if (is_globally_new and trigger == triggers[0])
            else "STANDARD_REMINDER"
        )

        rem = Reminder(
            _id=f"{invoice_id}_{int(trigger.timestamp())}",
            invoice_id=invoice_id,
            user_id=user_id,
            channels_selected=channels,
            channel_used=[],
            message=getattr(payload, "custom_message", "") or intro_flag,
            next_send=trigger,
            status="pending",
            active=True,
        )

        db.collection("reminders").document(rem.id).set(
            rem.dict(by_alias=True)
        )
        reminders.append(rem)

    logger.info(
        "Scheduled %d reminders. Intro required: %s",
        len(reminders),
        is_globally_new,
    )
    return reminders