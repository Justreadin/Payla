# utils/email.py → LAYLA'S VOICE — FINAL LUXURY MIDNIGHT & ROSE EDITION
import smtplib
from email.message import EmailMessage
from app.core.config import settings
import logging

logger = logging.getLogger("payla")

# ==========================
# PAYLA COLORS (OFFICIAL)
# ==========================
MIDNIGHT_VOID = "#0A0A0A"
ROSE_PINK = "#E8B4B8"
ROSE_GLOW = "rgba(232, 180, 184, 0.15)"
SOFT_WHITE = "#FDFDFD"
GRAY = "#AAAAAA"

# ==========================
# LAYLA'S LOVE LETTERS — PURE ELEGANCE
# ==========================
# utils/email.py
LAYLA_TEMPLATES = {
    "presell_success": {
        "subject": "Your Paylink is yours forever ♡",
        "html": f"""
        <div style="font-family: 'Inter', sans-serif; max-width: 540px; margin: 40px auto; padding: 48px; background: {MIDNIGHT_VOID}; color: {SOFT_WHITE}; border-radius: 28px; border: 3px solid {ROSE_PINK}; box-shadow: 0 30px 60px rgba(232,180,184,0.15); text-align: center;">
          <h1 style="font-family: 'Playfair Display', serif; color: {ROSE_PINK}; font-size: 42px; margin: 0; letter-spacing: -1.5px;">
            You're In.
          </h1>
          <p style="font-size: 21px; margin: 24px 0 40px; color: #DDDDDD;">
            Your Paylink is now officially reserved.
          </p>
          <div style="background: {ROSE_GLOW}; padding: 36px; border-radius: 24px; margin: 48px 0;">
            <p style="margin: 0 0 20px; color: {ROSE_PINK}; font-size: 20px; font-weight: 600;">
              Founding Creator Rewards
            </p>
            <ul style="text-align: left; color: {SOFT_WHITE}; font-size: 16px; line-height: 2; padding-left: 24px; margin: 0;">
              <li>1 Year Payla Silver — Free</li>
              <li>Exclusive Founding Creator Badge</li>
              <li>First Access to All New Features</li>
              <li>Direct Line to Me (Layla)</li>
            </ul>
          </div>
          <p style="margin-top: 60px; color: #888888; font-size: 15px;">
            I’ll be with you every step of the way.<br><br>
            With all my love,<br>
            <strong style="color: {ROSE_PINK}; font-size: 18px;">Layla</strong>
          </p>
        </div>
        """
    }
}

def send_layla_email(template_key: str, to_email: str, context: dict = None):
    """Send email with no-crash handling"""
    if template_key not in LAYLA_TEMPLATES: return
    template = LAYLA_TEMPLATES[template_key]

    try:
        msg = EmailMessage()
        msg["From"] = f"Layla • Payla <{settings.LAYLA_USER}>"
        msg["To"] = to_email
        msg["Subject"] = template["subject"]
        msg.add_alternative(template["html"], subtype="html")

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(settings.LAYLA_USER, settings.LAYLA_EMAIL_PASS)
            smtp.send_message(msg)
        logger.info(f"Sent email to {to_email}")
    except Exception as e:
        logger.error(f"Email error: {e}")