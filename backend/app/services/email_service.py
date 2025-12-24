# services/email_service.py
import requests
from pydantic import BaseModel
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)
RESEND_URL = "https://api.resend.com/emails"

# ==========================
# PAYLA LUXURY CONSTANTS
# ==========================
MIDNIGHT = "#0A0A0A"
ROSE = "#E8B4B8"
SOFT_WHITE = "#FDFDFD"
SANS = "'Inter', -apple-system, sans-serif"
SERIF = "'Playfair Display', serif"

class EmailData(BaseModel):
    to: str
    subject: str
    html_content: str
    from_email: str = "Email • Payla <favour@payla.vip>"

def send_email(data: EmailData):
    try:
        headers = {
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "from": data.from_email,
            "to": [data.to],
            "subject": data.subject,
            "html": data.html_content
        }
        resp = requests.post(RESEND_URL, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Email failed: {e}")
        raise

def get_footer():
    """Consistent Layla Signature"""
    return f"""
    <div style="margin-top:60px; padding-top:32px; border-top:1px solid rgba(232,180,184,0.15);">
        <p style="margin:0; color:#888888; font-size:15px;">I’ll be waiting.</p>
        <p style="margin:8px 0 0; color:{ROSE}; font-size:22px; font-family:{SERIF};">— Layla</p>
        <p style="margin:4px 0 0; font-weight:900; letter-spacing:4px; font-size:12px; color:rgba(232,180,184,0.4);">PAYLA</p>
    </div>
    """

# ========================================
# 1. VERIFICATION EMAIL
# ========================================
def send_verification_email(email: str, token: str):
    verify_link = f"{settings.APP_BASE_URL}api/auth/verify-email?token={token}"
    
    html_content = f"""
    <div style="background:{MIDNIGHT}; color:{SOFT_WHITE}; font-family:{SANS}; padding:60px 20px; min-height:100vh;">
      <div style="max-width:460px; margin:0 auto; background:{MIDNIGHT}; border:1px solid rgba(232,180,184,0.25); border-radius:32px; padding:48px;">
        
        <h1 style="font-family:{SERIF}; font-size:32px; font-weight:400; color:{ROSE}; margin-bottom:32px; letter-spacing:-0.5px;">
          Claim your identity.
        </h1>

        <div style="font-size:16px; line-height:1.9; color:#D6D6D6; font-weight:300;">
          <p>You’ve taken the first step toward a new standard.</p>
          <p>Before we begin, I need to ensure this inbox belongs to you.</p>
          
          <div style="margin:48px 0; text-align:center;">
            <a href="{verify_link}" style="background:{ROSE}; color:{MIDNIGHT}; padding:16px 40px; border-radius:12px; text-decoration:none; font-weight:600; font-size:16px; display:inline-block;">
              Verify Email Address
            </a>
          </div>

          <p style="font-size:14px; color:#888888;">
            If the button doesn't work, use the link below:<br/>
            <a href="{verify_link}" style="color:{ROSE}; text-decoration:none;">{verify_link}</a>
          </p>
        </div>

        {get_footer()}
      </div>
    </div>
    """
    send_email(EmailData(to=email, subject="Verify your identity", html_content=html_content))

# ========================================
# 2. PASSWORD RESET
# ========================================
def send_reset_password_email(email: str, code: str):
    html_content = f"""
    <div style="background:{MIDNIGHT}; color:{SOFT_WHITE}; font-family:{SANS}; padding:60px 20px; min-height:100vh;">
      <div style="max-width:460px; margin:0 auto; background:{MIDNIGHT}; border:1px solid rgba(232,180,184,0.25); border-radius:32px; padding:48px;">
        
        <h1 style="font-family:{SERIF}; font-size:32px; font-weight:400; color:{ROSE}; margin-bottom:32px;">
          Access requested.
        </h1>

        <div style="font-size:16px; line-height:1.9; color:#D6D6D6; font-weight:300;">
          <p>A password reset was requested for your account.</p>
          <p>Your unique verification code is below.</p>
          
          <div style="margin:40px 0; background:rgba(232,180,184,0.05); border:1px solid rgba(232,180,184,0.1); border-radius:16px; padding:32px; text-align:center;">
            <span style="font-size:42px; font-weight:700; color:{ROSE}; letter-spacing:8px;">{code}</span>
          </div>

          <p style="font-size:14px; color:#888888;">
            This code expires in 10 minutes. If you didn't request this, you may safely ignore it.
          </p>
        </div>

        {get_footer()}
      </div>
    </div>
    """
    send_email(EmailData(to=email, subject="Your verification code", html_content=html_content))

# ========================================
# 3. PRESELL REWARD (FOUNDING CREATOR)
# ========================================
def send_presell_reward_email(email: str, full_name: str, username: str):
    html_content = f"""
    <div style="background:{MIDNIGHT}; color:{SOFT_WHITE}; font-family:{SANS}; padding:60px 20px; min-height:100vh;">
      <div style="max-width:460px; margin:0 auto; background:{MIDNIGHT}; border:1px solid {ROSE}; border-radius:32px; padding:48px;">
        
        <h1 style="font-family:{SERIF}; font-size:32px; font-weight:400; color:{ROSE}; margin-bottom:12px;">
          The Crown is yours.
        </h1>
        <p style="color:#888888; font-size:14px; text-transform:uppercase; letter-spacing:2px; margin-bottom:32px;">Founding Creator</p>

        <div style="font-size:16px; line-height:1.9; color:#D6D6D6; font-weight:300;">
          <p>Welcome, {full_name.split()[0]}.</p>
          <p>You didn’t just join early. You helped define the standard. Your payment identity is now eternally reserved.</p>
          
          <div style="margin:40px 0; border-left:2px solid {ROSE}; padding-left:24px;">
            <p style="color:{SOFT_WHITE}; font-size:24px; font-weight:700; margin:0;">payla.ng/@{username}</p>
          </div>

          <p style="color:{ROSE}; font-weight:600; margin-top:32px;">Your Eternal Rewards:</p>
          <ul style="list-style-type:none; padding:0; color:{SOFT_WHITE};">
            <li style="margin-bottom:8px;">• 1 Year Payla Silver — Complimentary</li>
            <li style="margin-bottom:8px;">• Founding Creator Badge</li>
            <li style="margin-bottom:8px;">• Lifetime Price Protection</li>
            <li style="margin-bottom:8px;">• Direct Line to Support</li>
          </ul>

          <p style="margin-top:32px;">
            This is only the beginning. I'll be in touch as we roll out your exclusive features.
          </p>
        </div>

        {get_footer()}
      </div>
    </div>
    """
    send_email(EmailData(to=email, subject="Your Crown has arrived", html_content=html_content))