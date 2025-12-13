# services/email_service.py → LAYLA'S FINAL LUXURY EMAILS (2026)
import requests
from pydantic import BaseModel
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)
RESEND_URL = "https://api.resend.com/emails"

# ==========================
# PAYLA LUXURY COLORS
# ==========================
MIDNIGHT = "#0A0A0A"
ROSE = "#E8B4B8"
ROSE_GLOW = "rgba(232,180,184,0.12)"
GOLD = "#D4AF37"
SOFT_WHITE = "#FDFDFD"

class EmailData(BaseModel):
    to: str
    subject: str
    html_content: str
    from_email: str = "Layla • Payla <layla@payla.vip>"

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
        logger.info(f"Layla email sent → {data.to}")
    except Exception as e:
        logger.error(f"Layla email failed: {e}")
        raise


# ========================================
# 1. VERIFICATION EMAIL — PURE AUDACITY
# ========================================
def send_verification_email(email: str, token: str):
    verify_link = f"{settings.APP_BASE_URL}api/auth/verify-email?token={token}"
    
    html_content = f"""
    <div style="background:{MIDNIGHT}; color:{SOFT_WHITE}; font-family:'Inter',sans-serif; padding:40px 20px; min-height:100vh;">
      <div style="max-width:520px; margin:40px auto; background:{MIDNIGHT}; border:2px solid {ROSE}; border-radius:28px; overflow:hidden; box-shadow:0 30px 80px rgba(232,180,184,0.15);">
        
        <!-- Header Glow -->
        <div style="background:linear-gradient(135deg, {ROSE}10, transparent); padding:48px 40px 32px; text-align:center;">
          <h1 style="font-family:'Playfair Display',serif; font-size:48px; font-weight:900; margin:0; background:linear-gradient(90deg, {ROSE}, {GOLD}); -webkit-background-clip:text; -webkit-text-fill-color:transparent;">
            Welcome to Payla
          </h1>
          <p style="font-size:18px; color:#CCCCCC; margin:20px 0 0; line-height:1.6;">
            You’ve been invited to something extraordinary.
          </p>
        </div>

        <!-- Main Content -->
        <div style="padding:40px; text-align:center;">
          <p style="font-size:17px; line-height:1.8; color:#DDDDDD; margin:0 0 32px;">
            One final step to claim your place.
          </p>

          <div style="text-align:center; margin:48px 0;">
            <a href="{verify_link}" style="background:{ROSE}; color:#000; padding:18px 52px; border-radius:16px; text-decoration:none; font-weight:800; font-size:19px; display:inline-block; box-shadow:0 10px 30px rgba(232,180,184,0.3);">
              Verify Your Email
            </a>
          </div>

          <p style="color:#888888; font-size:15px; line-height:1.7; margin:40px 0 0;">
            Or paste this link:<br>
            <code style="background:#1a1a1a; padding:12px 16px; border-radius:8px; font-size:14px; word-break:break-all; display:inline-block; margin-top:12px;">
              {verify_link}
            </code>
          </p>
        </div>

        <!-- Signature -->
        <div style="background:{ROSE_GLOW}; padding:40px; text-align:center; border-top:1px solid rgba(232,180,184,0.2);">
          <p style="margin:0; color:#E8B4B8; font-size:16px;">
            With quiet anticipation,<br>
            <strong>Layla</strong>
          </p>
          <p style="margin:12px 0 0; color:#666666; font-size:13px;">
            Your personal assistant at Payla
          </p>
        </div>
      </div>
    </div>
    """
    send_email(EmailData(to=email, subject="Welcome to Payla — Verify Your Email", html_content=html_content))


