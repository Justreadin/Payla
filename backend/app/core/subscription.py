
"""Silver entitlement checks for Payla's permanent Free tier."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from fastapi import Depends, HTTPException, status

from app.core.auth import get_current_user
from app.core.firebase import db
from app.models.user_model import User

logger = logging.getLogger("payla")

SUBSCRIPTION_GRACE_DAYS = 7

# Only genuinely paid plans can grant subscription access.
PAID_PLANS = {"silver", "gold", "opal"}

# These states must never grant access by themselves.
INACTIVE_STATES = {
    "cancelled",
    "canceled",
    "expired",
    "disabled",
    "complete",
    "completed",
    "free",
    "inactive",
    "revoked",
    "refunded",
    "chargeback",
    "suspended",
}

# These states stop renewal but do not immediately revoke already-paid access.
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

# Only these states qualify for renewal-failure grace.
RENEWAL_PROBLEM_STATES = {
    "past_due",
    "payment_failed",
    "unpaid",
}


def parse_firestore_datetime(value: Any) -> Optional[datetime]:
    """Convert supported Firestore, Python, Unix, and ISO timestamps to UTC."""
    if value is None:
        return None

    if isinstance(value, datetime):
        return (
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None
            else value.astimezone(timezone.utc)
        )

    if hasattr(value, "to_datetime"):
        try:
            result = value.to_datetime()
            return (
                result.replace(tzinfo=timezone.utc)
                if result.tzinfo is None
                else result.astimezone(timezone.utc)
            )
        except Exception:
            logger.warning("Could not convert Firestore datetime")
            return None

    if isinstance(value, dict) and "_seconds" in value:
        try:
            return datetime.fromtimestamp(
                float(value["_seconds"]),
                tz=timezone.utc,
            )
        except (TypeError, ValueError, OverflowError, OSError):
            return None

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (TypeError, ValueError, OverflowError, OSError):
            return None

    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return (
                parsed.replace(tzinfo=timezone.utc)
                if parsed.tzinfo is None
                else parsed.astimezone(timezone.utc)
            )
        except ValueError:
            logger.warning("Could not parse subscription datetime string")
            return None

    logger.warning(
        "Unsupported subscription datetime type: %s",
        type(value).__name__,
    )
    return None


def _subscription_state(user: Any) -> str:
    """Return a normalized subscription state."""
    value = getattr(user, "subscription_status", None) or "inactive"
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _has_voluntary_cancellation(user: Any, state: str) -> bool:
    """Determine whether renewal has been voluntarily stopped."""
    return (
        state in VOLUNTARY_CANCELLATION_STATES
        or bool(getattr(user, "cancel_at_period_end", False))
    )


def is_trial_active(_user: Any) -> bool:
    """Compatibility function: trials never grant paid access."""
    return False


def get_subscription_status(user: Any) -> dict:
    """
    Evaluate subscription access using the paid-through date.

    Voluntary cancellation preserves access until the paid period ends.
    Failed renewals may receive seven days of grace.
    Trials and expired subscriptions do not grant access.
    """
    raw_end = getattr(user, "subscription_end", None)

    if raw_end is None:
        raw_end = getattr(user, "next_billing_date", None)

    end = parse_firestore_datetime(raw_end)
    state = _subscription_state(user)
    now = datetime.now(timezone.utc)

    result = {
        "is_active": False,
        "in_grace_period": False,
        "days_left_in_grace": 0,
        "end": end,
    }

    if end is None:
        return result

    # A paid period remains valid even if renewal has been cancelled,
    # disabled, or marked expired prematurely by a provider event.
    # Explicit revocation, refund, chargeback, or suspension overrides this.
    if state in {"revoked", "refunded", "chargeback", "suspended"}:
        return result

    if end > now:
        result["is_active"] = True
        return result

    # Cancellation never receives renewal-failure grace.
    if _has_voluntary_cancellation(user, state):
        return result

    # Grace applies only when a renewal problem has actually been recorded.
    if state not in RENEWAL_PROBLEM_STATES:
        return result

    grace_end = end + timedelta(days=SUBSCRIPTION_GRACE_DAYS)

    if grace_end > now:
        result["is_active"] = True
        result["in_grace_period"] = True
        result["days_left_in_grace"] = max(
            0,
            (grace_end - now).days,
        )

    return result


def has_active_subscription(user: Any) -> bool:
    """Return whether the user's paid plan currently grants access."""
    plan = str(getattr(user, "plan", None) or "free").strip().lower()

    if plan not in PAID_PLANS:
        return False

    return get_subscription_status(user)["is_active"]


