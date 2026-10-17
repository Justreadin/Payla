# app/tasks/reminder_service_loop.py
"""
Reminder worker.

Runs once per minute. Finds reminders whose next_send is due, sends
them across the client's selected channels, and tracks per-channel
delivery.

Reliability guarantees:
  - Per-reminder lock with a 10-minute timeout, so a crashed worker
    does not strand a reminder forever.
  - Quiet-hours deferral: a reminder due during the quiet window is
    rescheduled to the next quiet-hours exit instead of sleeping
    in-process. No infinite loops, no long-lived tasks.
  - Bounded retries per channel. After MAX_RETRIES the channel is
    reported as failed and the reminder stays pending for a future
    cycle.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.firebase import db
from app.core.reminder_config import get_quiet_hours_utc
from app.models.reminder_model import Reminder
from app.services.channels import (
    send_via_email,
    send_via_sms,
    send_via_whatsapp,
)
from app.services.reminder_service import (
    get_layla_email,
    get_layla_sms,
    get_layla_whatsapp,
    map_templates,
)
from app.utils.email_render import render_email
from app.utils.email_render.components import (
    button,
    eyebrow,
    heading,
    paragraph,
    sign_off,
)
from app.core.config import settings
from app.utils.invoice_reminder_templates import get_invoice_subject

logger = logging.getLogger("payla.reminders")

CHECK_INTERVAL = settings.REMINDER_CHECK_INTERVAL_SECONDS
MAX_RETRIES = settings.REMINDER_MAX_RETRIES
RETRY_INTERVAL = settings.REMINDER_RETRY_INTERVAL_SECONDS
LOCK_TIMEOUT = timedelta(minutes=settings.REMINDER_LOCK_TIMEOUT_MINUTES)

QUIET_START_UTC, QUIET_END_UTC = get_quiet_hours_utc("WAT")


# ---------------------------
# Time helpers
# ---------------------------

def _utcnow() -> datetime:
    return datetime.utcnow().replace(tzinfo=timezone.utc)


def is_within_quiet_hours(now: datetime) -> bool:
    """
    Return True when `now` (UTC) falls inside the configured quiet
    window. Hours come from reminder_config and match the values used
    by reminder_service.is_within_quiet_hours.
    """
    if QUIET_START_UTC > QUIET_END_UTC:
        return now.hour >= QUIET_START_UTC or now.hour < QUIET_END_UTC
    return QUIET_START_UTC <= now.hour < QUIET_END_UTC


def _next_quiet_exit(now: datetime) -> datetime:
    """
    Return the UTC datetime at which the current quiet window ends.

    If quiet hours span midnight, the exit is either today's
    QUIET_END_UTC (when now is past midnight and before the exit) or
    tomorrow's QUIET_END_UTC. Otherwise it is today's QUIET_END_UTC.
    """
    if QUIET_START_UTC > QUIET_END_UTC:
        if now.hour < QUIET_END_UTC:
            return now.replace(
                hour=QUIET_END_UTC, minute=0, second=0, microsecond=0
            )
        tomorrow = now + timedelta(days=1)
        return tomorrow.replace(
            hour=QUIET_END_UTC, minute=0, second=0, microsecond=0
        )

    return now.replace(
        hour=QUIET_END_UTC, minute=0, second=0, microsecond=0
    )


# ---------------------------
# Locking
# ---------------------------

def acquire_reminder_lock(reminder_id: str) -> bool:
    ref = db.collection("reminders").document(reminder_id)

    @firestore.transactional
    def txn(transaction):
        snap = ref.get(transaction=transaction)
        data = snap.to_dict() or {}

        locked = data.get("locked", False)
        locked_at = data.get("locked_at")

        if locked and locked_at:
            if locked_at.tzinfo is None:
                locked_at = locked_at.replace(tzinfo=timezone.utc)
            if _utcnow() - locked_at < LOCK_TIMEOUT:
                return False

        transaction.update(ref, {
            "locked": True,
            "locked_at": _utcnow(),
        })
        return True

    return txn(db.transaction())


def release_reminder_lock(reminder_id: str) -> None:
    db.collection("reminders").document(reminder_id).update({
        "locked": False,
        "locked_at": None,
    })


# ---------------------------
# Sending
# ---------------------------

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
    Send via a single channel with bounded retries.

    Quiet hours are handled by the caller, not here. If a retry lands
    inside quiet hours, the send still attempts — the caller's job is
    to defer the whole reminder before we get here.
    """
    attempt = 0

    while attempt < max_retries:
        try:
            if method == "whatsapp" and invoice.get("client_phone"):
                logger.info(
                    "[%s] attempt %d/%d phone=%s",
                    method, attempt + 1, max_retries,
                    invoice["client_phone"],
                )
                await send_via_whatsapp(invoice["client_phone"], msg)

            elif method == "sms" and invoice.get("client_phone"):
                logger.info(
                    "[%s] attempt %d/%d phone=%s",
                    method, attempt + 1, max_retries,
                    invoice["client_phone"],
                )
                await send_via_sms(invoice["client_phone"], msg)

            elif method == "email" and invoice.get("client_email"):
                logger.info(
                    "[%s] attempt %d/%d email=%s",
                    method, attempt + 1, max_retries,
                    invoice["client_email"],
                )
                await send_via_email(
                    invoice["client_email"],
                    subject,
                    html,
                    email_type=email_type,
                )

            else:
                # No recipient on this channel; treat as a skip, not
                # a failure.
                logger.info("[%s] no recipient, skipping", method)
                return True

            logger.info("[%s] success", method)
            return True

        except Exception as exc:
            attempt += 1
            logger.error(
                "[%s] attempt %d/%d failed: %s",
                method, attempt, max_retries, exc,
            )
            if attempt < max_retries:
                await asyncio.sleep(RETRY_INTERVAL)

    logger.error("[%s] all %d attempts failed", method, max_retries)
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
) -> None:
    """
    Send via one channel and update per-channel tracking in Firestore.
    Channels run independently in parallel; each records its own
    success or failure.
    """
    if ch in rem.channel_used:
        logger.info("[%s] already sent for %s, skipping", ch, rem.id)
        return

    logger.info("[%s] starting send for %s", ch, rem.id)

    if ch == "whatsapp":
        payload = whatsapp_msg
    elif ch == "sms":
        payload = sms_msg
    else:
        payload = ""

    success = await send_single_channel(
        ch,
        invoice,
        payload,
        email_subject,
        email_html if ch == "email" else None,
        email_type=email_type,
    )

    if not success:
        logger.error("[%s] failed for %s", ch, rem.id)
        return

    try:
        ref = db.collection("reminders").document(rem.id)

        @firestore.transactional
        def update_channel(transaction):
            snap = ref.get(transaction=transaction)
            data = snap.to_dict() or {}

            channel_used = data.get("channel_used", [])
            if ch not in channel_used:
                channel_used.append(ch)

            status = (
                "sent"
                if set(channel_used) == set(all_channels)
                else "pending"
            )

            transaction.update(ref, {
                "channel_used": channel_used,
                "status": status,
                "sent_at": _utcnow(),
            })

        await asyncio.to_thread(update_channel, db.transaction())
        logger.info("[%s] marked as sent for %s", ch, rem.id)

    except Exception as exc:
        logger.error("[%s] Firestore update failed: %s", ch, exc)


