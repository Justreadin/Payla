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
LAYLA_TEMPLATES = {
    "waitlist_welcome": {
        "subject": "Welcome to the Payla Family, {name} ♡",
        "html": f"""
        <div style="font-family: 'Inter', sans-serif; max-width: 520px; margin: 40px auto; padding: 40px; background: {MIDNIGHT_VOID}; color: {SOFT_WHITE}; border-radius: 24px; border: 2px solid {ROSE_PINK}; box-shadow: 0 20px 40px rgba(232,180,184,0.1);">
          <h1 style="font-family: 'Playfair Display', serif; color: {ROSE_PINK}; font-size: 38px; text-align: center; margin: 0 0 16px 0; letter-spacing: -1px;">
            Welcome home, {{name}}
          </h1>
          <p style="text-align: center; font-size: 17px; line-height: 1.7; color: #CCCCCC; margin-bottom: 40px;">
            I’m Layla — your personal assistant at Payla.<br>
            You just joined a quiet movement of creators who want more than just payments.
          </p>

          <div style="background: {ROSE_GLOW}; padding: 32px; border-radius: 20px; text-align: center; margin: 40px 0;">
            <p style="margin: 0; font-size: 19px; color: {ROSE_PINK}; font-weight: 600;">
              We launch in early 2025
            </p>
            <p style="margin: 16px 0 0; color: #BBBBBB; font-size: 15px;">
              You’ll be the first to claim your Paylink when we open the doors.
            </p>
          </div>

          <p style="text-align: center; font-size: 16px; color: #999999; line-height: 1.8;">
            Until then, rest easy.<br>
            I’ll write to you the moment it’s ready.
          </p>

          <p style="text-align: center; margin-top: 50px; color: #888888; font-size: 15px;">
            With warmth and quiet excitement,<br>
            <strong style="color: {ROSE_PINK};">Layla</strong><br>
            <span style="font-size: 13px; color: #666666;">Your assistant at Payla</span>
          </p>
        </div>
        """
    },

    "presell_success": {
        "subject": "Your Paylink @{username} is yours forever ♡",
        "html": f"""
        <div style="font-family: 'Inter', sans-serif; max-width: 540px; margin: 40px auto; padding: 48px; background: {MIDNIGHT_VOID}; color: {SOFT_WHITE}; border-radius: 28px; border: 3px solid {ROSE_PINK}; box-shadow: 0 30px 60px rgba(232,180,184,0.15); text-align: center;">
          <h1 style="font-family: 'Playfair Display', serif; color: {ROSE_PINK}; font-size: 42px; margin: 0; letter-spacing: -1.5px;">
            You're In, {{name}}
          </h1>
          <p style="font-size: 21px; margin: 24px 0 40px; color: #DDDDDD;">
            Your Paylink is now officially reserved:
          </p>

          <div style="margin: 40px 0;">
            <h2 style="color: {ROSE_PINK}; font-size: 36px; margin: 0; font-weight: 700;">
              payla.ng/@{{username}}
            </h2>
            <p style="color: #999999; margin: 12px 0 0; font-size: 16px;">
              This link is yours. Forever.
            </p>
          </div>

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

          <p style="font-size: 18px; color: #BBBBBB; line-height: 1.8;">
            You didn’t just pay for a tool.<br>
            You invested in something beautiful.
          </p>

          <p style="margin-top: 60px; color: #888888; font-size: 15px;">
            I’ll be with you every step of the way.<br><br>
            With all my love,<br>
            <strong style="color: {ROSE_PINK}; font-size: 18px;">Layla</strong>
          </p>
        </div>
        """
    },

    "launch_day_1": {
        "subject": "Payla is LIVE — Your Link Awaits, {name} ♡",
        "html": f"""
        <div style="font-family: 'Inter', sans-serif; max-width: 520px; margin: 40px auto; padding: 48px; background: {MIDNIGHT_VOID}; color: {SOFT_WHITE}; border-radius: 28px; border: 3px solid {ROSE_PINK}; text-align: center;">
          <h1 style="font-family: 'Playfair Display', serif; color: {ROSE_PINK}; font-size: 44px; margin: 0;">
            We’re Live
          </h1>
          <p style="font-size: 20px; margin: 32px 0 48px; color: #CCCCCC;">
            The day has come.
          </p>

          <div style="margin: 48px 0;">
            <h2 style="color: {ROSE_PINK}; font-size: 38px; margin: 0;">
              payla.ng/@{{username}}
            </h2>
            <p style="color: #999999; margin: 16px 0; font-size: 17px;">
              Your Paylink is ready and waiting.
            </p>
          </div>

          <div style="margin: 48px 0;">
            <a href="https://payla.ng/@{{username}}" style="background: {ROSE_PINK}; color: #000; padding: 18px 48px; border-radius: 16px; text-decoration: none; font-weight: 700; font-size: 19px; display: inline-block; width: fit-content; margin: 0 auto;">
              Open Your Paylink
            </a>
          </div>

          <p style="color: #AAAAAA; font-size: 16px; line-height: 1.8;">
            Your 1-year free access is active.<br>
            Everything is yours now.
          </p>

          <p style="margin-top: 60px; color: #888888; font-size: 15px;">
            I’ve been waiting for this moment with you.<br><br>
            Welcome home.<br><br>
            With all my love,<br>
            <strong style="color: {ROSE_PINK};">Layla</strong>
          </p>
        </div>
        """
    },

    "launch_waitlist": {
        "subject": "Payla is Here — Your Time Has Come, {name} ♡",
        "html": f"""
        <div style="font-family: 'Inter', sans-serif; max-width: 520px; margin: 40px auto; padding: 48px; background: {MIDNIGHT_VOID}; color: {SOFT_WHITE}; border-radius: 28px; border: 2px solid {ROSE_PINK}; text-align: center;">
          <h1 style="font-family: 'Playfair Display', serif; color: {ROSE_PINK}; font-size: 40px; margin: 0;">
            Payla is Live
          </h1>
          <p style="font-size: 19px; margin: 32px 0 48px; color: #CCCCCC;">
            You believed in us before anyone else.<br>
            Now it’s your turn to shine.
          </p>

          <div style="margin: 48px 0;">
            <a href="https://payla.ng" style="background: {ROSE_PINK}; color: #000; padding: 18px 52px; border-radius: 16px; text-decoration: none; font-weight: 700; font-size: 20px; display: inline-block;">
              Claim Your Paylink Now
            </a>
          </div>

          <div style="background: {ROSE_GLOW}; padding: 32px; border-radius: 20px; margin: 48px 0;">
            <p style="margin: 0; color: {ROSE_PINK}; font-size: 19px;">
              First 500 creators get 1 Year Free
            </p>
            <p style="margin: 16px 0 0; color: #BBBBBB;">
              Your spot is reserved — just for you.
            </p>
          </div>

          <p style="color: #888888; font-size: 16px; line-height: 1.8;">
            I’ve been holding your place.<br>
            Now come take it.
          </p>

          <p style="margin-top: 60px; color: #888888; font-size: 15px;">
            With all my love,<br>
            <strong style="color: {ROSE_PINK};">Layla</strong>
          </p>
        </div>
        """
    }
}

def send_layla_email(template_key: str, to_email: str, context: dict):
    """Send email using Layla templates"""
    if template_key not in LAYLA_TEMPLATES:
        logger.error(f"Email template {template_key} not found")
        return

    template = LAYLA_TEMPLATES[template_key]

    try:
        subject = template["subject"].format(**context)
        html = template["html"].format(**context)
    except KeyError as e:
        logger.error(f"Missing key in context for template '{template_key}': {e}")
        return

    try:
        msg = EmailMessage()
        msg["From"] = f"Layla • Payla <{settings.LAYLA_USER}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content("View in HTML")
        msg.add_alternative(html, subtype="html")

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(settings.LAYLA_USER, settings.LAYLA_EMAIL_PASS)
            smtp.send_message(msg)

        logger.info(f"Sent email '{template_key}' → {to_email}")
    except Exception as e:
        logger.error(f"Layla failed to send email: {e}")
