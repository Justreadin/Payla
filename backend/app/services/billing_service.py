# app/services/billing_service.py
import logging
from app.services.reminder_service import send_via_email # Reusing the low-level sender

logger = logging.getLogger("payla.billing")

async def dispatch_billing_email(to_email, subject, html, sender):
    """
    Independent dispatcher for billing. 
    Does not respect 'Quiet Hours' because billing alerts are critical.
    """
    try:
        # Direct call to the low-level email sender
        await send_via_email(
            to_email=to_email,
            subject=subject,
            html=html,
            email_type="billing",
            sender=sender
        )
        return True
    except Exception as e:
        logger.error(f"Postmark/Mailgun error sending billing email to {to_email}: {e}")
        return False