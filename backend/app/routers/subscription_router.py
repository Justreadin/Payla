"""Payla subscriptions: permanent Free tier, auto-renewing Silver, founder price protection."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from google.cloud import firestore as google_firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.firebase import db
from app.core.subscription import (
    can_access_silver_features,
    get_subscription_status,
    parse_firestore_datetime,
)
from app.core.constants import (
    FOUNDING_LIMIT,
    FOUNDING_RESERVATION_HOURS,
)
from app.models.user_model import User
from app.services.paystack import (
    disable_subscription,
    get_subscription_manage_link,
    get_plan,
    initialize_subscription_payment,
    verify_payment,
)

router = APIRouter(prefix="/subscription", tags=["Subscription"])
logger = logging.getLogger("payla")

COUNTER_REF = db.collection("founding_offer").document("state")


FOUNDING_PRICES = {
    "silver_monthly": settings.PAYLA_FOUNDING_SILVER_MONTHLY_PRICE_NGN,
    "silver_yearly": settings.PAYLA_FOUNDING_SILVER_YEARLY_PRICE_NGN,
}

PLANS = {
    "silver_monthly": {
        "name": "Payla Silver (Monthly)",
        "amount_ngn": settings.PAYLA_SILVER_MONTHLY_PRICE_NGN,
        "interval": "monthly",
        "description": "Silver features, billed monthly",
    },
    "silver_yearly": {
        "name": "Payla Silver (Yearly)",
        "amount_ngn": settings.PAYLA_SILVER_YEARLY_PRICE_NGN,
        "interval": "yearly",
        "description": "Silver features, billed annually",
    },
}

for _plan in PLANS.values():
    _plan["amount_kobo"] = _plan["amount_ngn"] * 100


def _plan_code(plan_key: str, founding: bool) -> str:
    if plan_key == "silver_monthly":
        value = (
            settings.PAYSTACK_FOUNDING_SILVER_MONTHLY_PLAN_CODE
            if founding
            else settings.PAYSTACK_SILVER_MONTHLY_PLAN_CODE
        )
    else:
        value = (
            settings.PAYSTACK_FOUNDING_SILVER_YEARLY_PLAN_CODE
            if founding
            else settings.PAYSTACK_SILVER_YEARLY_PLAN_CODE
        )
    return value.strip()


def _is_lifetime_founder(data: dict) -> bool:
    return bool(
        data.get("founding_member_ever")
        or data.get("founding_price_locked")
    )


def _price_for(
    plan_key: str,
    founding: bool,
    user_data: dict | None = None,
) -> int:
    """Return the correct price, preserving stored prices for returning founders."""
    if founding and user_data and _is_lifetime_founder(user_data):
        stored_field = (
            "founding_monthly_price_ngn"
            if plan_key == "silver_monthly"
            else "founding_yearly_price_ngn"
        )
        stored_price = user_data.get(stored_field)
        if stored_price is not None:
            try:
                price = int(stored_price)
                if price > 0:
                    return price
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid locked founding price in user record for %s",
                    stored_field,
                )

    if founding:
        return FOUNDING_PRICES[plan_key]

    return int(PLANS[plan_key]["amount_ngn"])


def _counter_data(raw: dict | None) -> dict:
    """Normalize founding capacity and available slot IDs."""
    value = dict(raw or {})
    if not isinstance(value.get("available_slots"), list):
        claimed = max(0, int(value.get("claimed_count", 0)))
        reserved = max(0, int(value.get("reserved_count", 0)))
        occupied = min(FOUNDING_LIMIT, claimed + reserved)
        value["available_slots"] = list(
            range(occupied + 1, FOUNDING_LIMIT + 1)
        )

    value["available_slots"] = sorted({
        int(number)
        for number in value["available_slots"]
        if 1 <= int(number) <= FOUNDING_LIMIT
    })
    value["claimed_count"] = max(0, int(value.get("claimed_count", 0)))
    value["reserved_count"] = max(0, int(value.get("reserved_count", 0)))
    return value


def _user_snapshot(user_id: str) -> tuple[dict, Any]:
    ref = db.collection("users").document(user_id)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="User not found")
    return snap.to_dict() or {}, ref


def _user_has_paid_access(data: dict) -> bool:
    class SnapshotUser:
        def __init__(self, values):
            self.plan = values.get("plan", "free")
            self.subscription_end = (
                values.get("subscription_end")
                or values.get("next_billing_date")
            )
            self.subscription_status = values.get(
                "subscription_status", "active"
            )
            self.cancel_at_period_end = bool(
                values.get("cancel_at_period_end", False)
            )
            self.manual_silver_override = values.get(
                "manual_silver_override", False
            )

    return can_access_silver_features(SnapshotUser(data))


def _founding_slots_remaining() -> int:
    snap = COUNTER_REF.get()
    counter = _counter_data(snap.to_dict() if snap.exists else None)
    return len(counter["available_slots"])


@google_firestore.transactional
def _reserve_checkout_transaction(
    transaction,
    lock_ref,
    reservation_ref,
    counter_ref,
    new_reference: str,
    plan_key: str,
    user_id: str,
    lifetime_founder: bool,
    now: datetime,
):
    """Atomically lock a checkout and reserve a founding slot if available."""
    lock_snap = lock_ref.get(transaction=transaction)
    reservation_snap = reservation_ref.get(transaction=transaction)
    counter_snap = counter_ref.get(transaction=transaction)

    lock = (lock_snap.to_dict() or {}) if lock_snap.exists else {}
    reservation = (
        (reservation_snap.to_dict() or {}) if reservation_snap.exists else {}
    )
    counter = _counter_data(
        counter_snap.to_dict() if counter_snap.exists else None
    )
    counter_changed = False

    if lock.get("status") == "pending":
        expires = parse_firestore_datetime(lock.get("expires_at"))
        if expires and expires > now:
            if lock.get("plan_key") != plan_key:
                return {"action": "conflict"}
            return {"action": "reuse", **lock}

        old_reference = lock.get("reference")
        if (
            reservation.get("status") == "reserved"
            and reservation.get("reference") == old_reference
        ):
            slot = reservation.get("founding_slot")
            if slot and int(slot) not in counter["available_slots"]:
                counter["available_slots"].append(int(slot))
                counter["available_slots"].sort()

            counter["reserved_count"] = max(
                0, counter["reserved_count"] - 1
            )
            counter["updated_at"] = now
            counter_changed = True
            transaction.set(
                reservation_ref,
                {"status": "expired", "expired_at": now},
                merge=True,
            )

        if old_reference:
            transaction.set(
                db.collection("pending_subscriptions").document(
                    str(old_reference)
                ),
                {"status": "expired", "updated_at": now},
                merge=True,
            )

    is_founding = bool(lifetime_founder)
    slot = None
    expires_at = now + timedelta(hours=FOUNDING_RESERVATION_HOURS)

    if not lifetime_founder and counter["available_slots"]:
        is_founding = True
        slot = counter["available_slots"].pop(0)
        counter["reserved_count"] += 1
        counter["updated_at"] = now
        counter_changed = True

        transaction.set(
            reservation_ref,
            {
                "user_id": user_id,
                "status": "reserved",
                "founding_slot": slot,
                "plan_key": plan_key,
                "reference": new_reference,
                "created_at": now,
                "expires_at": expires_at,
            },
            merge=True,
        )

    lock_data = {
        "user_id": user_id,
        "reference": new_reference,
        "plan_key": plan_key,
        "status": "pending",
        "is_founding_candidate": is_founding,
        "is_founding_returning_member": bool(lifetime_founder),
        "founding_slot": slot,
        "reservation_required": bool(is_founding and not lifetime_founder),
        "created_at": now,
        "expires_at": expires_at,
    }

    if counter_changed:
        transaction.set(counter_ref, counter, merge=True)

    transaction.set(lock_ref, lock_data, merge=True)
    return {"action": "created", **lock_data}


@google_firestore.transactional
def _release_slot_transaction(
    transaction,
    reservation_ref,
    counter_ref,
    reference: str,
    now: datetime,
):
    reservation_snap = reservation_ref.get(transaction=transaction)
    counter_snap = counter_ref.get(transaction=transaction)

    if not reservation_snap.exists:
        return False

    reservation = reservation_snap.to_dict() or {}
    if (
        reservation.get("status") != "reserved"
        or reservation.get("reference") != reference
    ):
        return False

    counter = _counter_data(
        counter_snap.to_dict() if counter_snap.exists else None
    )
    slot = reservation.get("founding_slot")

    if slot and int(slot) not in counter["available_slots"]:
        counter["available_slots"].append(int(slot))
        counter["available_slots"].sort()

    counter["reserved_count"] = max(0, counter["reserved_count"] - 1)
    counter["updated_at"] = now

    transaction.set(counter_ref, counter, merge=True)
    transaction.set(
        reservation_ref,
        {"status": "released", "released_at": now},
        merge=True,
    )
    return True


def release_founding_reservation(user_id: str, reference: str) -> None:
    """Release a still-pending founding slot for a failed or abandoned checkout."""
    now = datetime.now(timezone.utc)
    try:
        _release_slot_transaction(
            db.transaction(),
            db.collection("founding_reservations").document(user_id),
            COUNTER_REF,
            reference,
            now,
        )
    except Exception:
        logger.exception(
            "Could not release founding reservation for user %s", user_id
        )


async def _release_expired_reservations() -> None:
    """Release expired reservations only when payment is confirmed unsuccessful."""
    now = datetime.now(timezone.utc)

    try:
        docs = list(
            db.collection("founding_reservations")
            .where(filter=FieldFilter("status", "==", "reserved"))
            .stream()
        )

        for doc in docs:
            current = doc.to_dict() or {}
            expiry = parse_firestore_datetime(current.get("expires_at"))
            if not expiry or expiry > now:
                continue

            reference = current.get("reference")
            if not reference:
                continue

            pending_ref = db.collection("pending_subscriptions").document(
                str(reference)
            )
            pending_snap = pending_ref.get()

            if not pending_snap.exists:
                provider_status = "abandoned"
            else:
                pending = pending_snap.to_dict() or {}
                if pending.get("status") in {
                    "failed",
                    "initialization_failed",
                    "abandoned",
                    "expired",
                }:
                    provider_status = "abandoned"
                else:
                    try:
                        verified = await verify_payment(str(reference))
                        provider_status = str(
                            (verified.get("data") or {}).get(
                                "status", "unknown"
                            )
                        ).lower()
                    except HTTPException:
                        logger.warning(
                            "Could not verify expired founding checkout %s; "
                            "keeping its reservation",
                            reference,
                        )
                        continue

            if provider_status == "success":
                continue

            if provider_status not in {"abandoned", "failed", "reversed"}:
                continue

            tx = db.transaction()

            @google_firestore.transactional
            def expire_one(transaction):
                reservation_snap = doc.reference.get(
                    transaction=transaction
                )
                counter_snap = COUNTER_REF.get(transaction=transaction)
                lock_ref = db.collection(
                    "subscription_checkout_locks"
                ).document(doc.id)
                lock_snap = lock_ref.get(transaction=transaction)

                if not reservation_snap.exists:
                    return

                reservation = reservation_snap.to_dict() or {}
                if (
                    reservation.get("status") != "reserved"
                    or reservation.get("reference") != reference
                ):
                    return

                current_expiry = parse_firestore_datetime(
                    reservation.get("expires_at")
                )
                if current_expiry and current_expiry > now:
                    return

                counter = _counter_data(
                    counter_snap.to_dict() if counter_snap.exists else None
                )
                slot = reservation.get("founding_slot")

                if slot and int(slot) not in counter["available_slots"]:
                    counter["available_slots"].append(int(slot))
                    counter["available_slots"].sort()

                counter["reserved_count"] = max(
                    0, counter["reserved_count"] - 1
                )
                counter["updated_at"] = now

                transaction.set(COUNTER_REF, counter, merge=True)
                transaction.set(
                    doc.reference,
                    {"status": "expired", "expired_at": now},
                    merge=True,
                )
                transaction.set(
                    pending_ref,
                    {"status": "expired", "updated_at": now},
                    merge=True,
                )

                if (
                    lock_snap.exists
                    and (lock_snap.to_dict() or {}).get("reference")
                    == reference
                ):
                    transaction.set(
                        lock_ref,
                        {"status": "expired", "updated_at": now},
                        merge=True,
                    )

            expire_one(tx)

    except Exception:
        logger.exception("Could not clean expired founding reservations")


def _status_payload(user_id: str, data: dict) -> dict:
    plan = str(data.get("plan") or "free").lower()
    paid_access = _user_has_paid_access(data)
    active = bool(plan in {"silver", "gold", "opal"} and paid_access)
    status_value = str(data.get("subscription_status") or "active").lower()

    state_user = type(
        "SubscriptionSnapshot",
        (),
        {
            "plan": plan,
            "subscription_end": (
                data.get("subscription_end")
                or data.get("next_billing_date")
            ),
            "subscription_status": status_value,
            "cancel_at_period_end": bool(
                data.get("cancel_at_period_end", False)
            ),
            "manual_silver_override": data.get(
                "manual_silver_override", False
            ),
        },
    )()

    sub_status = get_subscription_status(state_user)
    founder = _is_lifetime_founder(data)

    return {
        "plan": plan if active else "free",
        "is_active": active,
        "subscription_active": active,
        "trial_used": False,
        "trial_active": False,
        "trial_days_left": 0,
        "message": "Payla Silver active" if active else "Payla Free is active",
        "next_billing": (
            data.get("next_billing_date") or data.get("subscription_end")
        ),
        "subscription_end": data.get("subscription_end"),
        "subscription_status": status_value if active else "free",
        "cancel_at_period_end": bool(
            data.get("cancel_at_period_end", False)
        ),
        "in_grace_period": bool(sub_status["in_grace_period"] and active),
        "days_left_in_grace": (
            sub_status["days_left_in_grace"] if active else 0
        ),
        "can_use_premium": active,
        "billing": data.get("billing_cycle") if active else None,
        "founding_member": founder,
        "founding_member_ever": founder,
        "founding_price_locked": founder,
        "founding_spot": data.get("founding_spot"),
        "founding_monthly_price_ngn": (
            data.get(
                "founding_monthly_price_ngn",
                FOUNDING_PRICES["silver_monthly"],
            )
            if founder
            else None
        ),
        "founding_yearly_price_ngn": (
            data.get(
                "founding_yearly_price_ngn",
                FOUNDING_PRICES["silver_yearly"],
            )
            if founder
            else None
        ),
        # History markers for the renewal flow.
        "last_subscription_payment_at": data.get(
            "last_subscription_payment_at"
        ),
        "subscription_id": data.get("subscription_id"),
    }


@router.get("/status")
async def get_status(user: User = Depends(get_current_user)):
    data, _ = _user_snapshot(user.id)
    return _status_payload(user.id, data)


@router.get("/plans")
async def get_plans(user: User = Depends(get_current_user)):
    user_data, _ = _user_snapshot(user.id)
    returning_founder = _is_lifetime_founder(user_data)

    reservation_snap = (
        db.collection("founding_reservations").document(user.id).get()
    )
    reservation = (
        (reservation_snap.to_dict() or {})
        if reservation_snap.exists
        else {}
    )

    reservation_expires = parse_firestore_datetime(
        reservation.get("expires_at")
    )
    owns_active_reservation = bool(
        reservation.get("status") == "reserved"
        and reservation_expires is not None
        and reservation_expires > datetime.now(timezone.utc)
    )

    spots_remaining = _founding_slots_remaining()
    use_founding_price = bool(
        returning_founder or owns_active_reservation or spots_remaining > 0
    )

    public_plans = {}
    for key, base in PLANS.items():
        price = _price_for(
            key,
            use_founding_price,
            user_data if returning_founder else None,
        )
        public_plans[key] = {
            "name": base["name"],
            "amount_ngn": price,
            "amount_kobo": price * 100,
            "interval": base["interval"],
            "description": (
                f"₦{price:,} per "
                f"{'month' if key.endswith('monthly') else 'year'}"
            ),
            "pricing_type": (
                "founding" if use_founding_price else "standard"
            ),
        }

    return {
        "plans": public_plans,
        "founding_offer": {
            "total_spots": FOUNDING_LIMIT,
            "spots_remaining": spots_remaining,
            "available_for_this_account": (
                use_founding_price
                and not returning_founder
                and (owns_active_reservation or spots_remaining > 0)
            ),
            "is_existing_founder": returning_founder,
            "reserved_for_this_account": owns_active_reservation,
            "price_protected_forever": returning_founder,
        },
    }


@router.post("/start/{plan_key}")
async def start_subscription(
    plan_key: str,
    user: User = Depends(get_current_user),
):
    if plan_key not in PLANS:
        raise HTTPException(
            status_code=400,
            detail=f"Choose one of: {', '.join(PLANS)}",
        )

    user_data, _ = _user_snapshot(user.id)
    email = (
        user_data.get("email") or getattr(user, "email", "") or ""
    ).strip().lower()

    if not email:
        raise HTTPException(
            status_code=400,
            detail="An account email is required for billing",
        )

    if _user_has_paid_access(user_data):
        raise HTTPException(
            status_code=409,
            detail="You already have an active Silver subscription",
        )

    await _release_expired_reservations()

    now = datetime.now(timezone.utc)
    reference = f"payla-sub-{uuid.uuid4().hex}"
    lock_ref = db.collection("subscription_checkout_locks").document(
        user.id
    )
    reservation_ref = db.collection("founding_reservations").document(
        user.id
    )

    allocation = _reserve_checkout_transaction(
        db.transaction(),
        lock_ref,
        reservation_ref,
        COUNTER_REF,
        reference,
        plan_key,
        user.id,
        _is_lifetime_founder(user_data),
        now,
    )

    if allocation.get("action") == "conflict":
        raise HTTPException(
            status_code=409,
            detail=(
                "You already have a Silver checkout in progress. "
                "Complete it or wait for it to expire."
            ),
        )

    if allocation.get("action") == "reuse":
        reused_ref = str(allocation.get("reference", ""))
        snap = db.collection("pending_subscriptions").document(
            reused_ref
        ).get()
        pending = (snap.to_dict() or {}) if snap.exists else {}

        if (
            pending.get("authorization_url")
            and pending.get("status") == "pending"
        ):
            return {
                "success": True,
                "message": "Existing Silver checkout retrieved",
                "reference": reused_ref,
                "authorization_url": pending["authorization_url"],
                "amount_ngn": pending["amount_ngn"],
                "amount_kobo": pending["amount_kobo"],
                "currency": "NGN",
                "plan_code": plan_key,
                "billing_cycle": pending["billing_cycle"],
                "founding_member_offer": bool(
                    pending.get("is_founding_candidate")
                ),
                "founding_spot": pending.get("founding_slot"),
                "pricing_type": (
                    "founding"
                    if pending.get("is_founding_candidate")
                    else "standard"
                ),
            }

        raise HTTPException(
            status_code=409,
            detail=(
                "Your checkout is still being prepared. "
                "Please retry shortly."
            ),
        )

    is_founding = bool(allocation.get("is_founding_candidate"))
    is_returning_founder = bool(
        allocation.get("is_founding_returning_member")
    )
    amount_ngn = _price_for(
        plan_key,
        is_founding,
        user_data if is_returning_founder else None,
    )
    amount_kobo = amount_ngn * 100
    provider_plan_code = _plan_code(plan_key, is_founding)

    pending_ref = db.collection("pending_subscriptions").document(
        reference
    )
    pending_data = {
        "type": "silver_subscription",
        "user_id": user.id,
        "email": email,
        "plan": "silver",
        "plan_key": plan_key,
        "plan_code": plan_key,
        "paystack_plan_code": provider_plan_code,
        "interval": PLANS[plan_key]["interval"],
        "billing_cycle": PLANS[plan_key]["interval"],
        "amount_ngn": amount_ngn,
        "amount_kobo": amount_kobo,
        "currency": "NGN",
        "reference": reference,
        "is_founding_candidate": is_founding,
        "is_founding_returning_member": is_returning_founder,
        "founding_slot": allocation.get("founding_slot"),
        "status": "initializing",
        "created_at": now,
        "updated_at": now,
    }
    pending_ref.set(pending_data)

    try:
        if not provider_plan_code:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Silver recurring plans are not configured for "
                    "this Paystack environment."
                ),
            )

        provider_result = await get_plan(provider_plan_code)
        provider_plan = provider_result.get("data") or {}
        expected_interval = (
            "monthly" if plan_key.endswith("monthly") else "annually"
        )

        try:
            provider_amount = int(provider_plan.get("amount", -1))
        except (TypeError, ValueError):
            provider_amount = -1

        if (
            provider_amount != amount_kobo
            or provider_plan.get("currency") != "NGN"
            or provider_plan.get("interval") != expected_interval
        ):
            raise HTTPException(
                status_code=503,
                detail=(
                    "The configured Paystack plan does not match Payla's "
                    "expected price, currency, or interval. Checkout was "
                    "stopped to prevent an incorrect charge."
                ),
            )

        callback_url = str(settings.SUBSCRIPTION_CALLBACK_URL)

        parsed = urlsplit(callback_url)

        logger.info(
            "Subscription callback resolved: scheme=%s host=%s path=%s",
            parsed.scheme,
            parsed.hostname,
            parsed.path,
        )

        checkout = await initialize_subscription_payment(
            email=email,
            amount_kobo=amount_kobo,
            paystack_plan_code=provider_plan_code,
            reference=reference,
            metadata={
                "type": "subscription_initial",
                "user_id": user.id,
                "plan": "silver",
                "plan_code": plan_key,
                "billing_cycle": PLANS[plan_key]["interval"],
                "founding_candidate": is_founding,
                "founding_returning_member": is_returning_founder,
            },
            callback_url=callback_url,
        )

        updated_at = datetime.now(timezone.utc)
        pending_ref.update({
            "status": "pending",
            "authorization_url": checkout["authorization_url"],
            "paystack_access_code": checkout.get("access_code"),
            "updated_at": updated_at,
        })
        lock_ref.update({
            "status": "pending",
            "authorization_url": checkout["authorization_url"],
            "updated_at": updated_at,
        })

        if is_founding and not is_returning_founder:
            reservation_ref.update({
                "authorization_url": checkout["authorization_url"],
                "status": "reserved",
                "updated_at": updated_at,
            })

        return {
            "success": True,
            "message": "Subscription checkout initialized",
            "reference": reference,
            "authorization_url": checkout["authorization_url"],
            "amount_ngn": amount_ngn,
            "amount_kobo": amount_kobo,
            "currency": "NGN",
            "plan_code": plan_key,
            "billing_cycle": PLANS[plan_key]["interval"],
            "founding_member_offer": is_founding,
            "founding_spot": allocation.get("founding_slot"),
            "pricing_type": (
                "founding" if is_founding else "standard"
            ),
        }

    except Exception as exc:
        failure_time = datetime.now(timezone.utc)
        pending_ref.set({
            "status": "initialization_failed",
            "updated_at": failure_time,
        }, merge=True)
        lock_ref.set({
            "status": "initialization_failed",
            "updated_at": failure_time,
        }, merge=True)

        if is_founding and not is_returning_founder:
            release_founding_reservation(user.id, reference)

        if isinstance(exc, HTTPException):
            raise

        logger.exception(
            "Failed to initialize Payla subscription checkout for user %s",
            user.id,
        )
        raise HTTPException(
            status_code=502,
            detail="Could not initialize subscription checkout",
        ) from exc


@router.get("/verify/{reference}")
async def verify_subscription(
    reference: str,
    user: User = Depends(get_current_user),
):
    pending_ref = db.collection("pending_subscriptions").document(reference)
    pending_snap = pending_ref.get()

    if not pending_snap.exists:
        raise HTTPException(
            status_code=404,
            detail="Subscription reference not found",
        )

    pending = pending_snap.to_dict() or {}

    if pending.get("user_id") != user.id:
        raise HTTPException(
            status_code=403,
            detail="This checkout does not belong to your account",
        )

    if pending.get("status") in {
        "abandoned",
        "initialization_failed",
        "verification_mismatch",
        "failed",
        "expired",
    }:
        raise HTTPException(
            status_code=400,
            detail="This checkout is no longer valid. Start a new checkout.",
        )

    result = await verify_payment(reference)
    payment = result.get("data") or {}

    if payment.get("reference") != reference:
        raise HTTPException(
            status_code=400, detail="Paystack reference mismatch"
        )

    if payment.get("status") != "success":
        raise HTTPException(
            status_code=409,
            detail="Payment has not been confirmed as successful",
        )

    try:
        actual_amount = int(payment.get("amount", -1))
        expected_amount = int(pending.get("amount_kobo", -2))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400, detail="Invalid payment amount"
        )

    if actual_amount != expected_amount:
        raise HTTPException(
            status_code=400,
            detail="Payment amount does not match the selected plan",
        )

    if payment.get("currency") != "NGN":
        raise HTTPException(
            status_code=400, detail="Payment currency mismatch"
        )

    # Idempotent processing: the webhook may already have activated this payment.
    from app.services.subscription_webhooks import handle_subscription_event

    handled = handle_subscription_event("charge.success", payment)

    # Do not interpret "handled" as proof of activation.
    fresh_pending_snap = pending_ref.get()
    fresh_pending = fresh_pending_snap.to_dict() or {}

    fresh_user_data, _ = _user_snapshot(user.id)

    if (
        not handled
        or fresh_pending.get("status") != "paid"
        or fresh_user_data.get("last_payment_ref") != reference
        or not _user_has_paid_access(fresh_user_data)
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Payment was verified, but subscription activation "
                "has not been confirmed. Please retry shortly."
            ),
        )

    return {
        "success": True,
        "status": _status_payload(user.id, fresh_user_data),
    }


@router.post("/abandon/{reference}")
async def abandon_checkout(
    reference: str,
    user: User = Depends(get_current_user),
):
    """Allow the checkout owner to abandon an unpaid checkout."""
    pending_ref = db.collection("pending_subscriptions").document(reference)
    snap = pending_ref.get()

    if not snap.exists:
        raise HTTPException(status_code=404, detail="Checkout not found")

    pending = snap.to_dict() or {}

    if pending.get("user_id") != user.id:
        raise HTTPException(
            status_code=403,
            detail="This checkout does not belong to your account",
        )

    if pending.get("status") == "paid":
        raise HTTPException(
            status_code=409,
            detail="This checkout has already been paid",
        )

    # Never release a founding slot while the provider's payment outcome
    # is unknown. Verify first, and only abandon when no successful
    # charge exists.
    try:
        verification = await verify_payment(reference)
        payment = verification.get("data") or {}
        provider_status = str(payment.get("status", "")).lower()

        if provider_status == "success":
            raise HTTPException(
                status_code=409,
                detail=(
                    "Paystack reports a successful payment. "
                    "Refresh subscription status instead of abandoning checkout."
                ),
            )
    except HTTPException as exc:
        if exc.status_code == 409:
            raise
        # If verification is unavailable, do not release a founding reservation.
        raise HTTPException(
            status_code=503,
            detail=(
                "Paystack payment status could not be confirmed. "
                "Please retry before abandoning this checkout."
            ),
        ) from exc

    now = datetime.now(timezone.utc)
    pending_ref.set({
        "status": "abandoned",
        "updated_at": now,
    }, merge=True)

    lock_ref = db.collection("subscription_checkout_locks").document(user.id)
    lock_snap = lock_ref.get()

    if (
        lock_snap.exists
        and (lock_snap.to_dict() or {}).get("reference") == reference
    ):
        lock_ref.set({
            "status": "abandoned",
            "updated_at": now,
        }, merge=True)

    if (
        pending.get("is_founding_candidate")
        and not pending.get("is_founding_returning_member")
    ):
        release_founding_reservation(user.id, reference)

    return {
        "success": True,
        "message": "Checkout cancelled; no successful payment was detected.",
    }


@router.get("/manage-link")
async def subscription_manage_link(
    user: User = Depends(get_current_user),
):
    data, _ = _user_snapshot(user.id)
    sub_code = data.get("subscription_id")

    if not sub_code:
        raise HTTPException(
            status_code=400,
            detail="No recurring subscription was found",
        )

    link = await get_subscription_manage_link(str(sub_code))
    return {"success": True, "url": link}


@router.post("/cancel")
async def cancel_subscription(
    user: User = Depends(get_current_user),
):
    data, user_ref = _user_snapshot(user.id)

    if not _user_has_paid_access(data):
        raise HTTPException(
            status_code=400,
            detail="There is no active Silver subscription to cancel",
        )

    sub_code = data.get("subscription_id")
    email_token = data.get("subscription_email_token")

    if not sub_code or not email_token:
        raise HTTPException(
            status_code=400,
            detail=(
                "Paystack has not returned the cancellation details yet"
            ),
        )

    # Request provider-side cancellation before recording non-renewing status.
    await disable_subscription(str(sub_code), str(email_token))

    now = datetime.now(timezone.utc)
    user_ref.update({
        "subscription_status": "non_renewing",
        "cancel_at_period_end": True,
        "subscription_cancel_requested_at": now,
        "updated_at": now,
    })

    return {
        "success": True,
        "message": (
            "Automatic renewal has been disabled. Silver remains available "
            "through the paid period."
        ),
        "subscription_end": (
            data.get("subscription_end") or data.get("next_billing_date")
        ),
        "founding_price_locked": _is_lifetime_founder(data),
    }