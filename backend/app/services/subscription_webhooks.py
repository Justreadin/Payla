
"""Idempotent Paystack subscription-event handling for Payla.

Call handle_subscription_event(event, data) only after the receiving route has
validated Paystack's x-paystack-signature HMAC.

Returns True when an event belongs to subscriptions, so the generic paylink
and invoice handler can skip it.
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud import firestore as google_firestore
from app.core.constants import FOUNDING_LIMIT
from app.core.firebase import db
from app.core.subscription import parse_firestore_datetime
from app.core.config import settings
logger = logging.getLogger("payla")

COUNTER_REF = db.collection("founding_offer").document("state")

INITIAL_PLAN_KEYS = {"silver_monthly", "silver_yearly"}

TERMINAL_PROVIDER_STATES = {
    "cancelled",
    "canceled",
    "disabled",
    "expired",
    "complete",
    "completed",
}

VOLUNTARY_CANCELLATION_STATES = {
    "non_renewing",
    "cancel_at_period_end",
    "cancellation_pending",
    "cancelled",
    "canceled",
    "disabled",
    "expired",
    "complete",
    "completed",
}


def _founding_prices() -> tuple[int, int]:
    return (
        int(os.getenv("PAYLA_FOUNDING_SILVER_MONTHLY_PRICE_NGN", "7500")),
        int(os.getenv("PAYLA_FOUNDING_SILVER_YEARLY_PRICE_NGN", "75000")),
    )


def _subscription_object(data: dict) -> dict:
    sub = data.get("subscription")
    return sub if isinstance(sub, dict) else {}


def _subscription_code(data: dict) -> Optional[str]:
    code = data.get("subscription_code")

    if not code:
        sub = _subscription_object(data)
        code = sub.get("subscription_code") or sub.get("code")

    return str(code) if code else None


def _next_payment_date(data: dict) -> Optional[datetime]:
    sub = _subscription_object(data)

    return (
        parse_firestore_datetime(sub.get("next_payment_date"))
        or parse_firestore_datetime(data.get("next_payment_date"))
    )


def _event_time(data: dict) -> Optional[datetime]:
    """Extract a provider timestamp for ordering payment events."""
    for key in (
        "paid_at",
        "transaction_date",
        "created_at",
        "createdAt",
    ):
        parsed = parse_firestore_datetime(data.get(key))
        if parsed:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)

    return None


def _find_user_id(data: dict) -> Optional[str]:
    """Resolve a provider event to an existing Payla user."""
    metadata = data.get("metadata") or {}

    user_id = metadata.get("user_id") if isinstance(metadata, dict) else None

    if user_id:
        snapshot = db.collection("users").document(str(user_id)).get()
        if snapshot.exists:
            return str(user_id)

    sub_code = _subscription_code(data)

    if sub_code:
        matches = (
            db.collection("users")
            .where(filter=FieldFilter("subscription_id", "==", sub_code))
            .limit(1)
            .get()
        )
        if matches:
            return matches[0].id

    customer = data.get("customer") or {}
    if not isinstance(customer, dict):
        customer = {}

    email = (
        customer.get("email") or data.get("email") or ""
    ).strip().lower()

    if email:
        matches = (
            db.collection("users")
            .where(filter=FieldFilter("email", "==", email))
            .limit(1)
            .get()
        )
        if matches:
            return matches[0].id

    return None

def _event_marker(event: str, identifier: str) -> str:
    return hashlib.sha256(
        f"{event}:{identifier}".encode("utf-8")
    ).hexdigest()


def _counter_data(raw: Optional[dict]) -> dict:
    """Normalize the founding-offer counter document."""
    value = dict(raw or {})

    try:
        claimed = max(0, int(value.get("claimed_count", 0)))
        reserved = max(0, int(value.get("reserved_count", 0)))
    except (TypeError, ValueError):
        claimed, reserved = 0, 0

    if not isinstance(value.get("available_slots"), list):
        occupied = min(FOUNDING_LIMIT, claimed + reserved)
        value["available_slots"] = list(
            range(occupied + 1, FOUNDING_LIMIT + 1)
        )

    slots = set()

    for item in value["available_slots"]:
        try:
            slot = int(item)
        except (TypeError, ValueError):
            continue

        if 1 <= slot <= FOUNDING_LIMIT:
            slots.add(slot)

    value["available_slots"] = sorted(slots)
    value["claimed_count"] = claimed
    value["reserved_count"] = reserved

    return value


@google_firestore.transactional
def _process_initial_charge(
    transaction,
    pending_ref,
    user_ref,
    reservation_ref,
    lock_ref,
    counter_ref,
    marker_ref,
    data: dict,
    now: datetime,
    
):
    """Verify and atomically apply the first subscription payment."""
    # All transaction reads must occur before any writes.
    pending_snap = pending_ref.get(transaction=transaction)
    user_snap = user_ref.get(transaction=transaction)
    reservation_snap = reservation_ref.get(transaction=transaction)
    lock_snap = lock_ref.get(transaction=transaction)
    counter_snap = counter_ref.get(transaction=transaction)
    marker_snap = marker_ref.get(transaction=transaction)

    if marker_snap.exists:
        return "already_processed"

    if not pending_snap.exists or not user_snap.exists:
        return "missing_record"

    pending = pending_snap.to_dict() or {}
    user_data = user_snap.to_dict() or {}

    if pending.get("status") == "paid":
        transaction.set(
            marker_ref,
            {
                "event": "charge.success",
                "processed_at": now,
                "result": "already_paid",
            },
            merge=True,
        )
        return "already_processed"

    try:
        expected_amount = int(pending.get("amount_kobo", -1))
        actual_amount = int(data.get("amount", -2))
    except (TypeError, ValueError, OverflowError):
        expected_amount = -1
        actual_amount = -2

    currency = data.get("currency")
    status_value = str(data.get("status") or "").lower()

    if (
        status_value != "success"
        or expected_amount <= 0
        or actual_amount != expected_amount
        or currency != "NGN"
    ):
        transaction.set(
            pending_ref,
            {
                "status": "verification_mismatch",
                "observed_amount_kobo": actual_amount,
                "observed_currency": currency,
                "updated_at": now,
            },
            merge=True,
        )
        transaction.set(
            marker_ref,
            {
                "event": "charge.success",
                "processed_at": now,
                "result": "mismatch",
            },
        )
        return "payment_mismatch"

    cycle = str(
        pending.get("billing_cycle")
        or pending.get("interval")
        or "monthly"
    ).lower()

    if cycle not in {"monthly", "yearly"}:
        cycle = "monthly"

    cycle_days = 365 if cycle == "yearly" else 30
    next_bill = _next_payment_date(data)

    if not next_bill or next_bill <= now:
        next_bill = now + timedelta(days=cycle_days)

    subscription_code = _subscription_code(data)
    customer = data.get("customer") or {}

    if not isinstance(customer, dict):
        customer = {}

    subscription_obj = _subscription_object(data)

    user_updates = {
        "plan": "silver",
        "subscription_status": "active",
        "is_active": True,
        "subscription_end": next_bill,
        "next_billing_date": next_bill,
        "billing_cycle": cycle,
        "subscription_plan_key": pending.get("plan_key"),
        "subscription_plan_code": pending.get("paystack_plan_code"),
        "subscription_amount_ngn": pending.get("amount_ngn"),
        "last_payment_ref": data.get("reference"),
        "last_subscription_payment_reference": data.get("reference"),
        "last_subscription_payment_at": now,
        "billing_nudge_status": "active",
        "cancel_at_period_end": False,
        "updated_at": now,
    }

    if subscription_code:
        user_updates["subscription_id"] = subscription_code

    if customer.get("customer_code"):
        user_updates["paystack_customer_code"] = customer["customer_code"]

    email_token = (
        subscription_obj.get("email_token")
        or data.get("email_token")
    )

    if email_token:
        user_updates["subscription_email_token"] = email_token

    returning_founder = bool(
        pending.get("is_founding_returning_member")
        or user_data.get("founding_member_ever")
    )

    is_new_founder_candidate = bool(
        pending.get("is_founding_candidate") and not returning_founder
    )

    counter = _counter_data(
        counter_snap.to_dict() if counter_snap.exists else None
    )

    reservation = (
        reservation_snap.to_dict() or {}
        if reservation_snap.exists
        else {}
    )

    lock = lock_snap.to_dict() or {} if lock_snap.exists else {}
    counter_changed = False

    reservation_matches = (
        reservation.get("status") == "reserved"
        and reservation.get("reference") == data.get("reference")
    )

    slot = pending.get("founding_slot")
    reserved_slot = reservation.get("founding_slot")

    try:
        numeric_slot = int(slot) if slot is not None else None
        numeric_reserved_slot = (
            int(reserved_slot) if reserved_slot is not None else None
        )

    except (TypeError, ValueError):
        numeric_slot = None
        numeric_reserved_slot = None

    can_claim_new_founder_slot = (
        is_new_founder_candidate
        and reservation_matches
        and numeric_slot is not None
        and numeric_slot == numeric_reserved_slot
        and 1 <= numeric_slot <= FOUNDING_LIMIT
        and counter["reserved_count"] > 0
        and counter["claimed_count"] < FOUNDING_LIMIT
        and numeric_slot not in counter["available_slots"]
    )

    if can_claim_new_founder_slot:
        monthly_price, yearly_price = _founding_prices()

        user_updates.update({
            "founding_member": True,
            "founding_member_ever": True,
            "founding_price_locked": True,
            "founding_monthly_price_ngn": monthly_price,
            "founding_yearly_price_ngn": yearly_price,
            "founding_price_ngn": int(pending["amount_ngn"]),
            "founding_billing_cycle": cycle,
            "founding_plan_code": pending.get("paystack_plan_code"),
            "founding_spot": numeric_slot,
            "founding_joined_at": now,
        })

        counter["reserved_count"] -= 1
        counter["claimed_count"] += 1
        counter["updated_at"] = now
        counter_changed = True

        transaction.set(
            reservation_ref,
            {
                "status": "claimed",
                "claimed_at": now,
                "founding_slot": numeric_slot,
            },
            merge=True,
        )

    elif is_new_founder_candidate:
        # Never silently assign a founding slot without a valid reservation.
        logger.error(
            "Founding reservation validation failed for reference %s",
            data.get("reference"),
        )
        user_updates["founding_overflow_review_required"] = True

        # If this checkout still owns a valid reservation, release it.
        # This branch does not grant founder status.
        if reservation_matches:
            counter["reserved_count"] = max(
                0, counter["reserved_count"] - 1
            )
            if (
               numeric_reserved_slot is not None
                and 1 <= numeric_reserved_slot <= FOUNDING_LIMIT
                and numeric_reserved_slot not in counter["available_slots"]
                and counter["claimed_count"] + counter["reserved_count"]
                < FOUNDING_LIMIT
            ):
                counter["available_slots"].append(numeric_reserved_slot)
                counter["available_slots"].sort()

            counter["updated_at"] = now
            counter_changed = True
            transaction.set(
                reservation_ref,
                {"status": "released", "released_at": now},
                merge=True,
            )

    elif returning_founder:
        # Preserve the founding-price promise for returning members.
        user_updates.update({
            "founding_member": True,
            "founding_member_ever": True,
            "founding_price_locked": True,
        })

        monthly_price, yearly_price = _founding_prices()

        user_updates.setdefault(
            "founding_monthly_price_ngn",
            user_data.get("founding_monthly_price_ngn", monthly_price),
        )
        user_updates.setdefault(
            "founding_yearly_price_ngn",
            user_data.get("founding_yearly_price_ngn", yearly_price),
        )

        if user_data.get("founding_spot") is not None:
            user_updates["founding_spot"] = user_data["founding_spot"]

    transaction.update(user_ref, user_updates)

    transaction.set(
        pending_ref,
        {
            "status": "paid",
            "verified_at": now,
            "paystack_transaction_id": data.get("id"),
            "updated_at": now,
        },
        merge=True,
    )

    if counter_changed:
        transaction.set(counter_ref, counter, merge=True)

    if lock.get("reference") == data.get("reference"):
        transaction.set(
            lock_ref,
            {
                "status": "paid",
                "paid_at": now,
                "updated_at": now,
            },
            merge=True,
        )

    transaction.set(
        marker_ref,
        {
            "event": "charge.success",
            "reference": data.get("reference"),
            "processed_at": now,
            "result": "processed",
        },
    )

    return "processed"


@google_firestore.transactional
def _apply_user_event(
    transaction,
    user_ref,
    marker_ref,
    updates: dict,
    now: datetime,
    event: str,
):
    """Apply an event once, atomically with its idempotency marker."""
    marker_snap = marker_ref.get(transaction=transaction)
    user_snap = user_ref.get(transaction=transaction)

    if marker_snap.exists:
        return "already_processed"

    if not user_snap.exists:
        return "missing_user"

    transaction.update(
        user_ref,
        {**updates, "updated_at": now},
    )

    transaction.set(
        marker_ref,
        {
            "event": event,
            "processed_at": now,
            "result": "processed",
        },
    )

    return "processed"


@google_firestore.transactional
def _mark_initial_charge_failed_transaction(
    transaction,
    pending_ref,
    lock_ref,
    reference: str,
    now: datetime,
):
    """Mark a checkout failed only if it has not already been paid."""
    pending_snap = pending_ref.get(transaction=transaction)
    lock_snap = lock_ref.get(transaction=transaction)

    if not pending_snap.exists:
        return "missing"

    pending = pending_snap.to_dict() or {}

    if pending.get("status") == "paid":
        return "already_paid"

    lock = lock_snap.to_dict() or {} if lock_snap.exists else {}

    transaction.set(
        pending_ref,
        {
            "status": "failed",
            "updated_at": now,
        },
        merge=True,
    )

    if lock.get("reference") == reference:
        transaction.set(
            lock_ref,
            {
                "status": "failed",
                "updated_at": now,
            },
            merge=True,
        )

    return "failed"


def _set_initial_charge_failed(
    reference: str,
    pending: dict,
    pending_ref,
) -> None:
    """Safely fail an initial checkout and release its reservation."""
    now = datetime.now(timezone.utc)
    user_id = str(pending.get("user_id") or "")

    if not user_id:
        logger.warning(
            "Cannot clean up failed subscription checkout %s without user ID",
            reference,
        )
        return

    lock_ref = (
        db.collection("subscription_checkout_locks")
        .document(user_id)
    )

    outcome = _mark_initial_charge_failed_transaction(
        db.transaction(),
        pending_ref,
        lock_ref,
        reference,
        now,
    )

    if outcome == "already_paid":
        logger.info(
            "Ignoring delayed charge.failed for already-paid checkout %s",
            reference,
        )
        return

    if outcome == "missing":
        logger.warning(
            "Cannot mark missing checkout %s as failed",
            reference,
        )
        return

    try:
        from app.routers.subscription_router import (
            release_founding_reservation,
        )

        # The reservation release function must itself only release a
        # reservation that is still reserved and belongs to this reference.
        release_founding_reservation(user_id, reference)

    except Exception:
        logger.exception(
            "Could not release founding reservation for checkout %s",
            reference,
        )


@google_firestore.transactional
def _apply_renewal_failure_transaction(
    transaction,
    user_ref,
    marker_ref,
    updates: dict,
    now: datetime,
    event: str,
    event_time: Optional[datetime],
):
    """Atomically apply a renewal failure unless a newer payment exists."""
    marker_snap = marker_ref.get(transaction=transaction)
    user_snap = user_ref.get(transaction=transaction)

    if marker_snap.exists:
        return "already_processed"

    if not user_snap.exists:
        return "missing_user"

    user_data = user_snap.to_dict() or {}

    latest_payment = parse_firestore_datetime(
        user_data.get("last_subscription_payment_at")
    )

    if latest_payment and latest_payment.tzinfo is None:
        latest_payment = latest_payment.replace(tzinfo=timezone.utc)

    if (
        event_time
        and latest_payment
        and event_time < latest_payment
    ):
        transaction.set(
            marker_ref,
            {
                "event": event,
                "processed_at": now,
                "result": "ignored_stale_failure",
            },
        )
        return "stale"

    if (
        user_data.get("cancel_at_period_end") is True
        or user_data.get("subscription_status") in
        VOLUNTARY_CANCELLATION_STATES
    ):
        transaction.set(
            marker_ref,
            {
                "event": event,
                "processed_at": now,
                "result": "ignored_cancelled",
            },
        )
        return "cancelled"

    transaction.update(
        user_ref,
        {**updates, "updated_at": now},
    )

    transaction.set(
        marker_ref,
        {
            "event": event,
            "processed_at": now,
            "result": "processed",
        },
    )

    return "processed"


def _apply_renewal_failure(
    event: str,
    data: dict,
    identifier: str,
) -> bool:
    """Record a failed recurring charge without revoking paid time."""
    user_id = _find_user_id(data)

    if not user_id:
        logger.warning(
            "%s could not be mapped to a Payla user",
            event,
        )
        return True

    now = datetime.now(timezone.utc)
    user_ref = db.collection("users").document(user_id)
    user_snap = user_ref.get()

    if not user_snap.exists:
        return True

    user_data = user_snap.to_dict() or {}
    sub_code = _subscription_code(data)
    current_code = user_data.get("subscription_id")

    if sub_code and current_code and current_code != sub_code:
        logger.warning(
            "Ignoring stale %s for user %s",
            event,
            user_id,
        )
        return True

    marker_ref = db.collection("subscription_events").document(
        _event_marker(event, identifier)
    )

    _apply_renewal_failure_transaction(
        db.transaction(),
        user_ref,
        marker_ref,
        {
            "subscription_status": "past_due",
            "last_payment_failure_at": now,
        },
        now,
        event,
        _event_time(data),
    )

    return True


def handle_subscription_event(event: str, data: dict) -> bool:
    """Process subscription events; return False for ordinary payments."""
    data = data or {}
    reference = data.get("reference")

    # ---------------------------------------------------------------
    # 1. Initial subscription checkout.
    # ---------------------------------------------------------------
    if event in {"charge.success", "charge.failed"} and reference:
        pending_ref = (
            db.collection("pending_subscriptions")
            .document(str(reference))
        )

        pending_snap = pending_ref.get()

        if pending_snap.exists:
            pending = pending_snap.to_dict() or {}

            if (
                pending.get("type") == "silver_subscription"
                and pending.get("plan_key") in INITIAL_PLAN_KEYS
            ):
                if event == "charge.failed":
                    _set_initial_charge_failed(
                        str(reference),
                        pending,
                        pending_ref,
                    )
                    return True

                user_id = str(pending.get("user_id") or "")

                if not user_id:
                    logger.error(
                        "Initial subscription checkout %s has no user ID",
                        reference,
                    )
                    return True

                marker_ref = db.collection("subscription_events").document(
                    _event_marker(event, str(reference))
                )

                outcome = _process_initial_charge(
                    db.transaction(),
                    pending_ref,
                    db.collection("users").document(user_id),
                    db.collection("founding_reservations").document(user_id),
                    db.collection("subscription_checkout_locks").document(
                        user_id
                    ),
                    COUNTER_REF,
                    marker_ref,
                    data,
                    datetime.now(timezone.utc),
                )

                if outcome == "payment_mismatch":
                    logger.error(
                        "Subscription payment amount/currency mismatch "
                        "for reference %s",
                        reference,
                    )
                elif outcome == "missing_record":
                    logger.error(
                        "Could not find pending/user records for %s",
                        reference,
                    )

                return True

    # ---------------------------------------------------------------
    # 2. Subscription creation is not proof of payment.
    # ---------------------------------------------------------------
    if event == "subscription.create":
        user_id = _find_user_id(data)

        if not user_id:
            logger.warning(
                "subscription.create could not be mapped to a Payla user"
            )
            return True

        sub_code = _subscription_code(data)
        customer = data.get("customer") or {}

        if not isinstance(customer, dict):
            customer = {}

        user_ref = db.collection("users").document(user_id)
        user_snap = user_ref.get()

        if not user_snap.exists:
            return True

        user_data = user_snap.to_dict() or {}
        current_code = user_data.get("subscription_id")

        if sub_code and current_code and current_code != sub_code:
            logger.warning(
                "Ignoring stale subscription.create for user %s",
                user_id,
            )
            return True

        updates = {}

        if sub_code:
            updates["subscription_id"] = sub_code

        if customer.get("customer_code"):
            updates["paystack_customer_code"] = customer["customer_code"]

        sub_obj = _subscription_object(data)
        token = sub_obj.get("email_token") or data.get("email_token")

        if token:
            updates["subscription_email_token"] = token

        has_verified_payment = bool(
            user_data.get("last_subscription_payment_at")
            or user_data.get("last_payment_ref")
        )

        if not has_verified_payment and user_data.get("plan") not in {
            "silver", "gold", "opal"
        }:
            updates["subscription_status"] = "pending"

        if not updates:
            return True

        marker_id = _event_marker(
            event,
            sub_code or f"{user_id}:{customer.get('customer_code', '')}",
        )

        _apply_user_event(
            db.transaction(),
            user_ref,
            db.collection("subscription_events").document(marker_id),
            updates,
            datetime.now(timezone.utc),
            event,
        )

        return True

    # ---------------------------------------------------------------
    # 3. Recurring payment failures.
    # ---------------------------------------------------------------
    if event == "charge.failed" and data.get("subscription"):
        if reference:
            return _apply_renewal_failure(
                event,
                data,
                str(reference),
            )

        logger.warning(
            "Recurring charge.failed has no reference; "
            "cannot safely deduplicate it"
        )
        return True

    if event == "invoice.payment_failed":
        invoice_identifier = (
            data.get("invoice_code")
            or data.get("id")
            or reference
        )

        if not invoice_identifier:
            logger.warning(
                "invoice.payment_failed has no unique invoice identifier"
            )
            return True

        return _apply_renewal_failure(
            event,
            data,
            str(invoice_identifier),
        )

    # ---------------------------------------------------------------
    # 4. Recurring charge success.
    # ---------------------------------------------------------------
    if event == "charge.success" and data.get("subscription"):
        if not reference:
            logger.error(
                "Recurring charge.success has no reference; "
                "refusing a potentially non-idempotent period extension"
            )
            return True

        sub_code = _subscription_code(data)
        user_id = _find_user_id(data)

        if not user_id:
            logger.warning(
                "Recurring charge.success could not be mapped to a user"
            )
            return True

        now = datetime.now(timezone.utc)
        user_ref = db.collection("users").document(user_id)
        user_snap = user_ref.get()

        if not user_snap.exists:
            return True

        user_data = user_snap.to_dict() or {}
        current_code = user_data.get("subscription_id")

        if sub_code and current_code and current_code != sub_code:
            logger.warning(
                "Ignoring stale renewal for user %s (%s)",
                user_id,
                sub_code,
            )
            return True

        end = _next_payment_date(data)

        if not end or end <= now:
            old_end = parse_firestore_datetime(
                user_data.get("subscription_end")
            )

            base = max(old_end or now, now)
            cycle = str(
                user_data.get("billing_cycle") or "monthly"
            ).lower()

            days = 365 if cycle == "yearly" else 30
            end = base + timedelta(days=days)

        # Do not allow a delayed success event to undo an explicit
        # cancellation. The paid-through date can still reflect a charge
        # that actually succeeded.
        cancellation_requested = (
            user_data.get("cancel_at_period_end") is True
            or user_data.get("subscription_status") in
            VOLUNTARY_CANCELLATION_STATES
        )

        updates = {
            "plan": "silver",
            "subscription_status": (
                "non_renewing" if cancellation_requested else "active"
            ),
            "is_active": True,
            "subscription_end": end,
            "next_billing_date": end,
            "last_payment_ref": str(reference),
            "last_subscription_payment_reference": str(reference),
            "last_subscription_payment_at": now,
            "cancel_at_period_end": cancellation_requested,
            "billing_nudge_status": "active",
        }

        if sub_code:
            updates["subscription_id"] = sub_code

        customer = data.get("customer") or {}

        if isinstance(customer, dict) and customer.get("customer_code"):
            updates["paystack_customer_code"] = customer["customer_code"]

        marker_ref = db.collection("subscription_events").document(
            _event_marker(event, str(reference))
        )

        outcome = _apply_user_event(
            db.transaction(),
            user_ref,
            marker_ref,
            updates,
            now,
            event,
        )

        if outcome == "processed":
            logger.info(
                "Applied recurring subscription payment for user %s",
                user_id,
            )

        return True

    # ---------------------------------------------------------------
    # 5. Invoice and subscription lifecycle events.
    # ---------------------------------------------------------------
    # Invoice creation is not proof of payment. Acknowledge it without
    # changing entitlement or causing Paystack to retry indefinitely.
    if event == "invoice.create":
        return True

    # Invoice updates can contain useful lifecycle information, but their
    # paid/status fields alone must not activate or renew a subscription.
    # Entitlement changes for payment are handled by charge.success.
    if event == "invoice.update":
        logger.info(
            "Acknowledged invoice.update without changing entitlement"
        )
        return True

    lifecycle_events = {
        "subscription.not_renew",
        "subscription.disable",
        "subscription.expire",
    }

    if event in lifecycle_events:
        sub_code = _subscription_code(data)
        user_id = _find_user_id(data)

        if not user_id:
            logger.warning(
                "%s could not be mapped to a Payla user",
                event,
            )
            return True

        now = datetime.now(timezone.utc)
        user_ref = db.collection("users").document(user_id)
        user_snap = user_ref.get()

        if not user_snap.exists:
            return True

        user_data = user_snap.to_dict() or {}
        current_code = user_data.get("subscription_id")

        if sub_code and current_code and current_code != sub_code:
            logger.warning(
                "Ignoring stale %s for user %s",
                event,
                user_id,
            )
            return True

        if event == "subscription.not_renew":
            updates = {
                "subscription_status": "non_renewing",
                "cancel_at_period_end": True,
            }
            identifier = sub_code or user_id

        else:
            terminal_status = str(data.get("status") or "").lower()

            # The event name is the authoritative signal, not the
            # payload's status field. Paystack sends subscription.expire
            # with a status like "complete" or "expired"; both mean the
            # same thing. Normalizing to "expired" keeps every downstream
            # query and log analysis consistent.
            if event == "subscription.expire":
                terminal_status = "expired"
            elif event == "subscription.disable":
                terminal_status = (
                    terminal_status
                    if terminal_status in TERMINAL_PROVIDER_STATES
                    else "cancelled"
                )
            else:
                terminal_status = "cancelled"

            updates = {
                "subscription_status": terminal_status,
                "cancel_at_period_end": False,
                "last_subscription_id": current_code or sub_code,
                "preferred_domain": "ng",
            }

            identifier = sub_code or user_id

        marker_ref = db.collection("subscription_events").document(
            _event_marker(event, str(identifier))
        )

        _apply_user_event(
            db.transaction(),
            user_ref,
            marker_ref,
            updates,
            now,
            event,
        )

        # Mirror the domain revert to the paylink document so the
        # public route redirects correctly and link_url stays current.
        # Only fires on actual termination events, not on not_renew.
        if event != "subscription.not_renew":
            try:
                username = user_data.get("username") or ""
                paylink_ref = db.collection("paylinks").document(user_id)

                if username and paylink_ref.get().exists:
                    base = settings.BACKEND_URL.rstrip("/")
                    paylink_ref.update({
                        "preferred_domain": "ng",
                        "link_url": f"{base}/@{username}",
                    })
                    logger.info(
                        "Reverted preferred_domain to ng for user %s "
                        "after %s",
                        user_id,
                        event,
                    )
            except Exception:
                logger.exception(
                    "Could not revert preferred_domain for user %s "
                    "after %s",
                    user_id,
                    event,
                )


        return True

    return False
