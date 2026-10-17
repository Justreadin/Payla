# app/services/billing_service.py
import logging
import httpx

from app.core.config import settings

logger = logging.getLogger("payla.billing")


async def dispatch_billing_email(
    to_email: str,
    subject: str,
    html: str,
    sender: str,
) -> bool:
    """
    High-priority dispatcher for billing via Resend.
    Bypasses reminder logic to ensure delivery.
    """
    url = "https://api.resend.com/emails"

    headers = {
        "Authorization": f"Bearer {settings.RESEND_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "from": f"Payla Billing <{sender}>",
        "to": [to_email],
        "subject": subject,
        "html": html,
        "tags": [{"name": "category", "value": "billing"}],
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(url, headers=headers, json=payload)

        if response.status_code in (200, 201):
            logger.info(f"Billing email delivered to {to_email}")
            return True

        logger.error(
            f"Resend API error ({response.status_code}): {response.text[:200]}"
        )
        return False

    except Exception as e:
        logger.error(f"Critical failure in billing dispatcher: {e}")
        return False