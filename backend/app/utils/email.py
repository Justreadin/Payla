# utils/email.py — LAYLA: Your Personal Invoicing Concierge
import logging
logger = logging.getLogger("payla")

# ==========================
# LAYLA EMAIL TEMPLATES (2025 Elite Voice)
# ==========================
EMAIL_TEMPLATES = {
    "reminder": """
Hi {name},

Just a gentle nudge from me, Layla — your invoice of {amount} is due on {due_date}.

Here’s your secure payment link:
{link}

Tap and settle in seconds. I’ve got you.

With care,  
Layla  
Your assistant at Payla
""",

    "reminder_2": """
Hi {name},

Layla here. Your invoice is due tomorrow.

Quick payment link:
{link}

You’re almost done — let’s wrap this up beautifully.

Always,  
Layla
""",

    "overdue_gentle": """
Hi {name},

It’s Layla. I noticed your invoice of {amount} is now a day past due.

Here’s the link again — no stress:
{link}

I know life gets busy. I’m here when you’re ready.

Warmly,  
Layla
""",

    "overdue_firm": """
Hi {name},

Layla here. Your invoice of {amount} is now {days_overdue} days past due.

Please settle at your earliest convenience:
{link}

I’d love to mark this as complete for you.

Thank you,  
Layla
""",

    "payment_received": """
Hi {name},

It’s Layla — your payment of {amount} just landed safely.

Invoice {invoice_id} is now fully settled. You’re all good.

Thank you for trusting Payla.

With gratitude,  
Layla  
Your assistant
""",

    "welcome_layla": """
Hi {name},

I’m Layla — your new personal assistant at Payla.

From now on, I’ll handle your reminders, confirm payments, and make sure everything runs smoothly behind the scenes.

You focus on your craft. I’ve got the rest.

Excited to work with you,  
Layla
""",

    "noreply": """
Hello {name},

{notification_details}

For support: support@payla.vip

Best,  
The Payla Team
"""
}

# ==========================
# SENDER MAPPING — LAYLA IS REAL
# ==========================
SENDER_MAPPING = {
    "reminder": "Reminder • Payla <reminders@payla.vip>",
    "reminder_2": "Reminder • Payla <reminders@payla.vip>",
    "overdue_gentle": "Reminder • Payla <reminders@payla.vip>",
    "overdue_firm": "Reminder • Payla <reminders@payla.vip>",
    "payment_received": "Reminder • Payla <reminders@payla.vip>",
    "welcome_layla": "Layla • Payla <layla@payla.vip>",
    "noreply": "Payla <noreply@payla.vip>"
}

# ==========================
# HTML VERSIONS (Use with Resend)
# ==========================
HTML_TEMPLATES = {
    "reminder": """
    <div style="font-family: 'Inter', sans-serif; max-width: 480px; margin: 40px auto; padding: 32px; background: #0A0A0A; color: #FDFDFD; border-radius: 16px; border: 1px solid rgba(232,180,184,0.15);">
      <p style="margin:0; font-size:16px; color:#E8B4B8;">Hi {name},</p>
      <p style="margin:24px 0; font-size:15px; line-height:1.6;">
        Just a gentle nudge from me, <strong>Layla</strong> — your invoice of <strong>{amount}</strong> is due on <strong>{due_date}</strong>.
      </p>
      <div style="text-align:center; margin:32px 0;">
        <a href="{link}" style="background:#E8B4B8; color:#0A0A0A; padding:14px 32px; border-radius:12px; text-decoration:none; font-weight:600; display:inline-block;">
          Pay Now
        </a>
      </div>
      <p style="margin:24px 0 0; font-size:14px; color:#B8B8B8;">
        Tap and settle in seconds. I’ve got you.
      </p>
      <p style="margin:32px 0 8px; font-size:14px; color:#E8B4B8;">
        With care,<br><strong>Layla</strong><br>
        <span style="color:#888; font-size:12px;">Your assistant at Payla</span>
      </p>
    </div>
    """
}

# ==========================
# FUNCTIONS
# ==========================
def generate_email_content(email_type: str, context: dict, use_html: bool = False) -> str:
    if use_html and email_type in HTML_TEMPLATES:
        template = HTML_TEMPLATES[email_type]
    else:
        template = EMAIL_TEMPLATES.get(email_type, EMAIL_TEMPLATES["noreply"])
    
    try:
        return template.format(**context)
    except KeyError as e:
        logger.error(f"Missing context key {e} for email type '{email_type}'")
        return EMAIL_TEMPLATES["noreply"].format(name=context.get("name", "there"), notification_details="An error occurred.")

def get_sender(email_type: str) -> str:
    return SENDER_MAPPING.get(email_type, SENDER_MAPPING["noreply"])