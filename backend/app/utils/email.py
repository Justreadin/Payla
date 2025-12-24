# utils/email.py — LAYLA: Your Personal Invoicing Concierge
import logging

logger = logging.getLogger("payla")

# ==========================
# PAYLA LUXURY CONSTANTS
# ==========================
MIDNIGHT = "#0A0A0A"
ROSE = "#E8B4B8"
SOFT_WHITE = "#FDFDFD"
SANS = "'Inter', -apple-system, sans-serif"
SERIF = "'Playfair Display', serif"

# ==========================
# LAYLA EMAIL TEMPLATES (2025 Elite Voice)
# ==========================
EMAIL_TEMPLATES = {
    "first_contact": """
Hello,
<br><br>
I’m <strong>Layla</strong>, your new payment concierge at Payla.
<br><br>
I’ll be handling your transactions with <strong>{business_name}</strong> from now on to make things effortless. They’ve just issued an invoice for <strong>{amount}</strong>.
<br><br>
You can view the details and settle everything with a single tap below.
<br><br>
I’m looking forward to working with you.
""",

    "reminder": """
Hi,
<br><br>
<strong>Layla</strong> here. Just keeping you in the loop—your payment for <strong>{business_name}</strong> ({amount}) is coming up on {due_date}.
<br><br>
I’ve prepared everything for you. Tap here to handle it early and keep your day moving.
""",

    "reminder_2": """
Good morning,
<br><br>
<strong>Layla</strong> here.
<br><br>
Your <strong>{amount}</strong> payment to <strong>{business_name}</strong> is due tomorrow.
<br><br>
Your quick-access link is ready. Settle it in one tap below.
""",

    "due_today": """
Happy {day_of_week}!
<br><br>
<strong>Layla</strong> here. Today is the day for your <strong>{amount}</strong> payment to <strong>{business_name}</strong>.
<br><br>
One tap and I’ll make sure they get it instantly so you can focus on what you do best.
<br><br>
I've got you.
""",

    "overdue_gentle": """
Hello,
<br><br>
It’s <strong>Layla</strong>. I noticed your payment for <strong>{business_name}</strong> is just a day past due.
<br><br>
I’m keeping your link active and secure so we can get this cleared today without any stress.
<br><br>
Always here to help.
""",

    "overdue_firm": """
Hello,
<br><br>
<strong>Layla</strong> here. I’m doing my review and noticed your <strong>{amount}</strong> payment for <strong>{business_name}</strong> is still open.
<br><br>
I’d love to get this settled for you today so your account stays in perfect standing. Ready when you are.
""",

    "payment_received": """
<strong>Transaction Confirmed!</strong>
<br><br>
Your payment of <strong>{amount}</strong> to <strong>{business_name}</strong> has been processed perfectly.
<br><br>
I’ve updated your records and everything is in order. Thank you for being so prompt.
<br><br>
Talk soon!
"""
}

# Mapping for Titles and Buttons to keep the Logic clean
METADATA = {
    "first_contact": {"title": "A new standard", "button": "View Invoice"},
    "reminder": {"title": "A gentle reminder", "button": "Settle Early"},
    "reminder_2": {"title": "Due tomorrow", "button": "One-Tap Payment"},
    "due_today": {"title": "Today is the day", "button": "Pay Now"},
    "overdue_gentle": {"title": "Past due", "button": "Clear Payment"},
    "overdue_firm": {"title": "Account Review", "button": "Settle Now"},
    "payment_received": {"title": "Confirmed", "button": "View Receipt"}
}

# Default Sender fallback
SENDER_MAPPING = {
    "noreply": "Layla • Payla <concierge@payla.ng>"
}

# ==========================
# THE "ELITE CONCIERGE" HTML (Visual Perfection)
# ==========================

def get_html_wrapper(title, body_text, button_text, link, business_name):
    return f"""
    <div style="background:{MIDNIGHT}; color:{SOFT_WHITE}; font-family:{SANS}; padding:60px 20px; min-height:100vh;">
      <div style="max-width:460px; margin:0 auto; background:{MIDNIGHT}; border:1px solid rgba(232,180,184,0.25); border-radius:32px; padding:48px; box-shadow:0 40px 100px rgba(0,0,0,0.5);">
        
        <div style="margin-bottom:32px;">
            <span style="color:{ROSE}; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:3px;">
                {business_name} • Concierge
            </span>
        </div>

        <h1 style="font-family:{SERIF}; font-size:32px; font-weight:400; color:{ROSE}; margin-bottom:32px; letter-spacing:-0.5px; line-height:1.2;">
            {title}
        </h1>

        <div style="font-size:16px; line-height:1.8; color:#D6D6D6; font-weight:300; margin-bottom:40px;">
            {body_text}
        </div>

        <div style="text-align:left; margin-bottom:48px;">
            <a href="{link}" style="background:{ROSE}; color:{MIDNIGHT}; padding:18px 42px; border-radius:14px; text-decoration:none; font-weight:700; font-size:16px; display:inline-block;">
                {button_text}
            </a>
        </div>

        <div style="margin-top:60px; padding-top:32px; border-top:1px solid rgba(232,180,184,0.15);">
            <p style="margin:0; color:#888888; font-size:15px;">Talk soon.</p>
            <p style="margin:8px 0 0; color:{ROSE}; font-size:22px; font-family:{SERIF};">— Layla</p>
            <p style="margin:4px 0 0; font-weight:900; letter-spacing:4px; font-size:12px; color:rgba(232,180,184,0.4);">PAYLA</p>
        </div>

        <p style="margin-top:32px; font-size:11px; color:#444; line-height:1.6;">
            Powered by <strong>Payla</strong>. The new standard for creative transactions.
        </p>
      </div>
    </div>
    """

# ==========================
# FUNCTIONS
# ==========================
def generate_email_content(email_type: str, context: dict, use_html: bool = False) -> str:
    template_str = EMAIL_TEMPLATES.get(email_type)
    
    if not template_str:
        logger.error(f"Template type '{email_type}' not found.")
        return ""

    try:
        formatted_body = template_str.format(**context)
        
        if use_html:
            meta = METADATA.get(email_type, {"title": "Notification", "button": "View Details"})
            return get_html_wrapper(
                title=meta["title"],
                body_text=formatted_body,
                button_text=meta["button"],
                link=context.get("link", "https://payla.ng"),
                business_name=context.get("business_name", "Payla Creator")
            )
        return formatted_body
        
    except KeyError as e:
        logger.error(f"Missing context key {e} for email type '{email_type}'")
        return "An error occurred while generating content."

def get_sender(email_type: str) -> str:
    return SENDER_MAPPING.get(email_type, SENDER_MAPPING["noreply"])