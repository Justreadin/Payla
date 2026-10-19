
import httpx
import logging
from datetime import datetime, timezone

from app.core.config import settings

logger = logging.getLogger("payla")


async def create_paystack_subaccount(
    business_name: str,
    bank_code: str,
    account_number: str,
) -> str:
    """
    Create a Paystack subaccount for a creator.

    Returns:
        The Paystack subaccount code, e.g. ACCT_xxxxxx.

    Raises:
        HTTPException:
            400: Paystack rejected the supplied details.
            502: Paystack returned an unexpected/provider error.
            503: Paystack is temporarily unavailable or rate-limited.
            504: The request timed out.
    """
    from fastapi import HTTPException

    url = "https://api.paystack.co/subaccount"

    secret_key = settings.PAYSTACK_SECRET_KEY
    if not secret_key:
        logger.error("PAYSTACK_SECRET_KEY is not configured")
        raise HTTPException(
            status_code=500,
            detail="Payment service is not configured.",
        )

    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "business_name": business_name.strip(),
        "settlement_bank": bank_code,
        "account_number": account_number.strip(),
        "percentage_charge": 0,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers=headers,
            )

    except httpx.TimeoutException:
        logger.warning(
            "Paystack subaccount request timed out for business %s",
            business_name,
        )
        raise HTTPException(
            status_code=504,
            detail="Paystack took too long to set up your payout account. Please try again.",
        )

    except httpx.RequestError:
        logger.exception(
            "Network error creating Paystack subaccount for business %s",
            business_name,
        )
        raise HTTPException(
            status_code=503,
            detail="Paystack is temporarily unreachable. Please try again shortly.",
        )

    # Parse the provider response safely.
    try:
        response_data = response.json()
    except ValueError:
        logger.error(
            "Paystack returned non-JSON subaccount response: HTTP %s",
            response.status_code,
        )
        raise HTTPException(
            status_code=502,
            detail="Paystack returned an unexpected response. Please try again.",
        )

    provider_message = (
        response_data.get("message", "Unknown Paystack error")
        if isinstance(response_data, dict)
        else "Unexpected Paystack response"
    )

    # Success requires both an HTTP success status and a valid response body.
    if (
        response.status_code in (200, 201)
        and isinstance(response_data, dict)
        and response_data.get("status") is True
    ):
        data = response_data.get("data") or {}
        subaccount_code = data.get("subaccount_code")

        if not subaccount_code:
            logger.error(
                "Paystack reported subaccount success without a subaccount code"
            )
            raise HTTPException(
                status_code=502,
                detail="Paystack did not return a payout subaccount code.",
            )

        logger.info(
            "Paystack subaccount created successfully for business %s",
            business_name,
        )
        return subaccount_code

    # Log the status and provider message, but never log the secret key.
    logger.error(
        "Paystack subaccount creation failed: HTTP %s; message=%s",
        response.status_code,
        provider_message,
    )

    # Rate limiting or temporary provider unavailability.
    if response.status_code == 429 or response.status_code >= 500:
        raise HTTPException(
            status_code=503,
            detail="Paystack is temporarily unavailable or rate-limited. Please try again later.",
        )

    # Credentials/configuration errors should not be presented as invalid
    # creator bank details.
    if response.status_code in (401, 403):
        raise HTTPException(
            status_code=502,
            detail="Paystack authentication failed. Please contact support.",
        )

    # These responses commonly indicate rejected input. Other 4xx responses
    # are reported as provider request errors rather than assumed to be
    # invalid bank details.
    if response.status_code in (400, 404, 422):
        raise HTTPException(
            status_code=400,
            detail="Paystack rejected the payout details. Please check the bank and account information.",
        )

    raise HTTPException(
        status_code=502,
        detail="Unable to create the payout subaccount with Paystack.",
    )

# --- UPDATED: Permanent Payment Page ---
async def create_permanent_payment_page(username: str, display_name: str, subaccount_code: str = None) -> dict:
    """
    Creates a Paystack Payment Page. 
    If subaccount_code is provided, money is automatically routed to the creator.
    """
    base_slug = f"payla-{username.lower()}"
    url = "https://api.paystack.co/page"
    headers = {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "name": f"Pay {display_name} (@{username})",
        "description": f"Send money to @{username} via Payla",
        "amount": None,
        "redirect_url": f"{settings.FRONTEND_URL}/payment-success",
    }

    # If user has a subaccount, attach it to the page
    if subaccount_code:
        payload["subaccount"] = subaccount_code
        # 'subaccount' means the creator pays the Paystack fee (1.5% + ₦100)
        # 'account' means Payla (you) pays the fee. 
        payload["bearer"] = "subaccount" 

    # Try numeric suffixes for slug uniqueness
    async with httpx.AsyncClient(timeout=15.0) as client:
        for i in range(10):
            slug = base_slug if i == 0 else f"{base_slug}-{i+2}"
            payload["slug"] = slug

            try:
                response = await client.post(url, json=payload, headers=headers)
                
                if response.status_code in (200, 201):
                    data = response.json()["data"]
                    return {
                        "url": data.get("url") or f"https://paystack.com/pay/{data['slug']}",
                        "reference": str(data["id"]),
                        "slug": data["slug"]
                    }

                if response.status_code == 400:
                    error_msg = response.json().get("message", "")
                    if "slug already exists" in error_msg.lower():
                        continue
                    raise ValueError(error_msg)

                response.raise_for_status()
            except Exception as e:
                logger.error(f"Slug attempt {i} failed for @{username}: {e}")

        # Final Fallback: Timestamp slug
        timestamp_slug = f"{base_slug}-{int(datetime.now(timezone.utc).timestamp())}"
        payload["slug"] = timestamp_slug
        response = await client.post(url, json=payload, headers=headers)
        data = response.json()["data"]
        return {
            "url": data.get("url") or f"https://paystack.com/pay/{data['slug']}",
            "reference": str(data["id"]),
            "slug": data["slug"]
        }