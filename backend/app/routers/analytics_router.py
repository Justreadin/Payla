from fastapi import APIRouter, Depends
from datetime import datetime, timezone
from typing import Any

from app.core.firebase import db
from app.core.auth import get_current_user
from app.core.analytics import get_paylink_analytics
from app.core.subscription import require_silver
from app.models.user_model import User
from google.cloud.firestore_v1.base_query import FieldFilter


router = APIRouter(prefix="/dashboard/analytics", tags=["Analytics"])


# ============================================================
# HELPERS
# ============================================================

def _as_utc(value: Any):
    """Normalize Firestore or Python datetimes to a UTC datetime."""
    if value is None:
        return None

    if isinstance(value, datetime):
        dt = value
    elif hasattr(value, "to_datetime"):
        try:
            dt = value.to_datetime()
        except Exception:
            return None
    elif isinstance(value, dict) and "seconds" in value:
        try:
            return datetime.fromtimestamp(
                float(value["seconds"]), tz=timezone.utc
            )
        except (TypeError, ValueError, OverflowError, OSError):
            return None
    elif isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(
                float(value), tz=timezone.utc
            )
        except (TypeError, ValueError, OverflowError, OSError):
            return None
    else:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def _month_window(now: datetime):
    """Return (start_of_this_month, start_of_last_month) in UTC."""
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    if month_start.month == 1:
        last_month_start = month_start.replace(
            year=month_start.year - 1, month=12
        )
    else:
        last_month_start = month_start.replace(month=month_start.month - 1)

    return month_start, last_month_start


