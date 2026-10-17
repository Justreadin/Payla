
"""Small, defensive Paystack API client helpers for Payla."""
from __future__ import annotations

import logging
import math
import re
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import HTTPException

from app.core.config import settings


logger = logging.getLogger("payla.paystack")

PAYSTACK_BASE_URL = "https://api.paystack.co"
DEFAULT_CALLBACK_URL = "https://payla.ng/verify"
REQUEST_TIMEOUT_SECONDS = 20.0

# Paystack references should be treated as opaque identifiers, not URL syntax.
REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9._=-]{1,200}$")


def _headers() -> dict[str, str]:
    """Build authenticated Paystack request headers."""
    secret = getattr(settings, "PAYSTACK_SECRET_KEY", None)

    if not secret or not str(secret).strip():
        raise HTTPException(
            status_code=503,
            detail="Payment provider is not configured",
        )

    return {
        "Authorization": f"Bearer {secret}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _validate_reference(reference: str) -> str:
    """Reject malformed references before placing them in a URL."""
    if not isinstance(reference, str):
        raise HTTPException(
            status_code=400,
            detail="Invalid payment reference",
        )

    reference = reference.strip()

    if not REFERENCE_PATTERN.fullmatch(reference):
        raise HTTPException(
            status_code=400,
            detail="Invalid payment reference",
        )

    return quote(reference, safe="")


def _validate_amount_kobo(amount_kobo: int) -> int:
    """Validate an amount expressed in kobo."""
    if isinstance(amount_kobo, bool) or not isinstance(amount_kobo, int):
        raise HTTPException(
            status_code=400,
            detail="Payment amount must be a whole number of kobo",
        )

    if amount_kobo <= 0:
        raise HTTPException(
            status_code=400,
            detail="Payment amount must be greater than zero",
        )

    return amount_kobo


def _validate_amount_naira(amount: float) -> int:
    """Convert a naira amount to kobo without accepting invalid values."""
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        raise HTTPException(
            status_code=400,
            detail="Invalid payment amount",
        )

    if not math.isfinite(amount) or amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="Payment amount must be greater than zero",
        )

    amount_kobo = round(amount * 100)

    if amount_kobo <= 0:
        raise HTTPException(
            status_code=400,
            detail="Payment amount is too small",
        )

    return int(amount_kobo)


async def _request(
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
) -> dict:
    """Make an authenticated request and validate Paystack's response."""
    headers = _headers()

    try:
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT_SECONDS,
        ) as client:
            response = await client.request(
                method,
                f"{PAYSTACK_BASE_URL}{path}",
                headers=headers,
                json=json_body,
            )

            response.raise_for_status()

            try:
                result = response.json()
            except ValueError as exc:
                raise HTTPException(
                    status_code=502,
                    detail="Paystack returned an invalid response",
                ) from exc

    except HTTPException:
        raise

    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail=(
                "Paystack request timed out. Please check the payment "
                "status before retrying."
            ),
        ) from exc

    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code

        # TEMPORARY DIAGNOSTICS:
        # Do not log request headers, authorization tokens, or secret keys.
        # Remove or redact the response body after troubleshooting.
        logger.error(
            "Paystack HTTP error: method=%s path=%s status=%s body=%s",
            method,
            path,
            status_code,
            exc.response.text[:1000],
        )

        if status_code == 429:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Paystack is temporarily rate-limiting requests. "
                    "Please retry shortly."
                ),
            ) from exc

        raise HTTPException(
            status_code=502,
            detail="Paystack could not complete the request",
        ) from exc

    except httpx.RequestError as exc:
        # Log the exception class, not arbitrary request details.
        logger.warning(
            "Paystack network request failed: method=%s path=%s error_type=%s",
            method,
            path,
            type(exc).__name__,
        )

        raise HTTPException(
            status_code=502,
            detail="Paystack is temporarily unavailable",
        ) from exc

    if not isinstance(result, dict) or result.get("status") is not True:
        # Paystack can return HTTP 200 with status=false.
        # Log its message for temporary diagnostics without logging data.
        logger.error(
            "Paystack returned unsuccessful response: method=%s "
            "path=%s message=%s",
            method,
            path,
            str(result.get("message", "Unknown provider error"))[:300]
            if isinstance(result, dict)
            else "Invalid response structure",
        )

        raise HTTPException(
            status_code=502,
            detail="Paystack returned an unsuccessful response",
        )

    return result


async def initialize_payment(
    email: str,
    amount: float,
    metadata: dict,
) -> dict:
    """Initialize a one-time payment. Amount is expressed in naira."""
    if not isinstance(email, str) or not email.strip():
        raise HTTPException(
            status_code=400,
            detail="A valid customer email is required",
        )

    if not isinstance(metadata, dict):
        raise HTTPException(
            status_code=400,
            detail="Payment metadata must be an object",
        )

    amount_kobo = _validate_amount_naira(amount)

    callback_url = (
        getattr(settings, "PAYSTACK_CALLBACK_URL", None)
        or DEFAULT_CALLBACK_URL
    )

    result = await _request(
        "POST",
        "/transaction/initialize",
        json_body={
            "email": email.strip(),
            "amount": amount_kobo,
            "currency": "NGN",
            "metadata": metadata,
            "callback_url": callback_url,
        },
    )

    data = result.get("data")

    if not isinstance(data, dict):
        raise HTTPException(
            status_code=502,
            detail="Paystack returned an invalid checkout response",
        )

    if not data.get("authorization_url") or not data.get("reference"):
        raise HTTPException(
            status_code=502,
            detail="Paystack returned an incomplete checkout response",
        )

    return data