# ========================================
# 2. PASSWORD RESET — ELEGANT & URGENT
# ========================================
def send_reset_password_email(email: str, code: str):
    html_content = f"""
    <div style="background:{MIDNIGHT}; color:{SOFT_WHITE}; font-family:'Inter',sans-serif; padding:40px 20px; min-height:100vh;">
      <div style="max-width:520px; margin:40px auto; background:{MIDNIGHT}; border:2px solid {ROSE}; border-radius:28px; overflow:hidden; box-shadow:0 30px 80px rgba(232,180,184,0.15);">
        
        <div style="padding:48px 40px; text-align:center;">
          <h1 style="font-family:'Playfair Display',serif; color:{ROSE}; font-size:42px; margin:0 0 24px; letter-spacing:-1px;">
            Reset Your Password
          </h1>
          <p style="color:#CCCCCC; font-size:18px; margin:0 0 40px; line-height:1.7;">
            Your security is sacred to us.
          </p>

          <div style="background:{ROSE_GLOW}; padding:40px; border-radius:20px; margin:40px 0;">
            <p style="margin:0 0 16px; color:#E8B4B8; font-size:17px; font-weight:600;">
              Your verification code:
            </p>
            <h2 style="font-size:48px; letter-spacing:12px; margin:0; color:{ROSE}; font-weight:900;">
              {code}
            </h2>
            <p style="margin:24px 0 0; color:#999999; font-size:15px;">
              Valid for 10 minutes
            </p>
          </div>

          <p style="color:#888888; font-size:15px; line-height:1.7;">
            If you didn’t request this, ignore this email.<br>
            Your account remains secure.
          </p>
        </div>

        <div style="background:{ROSE_GLOW}; padding:40px; text-align:center; border-top:1px solid rgba(232,180,184,0.2);">
          <p style="margin:0; color:#E8B4B8; font-size:16px;">
            Always here for you,<br>
            <strong>Layla</strong>
          </p>
        </div>
      </div>
    </div>
    """
    send_email(EmailData(to=email, subject="Your Payla Password Reset Code", html_content=html_content))


# ========================================
# 3. PRESELL REWARD EMAIL — FOUNDING CREATOR CROWN
# ========================================
def send_presell_reward_email(email: str, full_name: str, username: str):
    html_content = f"""
    <div style="background:{MIDNIGHT}; color:{SOFT_WHITE}; font-family:'Inter',sans-serif; padding:40px 20px; min-height:100vh;">
      <div style="max-width:560px; margin:40px auto; background:{MIDNIGHT}; border:3px solid {ROSE}; border-radius:32px; overflow:hidden; box-shadow:0 40px 100px rgba(232,180,184,0.2);">
        
        <!-- Crown Header -->
        <div style="background:linear-gradient(135deg, {ROSE}20, transparent); padding:60px 40px 40px; text-align:center; position:relative;">
          <div style="font-size:64px; margin-bottom:16px;">Crown</div>
          <h1 style="font-family:'Playfair Display',serif; color:{ROSE}; font-size:52px; margin:0; letter-spacing:-2px;">
            Founding Creator
          </h1>
        </div>

        <!-- Main -->
        <div style="padding:0 48px 48px; text-align:center;">
          <h2 style="color:{ROSE}; font-size:32px; margin:32px 0 16px;">
            {full_name}
          </h2>
          <p style="font-size:20px; color:#E8E8E8; margin:0 0 40px;">
            Your Paylink is now eternally yours:
          </p>
          
          <div style="background:{ROSE_GLOW}; padding:32px; border-radius:24px; margin:40px 0;">
            <h3 style="color:{ROSE}; font-size:36px; margin:0; font-weight:800;">
              payla.ng/@{username}
            </h3>
            <p style="color:#BBBBBB; margin:16px 0 0; font-size:16px;">
              Reserved forever. No one can take it.
            </p>
          </div>

          <div style="margin:48px 0;">
            <p style="color:{ROSE}; font-size:22px; font-weight:700; margin:0 0 24px;">
              Your Eternal Rewards
            </p>
            <ul style="text-align:left; color:#E0E0E0; font-size:17px; line-height:2.2; padding-left:32px; margin:0;">
              <li>1 Year Payla Silver — Free Forever</li>
              <li>Founding Creator Crown Badge</li>
              <li>First Access to Every New Feature</li>
              <li>Direct Line to Layla (Me)</li>
              <li>Your Name in Payla History</li>
            </ul>
          </div>

          <p style="font-size:19px; color:#CCCCCC; line-height:1.8; margin:48px 0;">
            You didn’t just join early.<br>
            You helped build this.
          </p>

          <p style="color:#888888; font-size:16px; margin-top:60px;">
            I’ll be with you every step of the way.<br><br>
            With deepest gratitude,<br>
            <strong style="color:{ROSE}; font-size:20px;">Layla</strong>
          </p>
        </div>
      </div>
    </div>
    """
    send_email(EmailData(to=email, subject=f"@{username} is Yours Forever — Founding Creator Crown", html_content=html_content))