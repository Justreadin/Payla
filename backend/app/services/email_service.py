"""
Transactional Payla emails: verification, password reset, presell reward,
founding verification.

All functions call render_email(). None build HTML directly.
"""

import requests
from pydantic import BaseModel
from app.core.config import settings
from app.utils.email_render import render_email
from app.utils.email_render.components import (
    heading,
    eyebrow,
    paragraph,
    callout,
    mono,
    divider,
    button,
    sign_off,
)
import logging

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"


class EmailData(BaseModel):
    to: str
    subject: str
    html_content: str
    from_email: str = "Payla <favour@payla.vip>"


def send_email(data: EmailData):
    """Base dispatcher. Kept for backward compatibility."""
    try:
        headers = {
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "from": data.from_email,
            "to": [data.to],
            "subject": data.subject,
            "html": data.html_content,
        }
        resp = requests.post(RESEND_URL, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Email failed: {e}")
        raise


# ========================================
# 1. VERIFICATION EMAIL
# ========================================

def send_verification_email(email: str, token: str):
    verify_link = f"{settings.APP_BASE_URL}api/auth/verify-email?token={token}"

    html_content = render_email(
        title="Verify your identity",
        blocks=[
            heading("Claim your identity."),
            paragraph("You&rsquo;ve taken the first step toward a new standard."),
            paragraph(
                "Before we begin, I need to ensure this inbox belongs to you."
            ),
            button("Verify email address", verify_link),
            divider(),
            paragraph(
                "If the button doesn&rsquo;t work, use the link below:",
                color="#7A7A7A",
                size="14px",
            ),
            paragraph(
                f'<a href="{verify_link}" style="color:#E8B4B8; text-decoration:none; '
                f'word-break:break-all;">{verify_link}</a>',
                color="#E8B4B8",
                size="14px",
            ),
            sign_off("I&rsquo;ll be in touch."),
        ],
    )

    send_email(EmailData(
        to=email,
        subject="Verify your identity",
        html_content=html_content,
    ))


# ========================================
# 2. PASSWORD RESET
# ========================================

def send_reset_password_email(email: str, code: str):
    html_content = render_email(
        title="Your verification code",
        blocks=[
            heading("Access requested."),
            paragraph("A password reset was requested for your account."),
            paragraph("Your unique verification code is below."),
            callout(
                f'<p style="font-family:\'SF Mono\', Menlo, Consolas, monospace; '
                f'font-size:38px; font-weight:700; color:#E8B4B8; '
                f'letter-spacing:8px; text-align:center; margin:0;">{code}</p>'
            ),
            paragraph(
                "This code expires in 10 minutes. If you didn&rsquo;t "
                "request this, you may safely ignore it.",
                color="#7A7A7A",
                size="14px",
            ),
            sign_off("I&rsquo;ll be in touch."),
        ],
    )

    send_email(EmailData(
        to=email,
        subject="Your verification code",
        html_content=html_content,
    ))


# ========================================
# 3. PRESELL REWARD (FOUNDING CREATOR)
# ========================================

def send_presell_reward_email(email: str, full_name: str, username: str):
    first_name = full_name.split()[0] if full_name else "there"
    html_content = render_email(
        title="Your Crown has arrived",
        blocks=[
            eyebrow("Founding Creator"),
            heading("The Crown is yours."),
            paragraph(f"Welcome, {first_name}."),
            paragraph(
                "You didn&rsquo;t just join early. You helped define the "
                "standard. Your payment identity is now eternally reserved."
            ),
            callout(
                f'<p style="margin:0;">{mono(f"payla.ng/@{username}", size="22px")}</p>'
            ),
            eyebrow("Your eternal rewards"),
            paragraph(
                "One year of Payla Silver, complimentary.<br>"
                "Founding Creator badge.<br>"
                "Lifetime price protection.<br>"
                "Direct line to support.",
                color="#FDFDFD",
            ),
            paragraph(
                "This is only the beginning. I&rsquo;ll be in touch as we "
                "roll out your exclusive features."
            ),
            sign_off("Talk soon."),
        ],
    )

    send_email(EmailData(
        to=email,
        subject="Your Crown has arrived",
        html_content=html_content,
    ))


# ========================================
# 4. FOUNDING VERIFICATION
# ========================================

def send_founding_verification_email(email: str, token: str, username: str = None):
    """
    Verification for founding members with 1-year free Silver access.
    Rebuilt to match the design system. Previously a completely different
    visual language; now consistent with every other email.
    """
    if not username:
        username = email.split("@")[0]

    verify_url = f"{settings.APP_BASE_URL}api/founding/verify-email?token={token}"

    html_content = render_email(
        title="Verify your email to activate your Founding Creator access",
        blocks=[
            eyebrow("Founding Creator"),
            heading("One step away."),
            paragraph(
                "You&rsquo;ve secured your place as a "
                "<strong style=\"color:#FDFDFD;\">Founding Creator</strong>. "
                "One click to activate your one year of complimentary "
                "Payla Silver."
            ),
            callout(
                f'<p style="font-family:\'Inter\',sans-serif; font-size:13px; '
                f'font-weight:600; letter-spacing:0.14em; text-transform:uppercase; '
                f'color:#B8B8B8; margin:0 0 12px 0;">Your payment identity</p>'
                f'<p style="margin:0;">{mono(f"payla.ng/@{username}", size="24px")}</p>'
            ),
            button("Verify email and activate", verify_url),
            divider(),
            eyebrow("What you&rsquo;ll unlock"),
            paragraph(
                "Your unique Payla link.<br>"
                "One year of Payla Silver, complimentary.<br>"
                "Branded invoices and receipts.<br>"
                "Automated reminders from Layla.<br>"
                "Zero transaction fees from Payla.",
                color="#FDFDFD",
            ),
            paragraph(
                "This link expires in 24 hours. If you didn&rsquo;t sign up "
                "for Payla, please ignore this email.",
                color="#7A7A7A",
                size="13px",
            ),
            paragraph(
                "Button not working? Copy this link:",
                color="#7A7A7A",
                size="13px",
            ),
            paragraph(
                f'<a href="{verify_url}" style="color:#E8B4B8; '
                f'text-decoration:none; word-break:break-all;">{verify_url}</a>',
                color="#E8B4B8",
                size="13px",
            ),
            sign_off("See you on the inside."),
        ],
    )

    send_email(EmailData(
        to=email,
        subject="Verify your email to activate your Founding Creator access",
        html_content=html_content,
    ))