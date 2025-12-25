import logging
logger = logging.getLogger("payla")

# ==========================
# RECEIPT TEMPLATES (The Grand Finale)
# ==========================
RECEIPT_TEMPLATES = {
    "client_receipt": """
Hi {client_name},

Transaction confirmed. Your payment of {amount} to {business_name} has been processed successfully.

Invoice ID: {invoice_id}
Date: {date}

You can view or download your official PDF receipt here:
{receipt_link}

---
Did you like how easy that was? 
Stop sending bank details and start getting paid instantly. 
Claim your name before someone else does: https://payla.ng

Always here to help,
Layla
""",

    "user_payment_alert": """
Hi {user_name},

Great news! {client_name} just settled their invoice of {amount}.

The funds are on their way to your account. 
Layla has already sent the receipt to {client_email} and marked the invoice as 'Paid'.

View Transaction: {invoice_link}

One less follow-up for you to do. 🥂

With excitement,
Layla
"""
}

# ==========================
# HTML VERSIONS (Elite Branding)
# ==========================
# Colors: #0A0A0A (Black), #E8B4B8 (Payla Pink/Gold), #FDFDFD (Off-White)
HTML_RECEIPTS = {
    "client_receipt": """
    <div style="font-family: 'Inter', sans-serif; max-width: 480px; margin: 40px auto; padding: 32px; background: #0A0A0A; color: #FDFDFD; border-radius: 16px; border: 1px solid rgba(232,180,184,0.15);">
      <p style="margin:0; font-size:14px; color:#E8B4B8; text-transform:uppercase; letter-spacing:1px;">Payment Confirmed</p>
      <h2 style="margin:16px 0; font-weight:600; font-size:24px;">{amount}</h2>
      <p style="margin:0; font-size:15px; color:#B8B8B8;">Sent to <strong>{business_name}</strong></p>
      
      <div style="margin:32px 0; padding:20px; background:rgba(255,255,255,0.03); border-radius:12px;">
        <table style="width:100%; font-size:14px; color:#B8B8B8;">
          <tr><td style="padding:4px 0;">Invoice ID</td><td style="text-align:right; color:#FDFDFD;">{invoice_id}</td></tr>
          <tr><td style="padding:4px 0;">Date</td><td style="text-align:right; color:#FDFDFD;">{date}</td></tr>
        </table>
      </div>

      <div style="text-align:center; margin:32px 0;">
        <a href="{receipt_link}" style="background:#FDFDFD; color:#0A0A0A; padding:14px 32px; border-radius:12px; text-decoration:none; font-weight:600; display:inline-block; width:100%; box-sizing:border-box;">
          Download Receipt
        </a>
      </div>

      <hr style="border:0; border-top:1px solid rgba(232,180,184,0.1); margin:32px 0;">
      
      <p style="margin:0; font-size:13px; color:#E8B4B8; text-align:center;">
        Tired of sending bank account numbers?<br>
        <a href="https://payla.ng/@yourname" style="color:#FDFDFD; text-decoration:underline; font-weight:600;">Lock your @name identity today.</a>
      </p>
    </div>
    """,

    "user_payment_alert": """
    <div style="font-family: 'Inter', sans-serif; max-width: 480px; margin: 40px auto; padding: 32px; background: #0A0A0A; color: #FDFDFD; border-radius: 16px; border: 1px solid #E8B4B8;">
      <p style="margin:0; font-size:16px; color:#E8B4B8;">Hi {user_name},</p>
      <h2 style="margin:24px 0; font-size:22px;">You just got paid {amount}!</h2>
      <p style="margin:0; font-size:15px; color:#B8B8B8; line-height:1.6;">
        <strong>{client_name}</strong> settled their invoice via your Paylink. 
        I've already handled the receipt and paperwork for you.
      </p>
      
      <div style="text-align:center; margin:32px 0;">
        <a href="{invoice_link}" style="background:#E8B4B8; color:#0A0A0A; padding:14px 32px; border-radius:12px; text-decoration:none; font-weight:600; display:inline-block;">
          View Transaction
        </a>
      </div>

      <p style="margin:0; font-size:14px; color:#B8B8B8; text-align:center;">🥂 One less follow-up on your plate.</p>
    </div>
    """
}

def generate_receipt_content(template_key: str, context: dict, use_html: bool = True) -> str:
    template = HTML_RECEIPTS.get(template_key) if use_html else RECEIPT_TEMPLATES.get(template_key)
    if not template:
        return "Receipt details not found."
    return template.format(**context)