BILLING_TEMPLATES = {
    "trial_expiring_72h": {
        "subject": "Preserve your @{name} identity 🔐",
        "html": """
        <div style="font-family: 'Inter', sans-serif; max-width: 480px; margin: 40px auto; padding: 32px; background: #0A0A0A; color: #FDFDFD; border-radius: 12px; border: 1px solid #E8B4B8;">
          <p style="color:#E8B4B8; font-weight:600; font-size: 16px;">Hi {user_name},</p>
          <p style="font-size:15px; line-height:1.6;">
            Your professional hold on <strong>payla.ng/@{name}</strong> is set to expire in 72 hours.
          </p>
          <p style="font-size:14px; color:#B8B8B8;">
            To ensure your automated payment reminders and custom link remain uninterrupted, please select a plan to continue.
          </p>
          <div style="background: rgba(232, 180, 184, 0.1); padding: 16px; border-radius: 8px; margin: 24px 0; text-align: left;">
            <p style="margin: 0; font-size: 13px; color: #E8B4B8;">• Premium Monthly: ₦7,500</p>
            <p style="margin: 4px 0 0 0; font-size: 13px; color: #E8B4B8;">• Annual Savings: ₦75,000</p>
          </div>
          <div style="text-align:center; margin:32px 0;">
            <a href="{billing_url}" style="background:#E8B4B8; color:#0A0A0A; padding:14px 32px; border-radius:8px; text-decoration:none; font-weight:600; display:inline-block; width: 100%; box-sizing: border-box;">
              Secure My Identity
            </a>
          </div>
          <p style="font-size:12px; color:#888; text-align:center;">Maintain your unique Payla identity and premium features.</p>
        </div>
        """
    },
    "sub_expired_24h": {
        "subject": "Notice: Your Paylink status for @{name} ⏸️",
        "html": """
        <div style="font-family: 'Inter', sans-serif; max-width: 480px; margin: 40px auto; padding: 32px; background: #0A0A0A; color: #FDFDFD; border-radius: 12px; border: 1px solid #ff4444;">
          <p style="color:#ff4444; font-weight:600; font-size: 16px;">Hi {user_name},</p>
          <p style="font-size:15px; line-height:1.6;">
            Your subscription has officially ended. To prevent any disruption to your business, we have applied a <strong>7-day courtesy grace period</strong> to your account.
          </p>
          <p style="font-size:14px; color:#B8B8B8;">
            Your <strong>payla.ng/@{name}</strong> link and automated reminders are still active for now, but will be <strong>paused</strong> if no action is taken.
          </p>
          <div style="text-align:center; margin:32px 0;">
            <a href="{billing_url}" style="background:#FDFDFD; color:#0A0A0A; padding:14px 32px; border-radius:8px; text-decoration:none; font-weight:600; display:inline-block; width: 100%; box-sizing: border-box;">
              Reactivate Subscription
            </a>
          </div>
          <p style="font-size:13px; color:#B8B8B8; text-align:center;">
            Your courtesy access expires in <strong>6 days</strong>.
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