def can_access_silver_features(user: Any) -> bool:
    """
    Check the server-side entitlement.

    manual_silver_override must be server-managed and must never be writable
    through registration, profile updates, or other public user endpoints.
    """
    if getattr(user, "manual_silver_override", False):
        return True

    return has_active_subscription(user)


def _build_user(data: dict, user_id: Optional[str] = None) -> User:
    """Build a User model while retaining operational subscription fields."""
    payload = dict(data)

    # Firestore documents do not necessarily contain their own document ID.
    if not payload.get("_id") and user_id:
        payload["_id"] = user_id

    current = User(**payload)

    # Keep operational fields available for entitlement checks, including
    # fields not yet declared in the User model.
    for field in (
        "subscription_end",
        "subscription_status",
        "next_billing_date",
        "cancel_at_period_end",
        "manual_silver_override",
    ):
        if field not in data:
            continue

        try:
            setattr(current, field, data[field])
        except (AttributeError, TypeError, ValueError):
            # Evaluate the raw Firestore fields separately if the model
            # does not permit assignment of undeclared attributes.
            pass

    return current


def _entitlement_view(user: User, data: dict) -> Any:
    """
    Provide entitlement checks with the raw operational fields.

    This avoids losing subscription status fields when the Pydantic model
    ignores fields that have not yet been added to User.
    """
    from types import SimpleNamespace

    values = dict(data)
    values.setdefault("id", getattr(user, "id", None))

    # Use validated model values for the plan, but preserve raw operational
    # values from Firestore for subscription and cancellation decisions.
    values["plan"] = getattr(user, "plan", None) or "free"

    return SimpleNamespace(**values)


async def require_silver(
    user: Optional[User] = Depends(get_current_user),
) -> User:
    """FastAPI dependency for routes that require paid entitlement."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    snapshot = db.collection("users").document(user.id).get()

    if not snapshot.exists:
        raise HTTPException(status_code=404, detail="User not found")

    data = snapshot.to_dict() or {}
    current = _build_user(data, user_id=user.id)
    entitlement_user = _entitlement_view(current, data)

    if can_access_silver_features(entitlement_user):
        return current

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error": "subscription_required",
            "message": "Payla Silver is required to use this feature.",
            "upgrade_to": "silver",
            "cta": "Upgrade to Payla Silver",
            "upgrade_url": "/subscription",
            "current_plan": getattr(current, "plan", "free") or "free",
        },
    )


async def check_subscription_optional(
    user: Optional[User] = Depends(get_current_user),
) -> dict:
    """Return entitlement information without blocking a page."""
    if user is None:
        return {
            "has_access": False,
            "reason": "not_authenticated",
            "trial_active": False,
        }

    snapshot = db.collection("users").document(user.id).get()

    if not snapshot.exists:
        return {
            "has_access": False,
            "reason": "user_not_found",
            "trial_active": False,
        }

    data = snapshot.to_dict() or {}
    current = _build_user(data, user_id=user.id)
    entitlement_user = _entitlement_view(current, data)

    subscription_state = get_subscription_status(entitlement_user)
    subscription_active = has_active_subscription(entitlement_user)
    access = can_access_silver_features(entitlement_user)

    return {
        "has_access": access,
        "reason": None if access else "no_active_subscription",
        "plan": getattr(current, "plan", "free") or "free",
        "trial_active": False,
        "subscription_active": subscription_active,
        "in_grace_period": subscription_state["in_grace_period"],
        "days_left_in_grace": subscription_state["days_left_in_grace"],
        "should_upgrade": not access,
    }