def _collect_payments(user_id: str, cap: int = 50):
    """
    Read the canonical `payments` collection for this merchant.

    Uses a composite (user_id, status) query — requires a Firestore
    composite index. If the index is missing, Firestore returns an
    error with a link to create it; the router logs and returns an
    empty list rather than failing the request.

    Amount is the merchant's net share (`user_share`) so it matches
    the earnings figures used everywhere else.
    """
    payments = []

    try:
        payments_query = (
            db.collection("payments")
            .where(filter=FieldFilter("user_id", "==", user_id))
            .where(filter=FieldFilter("status", "==", "success"))
            .stream()
        )

        for doc in payments_query:
            data = doc.to_dict() or {}

            amount = data.get("user_share")
            if amount is None:
                amount = data.get("amount") or 0

            source = "invoice" if data.get("invoice_id") else "paylink"

            payments.append({
                "reference": data.get("paystack_reference") or doc.id,
                "amount": float(amount or 0),
                "currency": data.get("currency") or "NGN",
                "source": source,
                "invoice_id": data.get("invoice_id"),
                "paylink_id": data.get("paylink_id"),
                "client_email": data.get("client_email"),
                "paid_at": _as_utc(
                    data.get("paid_at") or data.get("created_at")
                ),
            })

    except Exception:
        import logging
        logging.getLogger("payla").exception(
            "Payments query failed for user %s. If this is a missing "
            "composite index, Firestore's error message includes a "
            "direct link to create it.",
            user_id,
        )
        return payments

    payments.sort(
        key=lambda p: p.get("paid_at")
        or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    return payments[:cap]


def _serialize_payment(payment: dict):
    paid_at = payment.get("paid_at")

    return {
        "reference": payment.get("reference"),
        "amount": payment.get("amount", 0),
        "currency": payment.get("currency", "NGN"),
        "source": payment.get("source", "paylink"),
        "invoice_id": payment.get("invoice_id"),
        "paylink_id": payment.get("paylink_id"),
        "client_email": payment.get("client_email"),
        "paid_at": paid_at.isoformat() if isinstance(paid_at, datetime) else None,
    }


def _aggregate_payments(payments):
    """
    Compute month-over-month, weekday totals, average, and source split
    from the recent payments slice.
    """
    now = datetime.now(timezone.utc)
    month_start, last_month_start = _month_window(now)

    this_month_total = 0.0
    last_month_total = 0.0
    total_amount = 0.0
    invoice_total = 0.0
    paylink_total = 0.0

    weekday_keys = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    weekday_totals = {key: 0.0 for key in weekday_keys}

    for payment in payments:
        paid_at = payment.get("paid_at")
        amount = float(payment.get("amount") or 0)
        source = payment.get("source")

        total_amount += amount

        if source == "invoice":
            invoice_total += amount
        else:
            paylink_total += amount

        if not isinstance(paid_at, datetime):
            continue

        if paid_at >= month_start:
            this_month_total += amount
        elif paid_at >= last_month_start:
            last_month_total += amount

        weekday_totals[weekday_keys[paid_at.weekday()]] += amount

    payment_count = len(payments)
    average_payment = (total_amount / payment_count) if payment_count else 0.0

    return {
        "this_month_revenue": round(this_month_total, 2),
        "last_month_revenue": round(last_month_total, 2),
        "weekday_totals": {
            key: round(value, 2) for key, value in weekday_totals.items()
        },
        "average_payment": round(average_payment, 2),
        "net_invoice_revenue": round(invoice_total, 2),
        "net_paylink_revenue": round(paylink_total, 2),
    }


# ============================================================
# MAIN ANALYTICS BUILDER
# ============================================================

async def fetch_full_analytics(current_user: User) -> dict:
    user_id = current_user.id
    username = current_user.username

    paylink_ref = db.collection("paylinks").document(user_id)
    paylink_doc = paylink_ref.get()

    # ── Payment source stats ──
    # We collect `payments` (canonical, net) for everything downstream.
    # The paylink transaction scan produces the funnel numbers: total
    # attempts (any status), successful attempts, and the paylink net
    # amount as recorded on the transaction itself.
    payments = _collect_payments(user_id)
    aggregates = _aggregate_payments(payments)

    # Default paylink stats.
    paylink_net = 0.0
    paylink_attempts = 0
    paylink_successful = 0
    funnel_views = 0
    funnel_taps = 0

    if paylink_doc.exists:
        txns_query = db.collection("paylink_transactions").where(
            filter=FieldFilter("paylink_id", "in", [user_id, username])
        ).stream()

        for t in txns_query:
            data = t.to_dict() or {}
            paylink_attempts += 1

            if data.get("status") in ("success", "paid"):
                paylink_successful += 1
                # Net to merchant is the *requested* amount, not the
                # gross charge. This matches user_share on the payments
                # record and everything the merchant sees elsewhere.
                requested = data.get("amount_requested")
                if requested is None:
                    requested = data.get("amount") or 0
                paylink_net += float(requested)

        analytics_data = get_paylink_analytics(user_id)
        funnel_views = int(analytics_data.get("page_views", 0))
        funnel_taps = int(analytics_data.get("transfer_clicks", 0))
        daily_views = analytics_data.get("daily_page_views", {})
        daily_clicks = analytics_data.get("daily_transfer_clicks", {})
    else:
        daily_views = {}
        daily_clicks = {}

    # Success rate as both a fraction and a percentage, so the UI can
    # show "6 of 9 attempts" rather than an unlabelled percentage.
    success_fraction_label = (
        f"{paylink_successful} of {paylink_attempts}"
        if paylink_attempts > 0
        else "No attempts yet"
    )

    success_rate_pct = 0.0
    if paylink_attempts > 0:
        success_rate_pct = round(
            (paylink_successful / paylink_attempts) * 100, 1
        )

    # Funnel — the four numbers that describe drop-off. Any value that
    # is missing stays as zero so the UI can render the shape.
    funnel = {
        "views": funnel_views,
        "taps": funnel_taps,
        "attempts": paylink_attempts,
        "paid": paylink_successful,
    }

    # Average payment across all sources, computed from the payments
    # slice. For a merchant with more than `cap` payments this is an
    # approximation; acceptable for a snapshot.
    average_payment = aggregates["average_payment"]

    return {
        # Link-only stats (the tile grid).
        "total_received": round(paylink_net, 2),
        "total_transactions": paylink_successful,
        "success_rate": f"{success_rate_pct}%",
        "success_fraction": success_fraction_label,
        "success_rate_pct": success_rate_pct,
        "successful_attempts": paylink_successful,
        "total_attempts": paylink_attempts,

        # Page and click data.
        "page_views": funnel_views,
        "transfer_clicks": funnel_taps,
        "daily_page_views": daily_views,
        "daily_transfer_clicks": daily_clicks,

        # Funnel.
        "funnel": funnel,

        # Payments and aggregates (all sources).
        "payments": [_serialize_payment(p) for p in payments],
        "average_payment": average_payment,
        "this_month_revenue": aggregates["this_month_revenue"],
        "last_month_revenue": aggregates["last_month_revenue"],
        "weekday_totals": aggregates["weekday_totals"],
        "net_invoice_revenue": aggregates["net_invoice_revenue"],
        "net_paylink_revenue": aggregates["net_paylink_revenue"],

        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


# ============================================================
# ROUTES
# ============================================================

@router.get("/")
async def get_analytics_slash(
    current_user: User = Depends(require_silver),
):
    return await fetch_full_analytics(current_user)


@router.get("")
async def get_analytics_no_slash(
    current_user: User = Depends(require_silver),
):
    return await fetch_full_analytics(current_user)