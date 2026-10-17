"""
Async payment alert dispatcher.

Called from the Paystack webhook after a merchant payment is committed
and its payout record created. Sends one email: the creator alert.

Paystack sends the payer their own receipt at checkout. Payla does not
send the payer anything, for paylink or invoice payments.

Failure handling:
  Best-effort. A payment alert failure must never raise out of this
  function; the payment has already been recorded and a webhook retry
  would risk duplicate processing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.core.config import settings
from app.core.firebase import db
from app.utils.firebase import firestore_run
from app.utils.receipt_templates import RECEIPT_TEMPLATES


logger = logging.getLogger("payla.receipt_service")

RESEND_URL = "https://api.resend.com/emails"
SENDER_CREATOR = "Payla <receipts@payla.vip>"


def _ngn(amount: float) -> str:
    return f"\u20a6{amount:,.2f}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _backend_url() -> str:
    return str(settings.BACKEND_URL).rstrip("/")


def _app_url() -> str:
    return str(settings.APP_BASE_URL).rstrip("/")


async def _send_via_resend(
    to_email: str,
    subject: str,
    html: str,
    sender: str,
) -> bool:
    """Single async send. Returns True on 2xx, False on any failure."""
    if not settings.RESEND_API_KEY:
        logger.error("RESEND_API_KEY missing; payment alert not sent")
        return False

    payload = {
        "from": sender,
        "to": [to_email],
        "subject": subject,
        "html": html,
        "tags": [{"name": "category", "value": "payment_alert"}],
    }

    headers = {
        "Authorization": f"Bearer {settings.RESEND_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                RESEND_URL, json=payload, headers=headers
            )

        if response.status_code in (200, 201):
            return True

        logger.error(
            "Resend rejected payment alert for %s (%s): %s",
            to_email,
            response.status_code,
            response.text[:200],
        )
        return False

    except Exception:
        logger.exception("Resend request failed for %s", to_email)
        return False


def _creator_first_name(creator: dict) -> str:
    name = (
        creator.get("full_name")
        or creator.get("name")
        or creator.get("business_name")
        or "there"
    )
    return str(name).split()[0]


async def _invoice_action_url(invoice_id: str) -> Optional[str]:
    """
    Return the public invoice URL for the payment alert button.

    The invoice document stores its own invoice_url, built at publish
    time as f"{BACKEND_URL}/i/{short_id}". Read it; do not recompute.
    Fall back to reconstructing from the canonical ID if the field is
    missing.
    """
    try:
        snapshot = await firestore_run(
            db.collection("invoices").document(invoice_id).get
        )
    except Exception:
        logger.exception(
            "Could not read invoice %s for alert URL", invoice_id
        )
        return None

    if not snapshot.exists:
        logger.warning(
            "Invoice %s not found; alert will fall back", invoice_id
        )
        return None

    data = snapshot.to_dict() or {}
    stored = data.get("invoice_url")

    if isinstance(stored, str) and stored.strip():
        return stored.strip()

    short_id = invoice_id.removeprefix("inv_")
    return f"{_backend_url()}/i/{short_id}"


def _paylink_action_url() -> str:
    return f"{_app_url()}/payout"


async def dispatch_payment_receipts(
    user_id: str,
    reference: str,
    amount: float,
    payment_data: dict,
) -> dict:
    """
    Send the payment alert to the creator. Never raises.
    """
    result = {
        "creator_alert_sent": False,
        "errors": [],
    }

    creator_snapshot = await firestore_run(
        db.collection("users").document(str(user_id)).get
    )

    if not creator_snapshot.exists:
        msg = f"creator {user_id} not found for reference {reference}"
        logger.error(msg)
        result["errors"].append(msg)
        return result

    creator = creator_snapshot.to_dict() or {}
    creator_email = creator.get("email")

    if not creator_email:
        msg = f"creator {user_id} has no email; payment alert skipped"
        logger.error(msg)
        result["errors"].append(msg)
        return result

    amount_str = _ngn(float(amount))

    invoice_id = payment_data.get("invoice_id")
    paylink_id = payment_data.get("paylink_id")

    # Route the button by payment type.
    if invoice_id:
        action_url = await _invoice_action_url(invoice_id)
        button_label = "View invoice"
    else:
        action_url = _paylink_action_url()
        button_label = "View transaction"

    if not action_url:
        # Fall back to the payout page rather than shipping an empty href.
        action_url = _paylink_action_url()
        button_label = "View transaction"

    alert_tpl = RECEIPT_TEMPLATES["user_payment_alert"]

    try:
        alert_html = alert_tpl["html"](
            user_name=_creator_first_name(creator),
            amount=amount_str,
            client_email=payment_data.get("client_email") or "Your client",
            button_label=button_label,
            action_url=action_url,
        )
    except Exception:
        logger.exception("Failed to render payment alert for %s", reference)
        alert_html = None

    if alert_html:
        sent = await _send_via_resend(
            to_email=creator_email,
            subject=f"You just got paid {amount_str}",
            html=alert_html,
            sender=SENDER_CREATOR,
        )
        result["creator_alert_sent"] = sent
        if not sent:
            result["errors"].append("payment_alert_send_failed")

    await _mark_receipt_status(reference, result)
    return result


async def _mark_receipt_status(reference: str, result: dict) -> None:
    """Write a marker to the payment document. Never raises."""
    try:
        await firestore_run(
            db.collection("payments").document(reference).update,
            {
                "receipt_sent_at": _now(),
                "receipt_status": (
                    "sent" if result["creator_alert_sent"] else "failed"
                ),
                "receipt_errors": result.get("errors") or [],
            },
        )
    except Exception:
        logger.exception(
            "Could not write receipt marker to payment %s", reference
        )