import asyncio
import httpx
import logging
from app.core.config import settings

logger = logging.getLogger("payla")

WHATSAPP_API_URL = f"https://graph.facebook.com/v24.0/{settings.WHATSAPP_PHONE_ID}/messages"

async def send_via_whatsapp(phone: str, message: str):
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": message}
    }

    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(WHATSAPP_API_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

            logger.info(f"WhatsApp message sent: {data}")
            return {"success": True, "response": data}

    except httpx.HTTPStatusError as e:
        logger.error(f"WhatsApp API error: {e.response.status_code} {e.response.text}")
        return {"success": False, "error": e.response.text}

    except Exception as e:
        logger.error(f"Unknown WhatsApp error: {e}")
        return {"success": False, "error": str(e)}



async def send_via_sms(phone: str, message: str):
    """
    Send SMS via Termii.
    - Detects Nigerian vs international numbers automatically.
    - Truncates to 160 characters.
    """
    try:
        # Ensure message is max 160 chars for SMS
        truncated_msg = message[:160] if len(message) > 160 else message

        # Normalize phone number (remove spaces, dashes)
        phone_clean = phone.replace(" ", "").replace("-", "")

        # Check if number is Nigerian (+234 or 0 prefix)
        if phone_clean.startswith("0"):
            phone_clean = "+234" + phone_clean[1:]
            sender = settings.TERMII_SENDER_ID
            channel = "generic"  # For domestic transactional
        elif phone_clean.startswith("+234"):
            sender = settings.TERMII_SENDER_ID
            channel = "generic"
        else:
            # International number
            sender = "Termii"  # Termii will assign numeric ID if Sender ID not allowed
            channel = "generic"

        payload = {
            "to": phone_clean,
            "from": sender,
            "sms": truncated_msg,
            "type": "transactional",
            "channel": channel,
            "api_key": settings.TERMII_API_KEY
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.ng.termii.com/api/sms/send",
                json=payload
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "successful":
                logger.info(f"Termii SMS sent: {data.get('message_id', 'no-id')}")
                return {"success": True, "sid": data.get("message_id")}
            else:
                logger.warning(f"Termii SMS failed: {data}")
                return {"success": False}

    except httpx.HTTPStatusError as e:
        logger.error(f"Termii HTTP error: {e.response.status_code} - {e.response.text}")
        return {"success": False}
    except Exception as e:
        logger.error(f"Termii SMS failed: {e}")
        return {"success": False}


async def send_via_email(email: str, subject: str, html: str, email_type: str = "noreply"):
    sender_mapping = {
        "reminder": "Reminder • Payla<reminders@payla.vip>",
        "layla": "Layla • Payla<layla@payla.vip>",
        "billing": "Payla Billing <billing.noreply@payla.vip>",
        "noreply": "Payla <support@payla.vip>"
    }
    from_email = sender_mapping.get(email_type, "Payla <support@payla.vip>")

    try:
        loop = asyncio.get_running_loop()
        # Run blocking Resend call in threadpool
        result = await loop.run_in_executor(
            None,
            lambda: resend.Emails.send({
                "from": from_email,
                "to": email,
                "subject": subject,
                "html": html
            })
        )
        logger.info(f"Email sent to {email} via {from_email}")
        return {"success": True}

    except Exception as e:
        logger.error(f"Email failed to {email} via {email_type}: {e}")
        return {"success": False}
