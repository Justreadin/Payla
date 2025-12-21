import asyncio
import httpx
import logging
import resend
from app.core.config import settings


logger = logging.getLogger("payla")

# -------------------------------------------------------------------
# Provider setup
# -------------------------------------------------------------------

WHATSAPP_API_URL = (
    f"https://graph.facebook.com/v24.0/{settings.WHATSAPP_PHONE_ID}/messages"
)

resend.api_key = settings.RESEND_API_KEY


# -------------------------------------------------------------------
# WhatsApp
# -------------------------------------------------------------------

async def send_via_whatsapp(phone: str, message: str) -> None:
    """
    Send WhatsApp message via Meta Graph API.
    Raises exception on ANY failure.
    """

    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": message},
    }

    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    logger.info(
        f"[WhatsApp] Attempting send | phone={phone} | chars={len(message)}"
    )

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            WHATSAPP_API_URL, json=payload, headers=headers
        )

        if response.status_code >= 400:
            logger.error(
                f"[WhatsApp] API error {response.status_code} | {response.text}"
            )
            raise RuntimeError(
                f"WhatsApp send failed ({response.status_code})"
            )

        data = response.json()
        logger.info(
            f"[WhatsApp] Delivered successfully | phone={phone} | response={data}"
        )


# -------------------------------------------------------------------
# SMS (Termii)
# -------------------------------------------------------------------

async def send_via_sms(phone: str, message: str) -> None:
    """
    Send SMS via Termii (Nigerian numbers only).
    Raises exception on ANY failure.
    """

    truncated_msg = message[:160]
    phone_clean = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")

    # Check if Nigerian number
    is_nigerian = (
        phone_clean.startswith("+234") or
        phone_clean.startswith("234") or
        (phone_clean.startswith("0") and len(phone_clean) == 11)
    )
    
    if not is_nigerian:
        logger.warning(
            f"[SMS] Non-Nigerian number detected: {phone_clean}. Termii only supports Nigerian numbers. "
            f"For international SMS, configure Twilio or another provider."
        )
        raise RuntimeError(f"SMS only available for Nigerian numbers (+234). Got: {phone}")

    # Normalize Nigerian phone numbers
    if phone_clean.startswith("+234"):
        phone_clean = phone_clean[1:]  # Remove + sign → 2348012345678
    elif phone_clean.startswith("0") and len(phone_clean) == 11:
        phone_clean = "234" + phone_clean[1:]  # 08012345678 → 2348012345678
    elif not phone_clean.startswith("234"):
        phone_clean = "234" + phone_clean  # 8012345678 → 2348012345678

    sender = settings.TERMII_SENDER_ID

    payload = {
        "to": phone_clean,
        "from": sender,
        "sms": truncated_msg,
        "type": "plain",  # Changed from "transactional"
        "channel": "generic",
        "api_key": settings.TERMII_API_KEY,
    }

    logger.info(
        f"[SMS] Attempting send | phone={phone_clean} | sender={sender} | msg_length={len(truncated_msg)}"
    )
    logger.debug(f"[SMS] Payload: {payload}")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://api.ng.termii.com/api/sms/send",
                json=payload,
            )

            logger.info(f"[SMS] Response status: {response.status_code}")
            logger.info(f"[SMS] Response body: {response.text}")

            if response.status_code >= 400:
                logger.error(
                    f"[SMS] HTTP error {response.status_code} | {response.text}"
                )
                raise RuntimeError(f"Termii SMS HTTP failure: {response.status_code}")

            try:
                data = response.json()
            except Exception as json_err:
                logger.error(f"[SMS] Failed to parse response JSON: {json_err}")
                raise RuntimeError("Termii SMS response not valid JSON")

            # Termii can return different response formats
            # Check for common success indicators
            message_id = data.get("message_id") or data.get("messageId")
            code = data.get("code")
            
            # Success conditions:
            # - Has message_id
            # - code == "ok"
            # - pinId exists (for some message types)
            is_success = (
                message_id is not None or 
                code == "ok" or
                data.get("pinId") is not None or
                "balance" in data  # Balance returned means API accepted it
            )

            if not is_success:
                logger.error(f"[SMS] Rejected by Termii | response={data}")
                raise RuntimeError(f"Termii SMS rejected: {data.get('message', 'Unknown error')}")

            logger.info(
                f"[SMS] ✅ Delivered successfully | phone={phone_clean} | response={data}"
            )

    except httpx.TimeoutException as e:
        logger.error(f"[SMS] Timeout error | phone={phone_clean} | error={e}")
        raise RuntimeError("Termii SMS timeout")
    except httpx.RequestError as e:
        logger.error(f"[SMS] Request error | phone={phone_clean} | error={e}")
        raise RuntimeError(f"Termii SMS request failed: {str(e)}")
    except Exception as e:
        logger.error(f"[SMS] Unexpected error | phone={phone_clean} | error={e}")
        raise


# -------------------------------------------------------------------
# Email (Resend)
# -------------------------------------------------------------------

async def send_via_email(
    email: str,
    subject: str,
    html: str,
    email_type: str = "noreply",
) -> None:
    """
    Send email via Resend.
    Raises exception on ANY failure.
    """

    sender_mapping = {
        "reminder": "Reminder • Payla <reminders@payla.vip>",
        "layla": "Layla • Payla <layla@payla.vip>",
        "billing": "Payla Billing <billing.noreply@payla.vip>",
        "noreply": "Payla <support@payla.vip>",
        "payment_received": "Payla <support@payla.vip>",
    }

    from_email = sender_mapping.get(
        email_type, sender_mapping["noreply"]
    )

    logger.info(
        f"[Email] Attempting send | to={email} | type={email_type} | subject={subject}"
    )

    loop = asyncio.get_running_loop()

    try:
        result = await loop.run_in_executor(
            None,
            lambda: resend.Emails.send(
                {
                    "from": from_email,
                    "to": email,
                    "subject": subject,
                    "html": html,
                }
            ),
        )

        logger.info(
            f"[Email] ✅ Delivered successfully | to={email} | from={from_email} | result={result}"
        )

    except Exception as e:
        logger.error(
            f"[Email] ❌ Failed | to={email} | error={e}"
        )
        raise RuntimeError(f"Email send failed: {str(e)}")