async def initialize_subscription_payment(
    *,
    email: str,
    amount_kobo: int,
    paystack_plan_code: str,
    reference: str,
    metadata: dict,
    callback_url: str,
) -> dict:
    """Initialize hosted checkout for a configured Paystack recurring plan.

    The subscription webhook must independently verify the initial payment
    before enabling paid access. A successful initialization is not payment.
    """
    if not isinstance(email, str) or not email.strip():
        raise HTTPException(
            status_code=400,
            detail="A valid customer email is required",
        )

    if (
        not isinstance(paystack_plan_code, str)
        or not paystack_plan_code.strip()
    ):
        raise HTTPException(
            status_code=503,
            detail="Silver billing plan is not configured",
        )

    if not isinstance(metadata, dict):
        raise HTTPException(
            status_code=400,
            detail="Subscription metadata must be an object",
        )

    # Validate the callback's basic URL structure.
    # This does not guarantee provider acceptance or page availability.
    if not isinstance(callback_url, str):
        raise HTTPException(
            status_code=500,
            detail="A valid HTTPS subscription callback URL is required",
        )

    callback_url = callback_url.strip()

    from urllib.parse import urlsplit

    parsed_callback = urlsplit(callback_url)

    if (
        parsed_callback.scheme != "https"
        or not parsed_callback.hostname
        or parsed_callback.username is not None
        or parsed_callback.password is not None
        or parsed_callback.query
        or parsed_callback.fragment
    ):
        raise HTTPException(
            status_code=500,
            detail="A valid HTTPS subscription callback URL is required",
        )

    # Safe callback diagnostics: do not log query strings or credentials.
    logger.info(
        "Subscription callback configured: scheme=%s host=%s path=%s valid=%s",
        parsed_callback.scheme,
        parsed_callback.hostname,
        parsed_callback.path,
        True,
    )

    amount_kobo = _validate_amount_kobo(amount_kobo)
    _validate_reference(reference)

    result = await _request(
        "POST",
        "/transaction/initialize",
        json_body={
            "email": email.strip(),
            "amount": amount_kobo,
            "currency": "NGN",
            "plan": paystack_plan_code.strip(),
            "reference": reference,
            "metadata": metadata,
            "callback_url": callback_url,
        },
    )

    data = result.get("data")

    if not isinstance(data, dict):
        raise HTTPException(
            status_code=502,
            detail="Paystack returned an invalid checkout response",
        )

    if not data.get("authorization_url") or not data.get("reference"):
        raise HTTPException(
            status_code=502,
            detail="Paystack returned an incomplete checkout response",
        )

    # Payla needs the reference it reserved in Firestore to match the
    # checkout and the eventual verified charge.
    if data["reference"] != reference:
        raise HTTPException(
            status_code=502,
            detail="Paystack returned a mismatched checkout reference",
        )

    return data


async def verify_payment(reference: str) -> dict:
    """Retrieve Paystack's transaction verification response."""
    safe_reference = _validate_reference(reference)

    return await _request(
        "GET",
        f"/transaction/verify/{safe_reference}",
    )


async def get_plan(plan_code: str) -> dict[str, Any]:
    """Fetch a Paystack plan to validate environment and pricing settings."""
    if not isinstance(plan_code, str) or not plan_code.strip():
        raise HTTPException(
            status_code=503,
            detail="Billing plan is not configured",
        )

    safe_plan_code = quote(plan_code.strip(), safe="")

    return await _request(
        "GET",
        f"/plan/{safe_plan_code}",
    )


async def disable_subscription(
    subscription_code: str,
    email_token: str,
) -> dict:
    """Ask Paystack to stop recurring charges for a subscription."""
    if (
        not isinstance(subscription_code, str)
        or not subscription_code.strip()
        or not isinstance(email_token, str)
        or not email_token.strip()
    ):
        raise HTTPException(
            status_code=400,
            detail="A cancellable subscription was not found",
        )

    return await _request(
        "POST",
        "/subscription/disable",
        json_body={
            "code": subscription_code.strip(),
            "token": email_token.strip(),
        },
    )


async def get_subscription_manage_link(
    subscription_code: str,
) -> str:
    """Generate a Paystack-hosted payment-method management link."""
    if (
        not isinstance(subscription_code, str)
        or not subscription_code.strip()
    ):
        raise HTTPException(
            status_code=400,
            detail="Subscription code is missing",
        )

    safe_code = quote(subscription_code.strip(), safe="")

    result = await _request(
        "GET",
        f"/subscription/{safe_code}/manage/link/",
    )

    data = result.get("data") or {}
    link = data.get("link") if isinstance(data, dict) else None

    if not isinstance(link, str) or not link.startswith("https://"):
        raise HTTPException(
            status_code=502,
            detail=(
                "Paystack did not return a valid payment-method "
                "management link"
            ),
        )

    return link
