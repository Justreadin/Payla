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


def send_founding_verification_email(email: str, token: str, username: str = None):
    """Send verification email for founding members with 1-year free access"""
    # Extract username from email if not provided
    if not username:
        username = email.split('@')[0]
    
    verify_url = f"{settings.APP_BASE_URL}api/founding/verify-email?token={token}"
    
    subject = "🎉 Verify your email to activate 1-year free access"
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Welcome to Payla</title>
    </head>
    <body style="margin:0; padding:0; background-color:#0A0A0A; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">
        <!-- Main Container -->
        <div style="max-width:600px; margin:0 auto; background-color:#0A0A0A; padding:40px 20px;">
            
            <!-- Card Container -->
            <div style="background: linear-gradient(145deg, #0F0F0F 0%, #0A0A0A 100%); border:1px solid rgba(232,180,184,0.15); border-radius:32px; padding:48px 32px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.8);">
                
                <!-- Logo -->
                <div style="text-align:center; margin-bottom:32px;">
                    <h1 style="font-family: 'Playfair Display', Georgia, serif; color: #E8B4B8; font-size: 36px; font-weight:900; margin:0; letter-spacing:-0.5px;">PAYLA</h1>
                    <div style="width:60px; height:2px; background:linear-gradient(90deg, transparent, #E8B4B8, transparent); margin:16px auto 0;"></div>
                </div>
                
                <!-- Header -->
                <div style="text-align:center; margin-bottom:32px;">
                    <h2 style="font-family: 'Playfair Display', Georgia, serif; color: #FDFDFD; font-size:28px; font-weight:700; margin:0 0 8px; line-height:1.2;">Welcome, Founding Creator</h2>
                    <p style="color: #E8B4B8; font-size:16px; margin:0; font-style:italic;">You're just one step away</p>
                </div>
                
                <!-- Content Card -->
                <div style="background: rgba(232,180,184,0.03); border:1px solid rgba(232,180,184,0.1); border-radius:24px; padding:32px; margin-bottom:32px;">
                    
                    <p style="color: #E5E5E5; font-size:16px; line-height:1.6; margin:0 0 24px;">
                        You've secured your place as a <strong style="color:#E8B4B8;">Founding Creator</strong>. Just one click to activate your 1-year free access to Payla Silver.
                    </p>
                    
                    <!-- Username Highlight -->
                    <div style="background: rgba(232,180,184,0.08); border-radius:16px; padding:20px; margin:24px 0; text-align:center; border:1px dashed rgba(232,180,184,0.2);">
                        <p style="color: #B8B8B8; font-size:14px; margin:0 0 8px; text-transform:uppercase; letter-spacing:1px;">Your Payment Identity</p>
                        <p style="color: #E8B4B8; font-size:28px; font-weight:700; margin:0; font-family:'Courier New', monospace;">payla.ng/@{username}</p>
                    </div>
                    
                    <!-- CTA Button -->
                    <div style="text-align:center; margin:32px 0;">
                        <a href="{verify_url}" style="display:inline-block; background: #E8B4B8; color: #0A0A0A; padding:18px 36px; border-radius:14px; text-decoration:none; font-weight:700; font-size:16px; letter-spacing:0.5px; box-shadow: 0 8px 24px rgba(232,180,184,0.3); transition: all 0.3s ease;">
                            ✨ VERIFY EMAIL & ACTIVATE
                        </a>
                    </div>
                    
                    <!-- Benefits -->
                    <div style="margin:32px 0 0;">
                        <p style="color: #E8B4B8; font-size:14px; font-weight:600; margin:0 0 16px; text-transform:uppercase; letter-spacing:1px;">What you'll unlock:</p>
                        <table style="width:100%; border-collapse:collapse;">
                            <tr>
                                <td style="padding:8px 0; color:#E5E5E5; font-size:14px;">
                                    <span style="color:#2ECC71; margin-right:8px;">✓</span> Your unique payla.ng/@{username}
                                </td>
                            </tr>
                            <tr>
                                <td style="padding:8px 0; color:#E5E5E5; font-size:14px;">
                                    <span style="color:#2ECC71; margin-right:8px;">✓</span> 1-year free access to Payla Silver
                                </td>
                            </tr>
                            <tr>
                                <td style="padding:8px 0; color:#E5E5E5; font-size:14px;">
                                    <span style="color:#2ECC71; margin-right:8px;">✓</span> Unlimited invoices & receipts
                                </td>
                            </tr>
                            <tr>
                                <td style="padding:8px 0; color:#E5E5E5; font-size:14px;">
                                    <span style="color:#2ECC71; margin-right:8px;">✓</span> Automated payment reminders
                                </td>
                            </tr>
                            <tr>
                                <td style="padding:8px 0; color:#E5E5E5; font-size:14px;">
                                    <span style="color:#2ECC71; margin-right:8px;">✓</span> Zero transaction fees forever
                                </td>
                            </tr>
                        </table>
                    </div>
                    
                    <!-- Fallback Link -->
                    <div style="margin-top:32px; padding-top:24px; border-top:1px solid rgba(232,180,184,0.1);">
                        <p style="color:#888888; font-size:13px; margin:0 0 8px;">Button not working? Copy this link:</p>
                        <p style="color:#E8B4B8; font-size:13px; margin:0; word-break:break-all;">
                            <a href="{verify_url}" style="color:#E8B4B8; text-decoration:none;">{verify_url}</a>
                        </p>
                    </div>
                </div>
                
                <!-- Footer -->
                <div style="text-align:center;">
                    <p style="color:#666666; font-size:12px; margin:0 0 16px; line-height:1.6;">
                        This link expires in 24 hours. If you didn't sign up for Payla, please ignore this email.
                    </p>
                    
                    <!-- Signature -->
                    <div style="margin-top:24px;">
                        <p style="color:#888888; font-size:14px; margin:0 0 4px;">See you on the inside,</p>
                        <p style="color:#E8B4B8; font-size:20px; font-family:'Playfair Display', serif; margin:0 0 8px;">— Layla</p>
                        <p style="color:#E8B4B8; font-size:10px; letter-spacing:4px; margin:0; opacity:0.5;">PAYLA</p>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Create EmailData object and pass it to send_email
    email_data = EmailData(
        to=email,
        subject=subject,
        html_content=html_content
    )
    send_email(email_data)