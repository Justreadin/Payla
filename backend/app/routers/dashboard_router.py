from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import logging

from app.utils.firebase import firestore_run
from app.core.firebase import db
from app.core.auth import get_current_user
from app.models.user_model import User
from app.models.invoice_model import Invoice
from app.core.config import settings
from google.cloud.firestore_v1.base_query import FieldFilter

logger = logging.getLogger("payla")
router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def require_login(user: Optional[User]) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def _invoice_payload(inv: Invoice) -> Dict[str, Any]:
    """Serialize an invoice for the dashboard response."""
    data = inv.dict(by_alias=True)

    data["invoice_url"] = (
        f"{settings.BACKEND_URL}{inv.invoice_url}"
        if inv.invoice_url
        else None
    )

    # Payment reference for receipt access — owner-only field.
    data["transaction_reference"] = getattr(inv, "transaction_reference", None)
    data["paystack_reference"] = getattr(inv, "paystack_reference", None)

    return data


def _build_entitlement(user: User) -> Dict[str, Any]:
    """
    Build the entitlement block used by the dashboard's soft gates and
    the renewal banner.

    `silver_history` values:
      active     — Silver is current
      cancelled  — Silver is active but renewal is off
      in_grace   — Silver is active through the renewal grace window
      expired    — Was Silver, is not now
      never      — Never subscribed to Silver
    """
    has_silver = user.can_access_silver_features()
    plan = (getattr(user, "plan", "free") or "free").lower()
    status = str(getattr(user, "subscription_status", "") or "").lower()

    cancel_at_period_end = bool(
        getattr(user, "cancel_at_period_end", False)
    )

    subscription_end = getattr(user, "subscription_end", None) or getattr(
        user, "next_billing_date", None
    )

    # Determine history.
    if has_silver:
        if cancel_at_period_end or status in {
            "non_renewing",
            "cancel_at_period_end",
            "cancellation_pending",
        }:
            history = "cancelled"
        elif status in {"past_due", "payment_failed", "unpaid"}:
            history = "in_grace"
        else:
            history = "active"
    else:
        was_silver = bool(
            getattr(user, "last_subscription_payment_at", None)
            or getattr(user, "founding_member_ever", False)
            or getattr(user, "subscription_id", None)
            or plan in {"silver", "gold", "opal"}
        )
        history = "expired" if was_silver else "never"

    days_in_grace = 0
    if history == "in_grace" and subscription_end is not None:
        from app.core.subscription import get_subscription_status
        sub = get_subscription_status(user)
        days_in_grace = int(sub.get("days_left_in_grace") or 0)

    return {
        "has_silver": has_silver,
        "plan": plan,
        "silver_history": history,
        "subscription_end": subscription_end,
        "cancel_at_period_end": cancel_at_period_end,
        "days_left_in_grace": days_in_grace,
    }


async def _compute_paylink_success_rate(
    user_id: str,
    username: str,
) -> str:
    """
    Compute the paylink success rate from the transaction log.

    Returns a formatted string like "66.7%" or "0%" when there are no
    attempts. Never raises — returns "0%" on any failure so the
    dashboard response is always well-formed.
    """
    attempts = 0
    successful = 0

    try:
        txns_query = (
            db.collection("paylink_transactions")
            .where(
                filter=FieldFilter(
                    "paylink_id", "in", [user_id, username]
                )
            )
            .stream()
        )

        for t in txns_query:
            data = t.to_dict() or {}
            attempts += 1
            if data.get("status") in ("success", "paid"):
                successful += 1

    except Exception:
        logger.exception(
            "Could not compute paylink success rate for user %s",
            user_id,
        )
        return "0%"

    if attempts <= 0:
        return "0%"

    return f"{round((successful / attempts) * 100, 1)}%"


@router.get("/", response_model=Dict[str, Any])
async def get_dashboard_data(current_user: Optional[User] = Depends(get_current_user)):
    user = require_login(current_user)

    user_id = user.id
    now = datetime.now(timezone.utc)

    total_earned = getattr(user, "total_earned", 0.0)
    invoice_revenue = getattr(user, "total_invoice_revenue", 0.0)
    paylink_revenue = getattr(user, "total_paylink_revenue", 0.0)
    subaccount_code = getattr(user, "paystack_subaccount_code", None)

    invoices_query = await firestore_run(
        db.collection("invoices")
        .where(filter=FieldFilter("sender_id", "==", user_id))
        .stream
    )

    invoices = []
    pending_amount = 0.0
    overdue_amount = 0.0
    overdue_count = 0

    for doc in invoices_query:
        inv_data = doc.to_dict()
        if inv_data.get("status") == "draft":
            continue

        inv_data["id"] = doc.id
        inv = Invoice(**inv_data)

        if inv.status == "pending" and inv.due_date:
            due_date_utc = inv.due_date.replace(tzinfo=timezone.utc)
            if due_date_utc < now:
                await firestore_run(
                    db.collection("invoices").document(inv.id).update,
                    {"status": "overdue", "updated_at": now}
                )
                inv.status = "overdue"

        if inv.status == "pending":
            pending_amount += inv.amount
        elif inv.status == "overdue":
            overdue_amount += inv.amount
            pending_amount += inv.amount
            overdue_count += 1

        invoices.append(inv)

    paylink_doc = await firestore_run(db.collection("paylinks").document(user_id).get)
    paylink_data = paylink_doc.to_dict() if paylink_doc.exists else {}
    paylink_url = paylink_data.get("link_url") or f"{settings.FRONTEND_URL}/@{user.username}"

    paylink_total_received = round(paylink_revenue, 2)
    paylink_total_transactions = int(paylink_data.get("total_transactions", 0))
    paylink_success_rate = await _compute_paylink_success_rate(
        user_id, user.username
    )

    next_settlement = now + timedelta(days=1)
    if now.weekday() >= 4:
        days_to_monday = (7 - now.weekday()) % 7
        next_settlement = now + timedelta(days=days_to_monday if days_to_monday > 0 else 7)

    entitlement = _build_entitlement(user)

    return {
        "stats": {
            "total_earned": round(total_earned, 2),
            "invoice_revenue": round(invoice_revenue, 2),
            "paylink_revenue": round(paylink_revenue, 2),
            "pending_amount": round(pending_amount, 2),
            "overdue_amount": round(overdue_amount, 2),
            "total_invoices": len(invoices),
            "overdue_count": overdue_count,
            "has_earnings": total_earned > 0,
            "is_subaccount_linked": bool(subaccount_code),
            "next_settlement_estimate": next_settlement.strftime("%Y-%m-%d")
        },
        "entitlement": entitlement,
        "invoices": [
            _invoice_payload(inv)
            for inv in sorted(
                invoices,
                key=lambda x: (
                    x.created_at if x.created_at.tzinfo else x.created_at.replace(tzinfo=timezone.utc)
                ) if x.created_at else now,
                reverse=True
            )[:10]
        ],
        "paylink": {
            "url": paylink_url,
            "total_received": paylink_total_received,
            "total_transactions": paylink_total_transactions,
            "success_rate": paylink_success_rate,
        }
    }