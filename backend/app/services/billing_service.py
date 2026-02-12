# app/services/billing_service.py
import logging
import httpx
from app.core.config import settings

logger = logging.getLogger("payla.billing")

async def dispatch_billing_email(to_email, subject, html, sender):
    """
    High-priority dispatcher for billing using Resend directly.
    Bypasses reminder logic to ensure delivery.
    """
    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {settings.RESEND_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "from": f"Payla Billing <{sender}>", # e.g. billing.noreply@payla.vip
        "to": [to_email],
        "subject": subject,
        "html": html,
        "tags": [
            {"name": "category", "value": "billing"}
        ]
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            
        if response.status_code in [200, 201]:
            logger.info(f"📩 Billing email delivered via Resend to {to_email}")
            return True
        else:
            logger.error(f"❌ Resend API Error ({response.status_code}): {response.text}")
            return False

    except Exception as e:
        logger.error(f"💥 Critical Failure in billing dispatcher: {str(e)}")
        return False