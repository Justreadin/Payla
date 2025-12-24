import logging
logger = logging.getLogger("payla")

MARKETING_TEMPLATES = {
    "client_conversion": {
        "subject": "A quick question about your payment to {business_name}",
        "html": """
        <div style="font-family: 'Inter', sans-serif; max-width: 480px; margin: 40px auto; padding: 32px; background: #0A0A0A; color: #FDFDFD; border-radius: 16px; border: 1px solid rgba(232,180,184,0.15);">
          <p style="color:#E8B4B8; font-size:16px; margin:0;">Hello {display_name},</p>
          
          <p style="line-height:1.6; font-size:15px; margin:24px 0;">
            It’s <strong>Layla</strong> from Payla. You recently paid <strong>{business_name}</strong> using their unique Payla link.
          </p>
          
          <p style="line-height:1.6; font-size:15px; color:#B8B8B8;">
            I noticed how fast that went—just about 12 seconds. Are you still sending out 10-digit account numbers and manually checking for screenshots?
          </p>
          
          <p style="line-height:1.6; font-size:15px; color:#FDFDFD;">
            You can look just as professional. There are only <strong>{spots_left} Founding Creator spots</strong> remaining for our lifetime price-lock (₦5,000/year).
          </p>
          
          <div style="text-align:center; margin:32px 0;">
            <a href="https://payla.ng/entry" style="background:#E8B4B8; color:#0A0A0A; padding:14px 32px; border-radius:12px; text-decoration:none; font-weight:600; display:inline-block; width:100%; box-sizing:border-box;">
              Claim My @Identity
            </a>
          </div>
          
          <p style="font-size:12px; color:#888; text-align:center; margin:0;">Stop the manual follow-ups. Start getting paid like a pro.</p>
          
          <p style="margin-top:32px; font-size:14px; color:#E8B4B8;">With care,<br><strong>Layla</strong></p>
          
          <hr style="border: 0; border-top: 1px solid rgba(255,255,255,0.05); margin: 24px 0;">
          
          <div style="text-align:center;">
             <a href="{unsubscribe_link}" style="color:#444; font-size:11px; text-decoration:none;">Unsubscribe from marketing updates</a>
          </div>
        </div>
        """
    }
}

def generate_marketing_content(template_key: str, context: dict) -> str:
    template = MARKETING_TEMPLATES.get(template_key)
    if not template:
        return ""
    
    # Fallback for display_name if not provided in context
    if "display_name" not in context or not context["display_name"]:
        context["display_name"] = "there" # Results in "Hello there,"
        
    try:
        return template["html"].format(**context)
    except KeyError as e:
        logger.error(f"Missing context key for marketing template {template_key}: {e}")
        return ""