# ---------------------------
# Custom-message wrapper
# ---------------------------

def _build_custom_message_email(
    custom_msg: str,
    link: str,
    business_name: str,
) -> str:
    """
    Wrap a creator-written reminder in the shared email design system.
    """
    return render_email(
        title=f"Message from {business_name}",
        blocks=[
            eyebrow(business_name),
            heading("A note about your invoice.", size="22px"),
            paragraph(custom_msg.replace("\n", "<br>")),
            button("View and pay", link),
            sign_off("Talk soon."),
        ],
    )


# ---------------------------
# Main worker
# ---------------------------

async def process_reminder(rem: Reminder) -> None:
    if not acquire_reminder_lock(rem.id):
        logger.info("Reminder %s already locked, skipping", rem.id)
        return

    try:
        # Quiet-hours deferral happens before we do any work.
        now = _utcnow()
        if is_within_quiet_hours(now):
            next_send = _next_quiet_exit(now)
            logger.info(
                "Reminder %s deferred past quiet hours to %s",
                rem.id, next_send.isoformat(),
            )
            await asyncio.to_thread(
                db.collection("reminders").document(rem.id).update,
                {"next_send": next_send, "updated_at": _utcnow()},
            )
            return

        reminder_ref = db.collection("reminders").document(rem.id)

        # 1. Invoice
        invoice_doc = await asyncio.to_thread(
            db.collection("invoices").document(rem.invoice_id).get
        )
        if not invoice_doc.exists:
            await asyncio.to_thread(reminder_ref.delete)
            return

        invoice = invoice_doc.to_dict() or {}

        if invoice.get("status") == "paid":
            logger.info(
                "Invoice %s paid. Deleting reminder %s",
                rem.invoice_id, rem.id,
            )
            await asyncio.to_thread(reminder_ref.delete)
            return

        # 2. Creator branding
        sender_id = invoice.get("sender_id")
        user_doc = await asyncio.to_thread(
            db.collection("users").document(sender_id).get
        )
        user_data = user_doc.to_dict() if user_doc.exists else {}

        biz_display_name = (
            user_data.get("business_name")
            or user_data.get("full_name")
            or "Your Provider"
        )

        # 3. Context
        amount = f"\u20a6{invoice.get('amount', 0):,}"

        raw_link = invoice.get("invoice_url", "")
        clean_link = (
            raw_link
            if raw_link.startswith("http")
            else f"https://payla.ng/{raw_link.lstrip('/')}"
        )

        due_date = invoice.get("due_date")
        if isinstance(due_date, str):
            try:
                due_date = datetime.fromisoformat(due_date).replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                due_date = None

        due_str = (
            due_date.strftime("%d %B %Y") if due_date else "N/A"
        )

        context = {
            "business_name": biz_display_name,
            "amount": amount,
            "due_date": due_str,
            "link": clean_link,
            "day_of_week": now.strftime("%A"),
        }

        # 4. Stage
        is_intro_needed = rem.message == "INTRO_REQUIRED"

        if is_intro_needed:
            whatsapp_key = "first_invoice"
            sms_key = "first"
            email_type = "first_contact"
        else:
            whatsapp_key, sms_key, email_type = map_templates(
                rem.next_send,
                due_date or now,
                context,
            )
            if email_type == "first_contact":
                email_type = "reminder"

        # 5. Content
        custom_msg = (
            rem.message
            if rem.message not in ("INTRO_REQUIRED", "STANDARD_REMINDER")
            else None
        )

        if sms_key == "first" and not custom_msg:
            from app.utils.sms_layla import SMS_LAYLA
            sms_msg = (
                SMS_LAYLA["first"].format(**context)
                + f" View invoice: {clean_link}"
            )[:160]
        else:
            sms_msg = custom_msg or get_layla_sms(sms_key, context)

        whatsapp_msg = custom_msg or get_layla_whatsapp(
            whatsapp_key, context
        )

        if custom_msg:
            email_html = _build_custom_message_email(
                custom_msg=custom_msg,
                link=clean_link,
                business_name=biz_display_name,
            )
            email_subject = f"Message from {biz_display_name}"
        else:
            email_html = get_layla_email(
                email_type,
                {
                    "business_name": biz_display_name,
                    "amount": amount,
                    "due_date": due_str,
                    "link": clean_link,
                    "day_of_week": context["day_of_week"],
                },
            )
            email_subject = get_invoice_subject(
                email_type, biz_display_name
            )

        # 6. Dispatch
        selected_channels = rem.channels_selected or []
        final_channels = [
            ch for ch in selected_channels
            if (
                (ch in ("whatsapp", "sms") and invoice.get("client_phone"))
                or (ch == "email" and invoice.get("client_email"))
            )
        ]

        if not final_channels:
            await asyncio.to_thread(reminder_ref.delete)
            return

        await asyncio.gather(
            *[
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
            ],
            return_exceptions=True,
        )

        # 7. Cleanup if all channels are done
        final_snap = await asyncio.to_thread(reminder_ref.get)
        if final_snap.exists:
            if final_snap.to_dict().get("status") == "sent":
                logger.info("Deleting completed reminder %s", rem.id)
                await asyncio.to_thread(reminder_ref.delete)

    except Exception:
        logger.exception("Error processing reminder %s", rem.id)
    finally:
        release_reminder_lock(rem.id)


async def reminder_loop() -> None:
    logger.info("Reminder loop started")

    while True:
        now = _utcnow()

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

            if pending_docs:
                logger.info(
                    "Found %d pending reminders", len(pending_docs)
                )

            tasks = []
            for doc in pending_docs:
                data = doc.to_dict()
                data["id"] = doc.id
                tasks.append(process_reminder(Reminder(**data)))

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        except Exception:
            logger.exception("Reminder loop error")

        await asyncio.sleep(CHECK_INTERVAL)