BILLING_TEMPLATES = {
    "trial_expiring_72h": {
        "subject": "Don't lose your @{name} identity 🔐",
        "html": """
        <div style="font-family: 'Inter', sans-serif; max-width: 480px; margin: 40px auto; padding: 32px; background: #0A0A0A; color: #FDFDFD; border-radius: 16px; border: 1px solid #E8B4B8;">
          <p style="color:#E8B4B8; font-weight:600;">Hi {user_name},</p>
          <p style="font-size:15px; line-height:1.6;">
            Your lock on <strong>payla.ng/@{name}</strong> expires in 72 hours.
          </p>
          <p style="font-size:14px; color:#B8B8B8;">
            As a <strong>Founding Creator</strong>, your price is locked at ₦5,000/year. If you lapse, the price jumps to ₦7,500.
          </p>
          <div style="text-align:center; margin:32px 0;">
            <a href="{billing_url}" style="background:#E8B4B8; color:#0A0A0A; padding:14px 32px; border-radius:12px; text-decoration:none; font-weight:600; display:inline-block;">
              Lock My Name for 1 Year
            </a>
          </div>
          <p style="font-size:12px; color:#888; text-align:center;">Don't let someone else claim your identity.</p>
        </div>
        """
    },
    "sub_expired_24h": {
        "subject": "Your Paylink has been paused ⏸️",
        "html": """
        <div style="font-family: 'Inter', sans-serif; max-width: 480px; margin: 40px auto; padding: 32px; background: #0A0A0A; color: #FDFDFD; border-radius: 16px; border: 1px solid #ff4444;">
          <p style="color:#ff4444; font-weight:600;">Hi {user_name},</p>
          <p style="font-size:15px; line-height:1.6;">
            Your subscription has expired, and your automated reminders for <strong>payla.ng/@{name}</strong> have been paused.
          </p>
          <div style="text-align:center; margin:32px 0;">
            <a href="{billing_url}" style="background:#FDFDFD; color:#0A0A0A; padding:14px 32px; border-radius:12px; text-decoration:none; font-weight:600; display:inline-block;">
              Reactivate My Account
            </a>
          </div>
          <p style="font-size:14px; color:#B8B8B8; text-align:center;">
            Payments sent to your link will no longer be processed until you renew.
          </p>
        </div>
        """
    }
}

def generate_billing_content(template_key: str, context: dict) -> str:
    """
    Retrieves the HTML template and injects variables like user_name, billing_url, etc.
    """
    template = BILLING_TEMPLATES.get(template_key)
    if not template:
        return ""
    
    # We use .format(**context) to replace {user_name}, {name}, etc. with real data
    return template["html"].format(**context)