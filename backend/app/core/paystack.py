import httpx
import logging
from app.core.config import settings
from datetime import datetime

logger = logging.getLogger("payla")

async def create_permanent_payment_page(username: str, display_name: str) -> dict:
    """
    Creates a Paystack Payment Page.
    Tries numeric suffixes first; if all fail, appends timestamp to ensure uniqueness.
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

    # Try numeric suffixes first
    for i in range(10):
        slug = base_slug if i == 0 else f"{base_slug}-{i+2}"
        payload["slug"] = slug

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, json=payload, headers=headers)

            if response.status_code in (200, 201):
                data = response.json()["data"]
                page_url = data.get("url") or f"https://paystack.com/pay/{data['slug']}"
                logger.info(f"Paystack page created for @{username}: {page_url}")
                return {
                    "url": page_url,
                    "reference": str(data["id"]),
                    "slug": data["slug"]
                }

            if response.status_code == 400:
                error_msg = response.json().get("message", "")
                if "slug already exists" in error_msg.lower():
                    logger.warning(f"Slug {slug} taken, trying next...")
                    continue
                else:
                    raise ValueError(error_msg)

            response.raise_for_status()

        except Exception as e:
            logger.error(f"Attempt {i+1} failed for @{username}: {e}")

    # All numeric suffixes failed → append timestamp
    timestamp_slug = f"{base_slug}-{int(datetime.utcnow().timestamp())}"
    payload["slug"] = timestamp_slug
    logger.info(f"All numeric slugs taken for @{username}, trying timestamp slug {timestamp_slug}")

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()["data"]
        page_url = data.get("url") or f"https://paystack.com/pay/{data['slug']}"
        logger.info(f"Paystack page created for @{username}: {page_url}")
        return {
            "url": page_url,
            "reference": str(data["id"]),
            "slug": data["slug"]
        }
