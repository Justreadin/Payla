"""Subscription billing reminders for Payla.

Sends reminders only. Never activates, downgrades, or extends a
subscription; verified payment events own those transitions.

Three notice states, mapped exactly to core/subscription.py:

  1. active, not cancelling, ending soon -> silver_renewing_soon
  2. non_renewing / cancel_at_period_end -> silver_ending
  3. in_grace_period (renewal failed)    -> silver_grace_period
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta

from app.core.config import settings
from app.core.firebase import db
from app.core.subscription import (
    PAID_PLANS,
    VOLUNTARY_CANCELLATION_STATES,
    get_subscription_status,
    parse_firestore_datetime,
)
from app.services.billing_service import dispatch_billing_email
from app.utils.billing_templates import (
    render_silver_renewing_soon,
    render_silver_ending,
    render_silver_grace_period,
)

logger = logging.getLogger("payla.billing")

CHECK_INTERVAL = 3600
BILLING_SENDER = "billing.noreply@payla.vip"

RENEWAL_NOTICE_DAYS = 7
ENDING_NOTICE_DAYS = 7

NUDGE_ACTIVE = "active"
NUDGE_RENEWING_SENT = "renewing_soon_sent"
NUDGE_ENDING_SENT = "ending_sent"
NUDGE_GRACE_SENT = "grace_sent"


class _UserView:
    """
    Attribute view over a Firestore user document.

    core/subscription.py reads user.subscription_status, user.subscription_end,
    user.plan, user.cancel_at_period_end, and user.manual_silver_override.
    A raw dict has keys, not attributes, so getattr silently returns None.
    This wrapper exposes the attributes the entitlement module expects.
    """

    def __init__(self, data: dict):
        self.plan = str(data.get("plan") or "free").lower()
        self.subscription_status = str(
            data.get("subscription_status") or "inactive"
        ).lower()
        self.subscription_end = (
            data.get("subscription_end")
            or data.get("next_billing_date")
        )
        self.cancel_at_period_end = bool(
            data.get("cancel_at_period_end", False)
        )
        self.manual_silver_override = bool(
            data.get("manual_silver_override", False)
        )


def _billing_url() -> str:
    return f"{str(settings.APP_BASE_URL).rstrip('/')}/subscription"


def _plan_interval(user: dict) -> str:
    value = str(user.get("billing_cycle") or "monthly").lower()
    return "yearly" if value in {"yearly", "annually", "annual"} else "monthly"


def _plan_amount_ngn(user: dict) -> int:
    """Return the price the user pays, preferring locked founding prices."""
    try:
        if user.get("founding_price_locked") or user.get("founding_member_ever"):
            field = (
                "founding_yearly_price_ngn"
                if _plan_interval(user) == "yearly"
                else "founding_monthly_price_ngn"
            )
            value = user.get(field)
            if value is not None:
                return int(value)

        value = user.get("subscription_amount_ngn")
        if value is not None:
            return int(value)

    except (TypeError, ValueError):
        pass

    return 7500 if _plan_interval(user) == "monthly" else 75000


async def _record_nudge(user_id: str, new_status: str) -> None:
    try:
        db.collection("users").document(user_id).update({
            "billing_nudge_status": new_status,
            "last_nudge_date": datetime.now(timezone.utc),
        })
    except Exception:
        logger.exception(
            "Could not record billing nudge for user %s", user_id
        )


async def _send(user_id: str, user: dict, html: str, subject: str) -> bool:
    email = (user.get("email") or "").strip()

    if not email:
        logger.warning(
            "User %s has no email; billing email skipped", user_id
        )
        return False

    try:
        return await dispatch_billing_email(
            to_email=email,
            subject=subject,
            html=html,
            sender=BILLING_SENDER,
        )
    except Exception:
        logger.exception("Billing dispatch failed for user %s", user_id)
        return False


async def check_billing_status() -> None:
    """Scan paid users and fire at most one notice per user per cycle."""
    now = datetime.now(timezone.utc)

    for doc in db.collection("users").stream():
        user = doc.to_dict() or {}
        plan = str(user.get("plan") or "free").strip().lower()

        if plan not in PAID_PLANS:
            continue

        end = parse_firestore_datetime(
            user.get("subscription_end") or user.get("next_billing_date")
        )
        if end is None:
            # A paid user with no end date cannot be evaluated for
            # entitlement by core/subscription.py. Skip; never downgrade.
            continue

        view = _UserView(user)
        status = get_subscription_status(view)
        state = view.subscription_status
        nudge = str(
            user.get("billing_nudge_status") or NUDGE_ACTIVE
        ).lower()

        # A stored nudge from a previous period should not block a new
        # notice. If the last nudge predates the current period, reset.
        last_nudge = parse_firestore_datetime(user.get("last_nudge_date"))
        if last_nudge and last_nudge < end - timedelta(days=RENEWAL_NOTICE_DAYS):
            nudge = NUDGE_ACTIVE

        days_to_end = (end - now).days

        # ── State 3: in grace ──
        if status.get("in_grace_period"):
            if nudge != NUDGE_GRACE_SENT:
                days_left = int(status.get("days_left_in_grace") or 0)
                if days_left <= 0:
                    continue

                first_name = (user.get("full_name") or "Creator").split()[0]
                username = user.get("username") or "creator"

                html = render_silver_grace_period(
                    user_name=first_name,
                    name=username,
                    days_left=days_left,
                    billing_url=_billing_url(),
                )
                sent = await _send(
                    doc.id,
                    user,
                    html,
                    "Your Silver subscription needs attention",
                )
                if sent:
                    await _record_nudge(doc.id, NUDGE_GRACE_SENT)
            continue

        # From here, end > now. Neither "ending soon" state applies if the
        # end date is further out than the notice window.
        if days_to_end > ENDING_NOTICE_DAYS:
            continue

        # ── State 2: voluntary cancellation ──
        cancelling = bool(user.get("cancel_at_period_end")) or (
            state in VOLUNTARY_CANCELLATION_STATES
        )
        if cancelling:
            if nudge != NUDGE_ENDING_SENT:
                first_name = (user.get("full_name") or "Creator").split()[0]
                username = user.get("username") or "creator"

                html = render_silver_ending(
                    user_name=first_name,
                    name=username,
                    days_remaining=max(days_to_end, 1),
                    billing_url=_billing_url(),
                )
                sent = await _send(
                    doc.id,
                    user,
                    html,
                    f"Your Silver ends in {max(days_to_end, 1)} days",
                )
                if sent:
                    await _record_nudge(doc.id, NUDGE_ENDING_SENT)
            continue

        # ── State 1: active, not cancelling ──
        if state == "active" and nudge == NUDGE_ACTIVE:
            first_name = (user.get("full_name") or "Creator").split()[0]
            username = user.get("username") or "creator"

            html = render_silver_renewing_soon(
                user_name=first_name,
                name=username,
                days_remaining=max(days_to_end, 1),
                billing_url=_billing_url(),
                amount_ngn=_plan_amount_ngn(user),
                interval=_plan_interval(user),
            )
            sent = await _send(
                doc.id,
                user,
                html,
                f"Your Silver renews in {max(days_to_end, 1)} days",
            )
            if sent:
                await _record_nudge(doc.id, NUDGE_RENEWING_SENT)


async def billing_service_loop() -> None:
    logger.info("Payla billing reminder loop started")

    while True:
        try:
            await check_billing_status()
        except asyncio.CancelledError:
            logger.info("Payla billing reminder loop cancelled")
            raise
        except Exception:
            logger.exception("Payla billing reminder loop error")

        await asyncio.sleep(CHECK_INTERVAL)