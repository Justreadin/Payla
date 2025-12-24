import logging
import requests
from pydantic import EmailStr
from app.core.config import settings

logger = logging.getLogger(__name__)

# Branding Constants
MIDNIGHT = "#0A0A0A"
ROSE = "#E8B4B8"
SOFT_WHITE = "#FDFDFD"

def send_email(to: str, subject: str, html: str, sender: str = None):
    """
    The base sender for all Payla emails.
    Connects to Resend API.
    """
    if not settings.RESEND_API_KEY:
        logger.error("RESEND_API_KEY not found in settings")
        return False

    # Default to Favour if no specific sender is provided
    from_email = sender or "Email • Payla <favour@payla.vip>"
    
    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {settings.RESEND_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "from": from_email,
        "to": [to],
        "subject": subject,
        "html": html
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        logger.info(f"Email sent successfully to {to} | Subject: {subject}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to}: {str(e)}")
        # In a 100% success rate model, we don't crash the app; 
        # the Service will catch this and try again on the next cron run.
        return False