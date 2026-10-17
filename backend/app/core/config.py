# core/config.py
import os
from typing import Optional

from pydantic import AnyUrl, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ────────────────────────────────
    # 1. APP & ENVIRONMENT
    # ────────────────────────────────
    PROJECT_NAME: str = "Payla"
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    DEBUG: bool = Field(default=True, env="DEBUG")

    BACKEND_URL: str = Field(
        default="https://payla.ng",
        env="BACKEND_URL",
        description="Canonical backend/frontend base URL used in webhooks, "
        "invoice links, and subscription callbacks.",
    )

    VIP_BASE_URL: str = Field(
        default="https://payla.vip",
        env="VIP_BASE_URL",
        description=(
            "Premium paylink domain. Silver merchants can publish a "
            "payla.vip/@username link in addition to their payla.ng "
            "link. Both domains resolve to the same page."
        ),
    )
    # ────────────────────────────────
    # 2. FRONTEND
    # ────────────────────────────────
    FRONTEND_URL: AnyUrl = Field(
        default="https://payla.ng",
        env="FRONTEND_URL",
        description="Base URL for the client app (e.g. https://payla.ng).",
    )

    SUBSCRIPTION_CALLBACK_URL: AnyUrl = Field(
        default="https://payla.ng/subscription",
        env="SUBSCRIPTION_CALLBACK_URL",
        description=(
            "URL Paystack redirects to after subscription checkout. "
            "Defaults to the production frontend. Override in "
            "development to point at ngrok."
        ),
    )

    # ────────────────────────────────
    # 3. FIREBASE / FIRESTORE
    # ────────────────────────────────
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = Field(
        default=None,
        env="GOOGLE_APPLICATION_CREDENTIALS",
        description="Path to Firebase service account JSON",
    )
    # Base64-encoded Firebase service account JSON
    PAYLA_FIREBASE_KEY: Optional[str] = Field(
        default=None,
        env="PAYLA_FIREBASE_KEY",
        description="Base64-encoded Firebase service account JSON",
    )

    # ────────────────────────────────
    # 4. PAYSTACK
    # ────────────────────────────────
    PAYSTACK_SECRET_KEY: str = Field(..., env="PAYSTACK_SECRET_KEY")
    PAYSTACK_PUBLIC_KEY: str = Field(..., env="PAYSTACK_PUBLIC_KEY")
    PAYSTACK_SECRET_PAYLA: str = Field(..., env="PAYSTACK_SECRET_PAYLA")
    PAYSTACK_PUBLIC_PAYLA: str = Field(..., env="PAYSTACK_PUBLIC_PAYLA")

    PAYSTACK_CLIENT_INVOICE_FEES_ENABLED: bool = Field(
        default=True,
        env="PAYSTACK_CLIENT_INVOICE_FEES_ENABLED",
        description=(
            "When False, invoices with fee_payer='client' are rejected "
            "at checkout. Set to False to disable client-paid fees."
        ),
    )

    PAYSTACK_FOUNDING_SILVER_MONTHLY_PLAN_CODE: str = Field(
        default="",
        env="PAYSTACK_FOUNDING_SILVER_MONTHLY_PLAN_CODE",
    )
    PAYSTACK_FOUNDING_SILVER_YEARLY_PLAN_CODE: str = Field(
        default="",
        env="PAYSTACK_FOUNDING_SILVER_YEARLY_PLAN_CODE",
    )
    PAYSTACK_SILVER_MONTHLY_PLAN_CODE: str = Field(
        default="",
        env="PAYSTACK_SILVER_MONTHLY_PLAN_CODE",
    )
    PAYSTACK_SILVER_YEARLY_PLAN_CODE: str = Field(
        default="",
        env="PAYSTACK_SILVER_YEARLY_PLAN_CODE",
    )
    # ────────────────────────────────
    # 5. WHATSAPP (Meta Graph API)
    # ────────────────────────────────
    WHATSAPP_TOKEN: str = Field(..., env="WHATSAPP_TOKEN")
    WHATSAPP_PHONE_ID: str = Field(..., env="WHATSAPP_PHONE_ID")
    WHATSAPP_TEMPLATE_NAME: str = Field(
        default="payla_reminder",
        env="WHATSAPP_TEMPLATE_NAME",
    )

    # ────────────────────────────────
    # 6. SMS (Termii)
    # ────────────────────────────────
    TERMII_API_KEY: str = Field(..., env="TERMII_API_KEY")
    TERMII_SENDER_ID: str = Field(
        default="Payla",
        env="TERMII_SENDER_ID",
    )

    # ────────────────────────────────
    # 7. RESEND (transactional email)
    # ────────────────────────────────
    RESEND_API_KEY: str = Field(..., env="RESEND_API_KEY")

     # ────────────────────────────────
    # 7b. PAYLA PRICING
    # ────────────────────────────────
    PAYLA_SILVER_MONTHLY_PRICE_NGN: int = Field(
        default=7500,
        env="PAYLA_SILVER_MONTHLY_PRICE_NGN",
    )
    PAYLA_SILVER_YEARLY_PRICE_NGN: int = Field(
        default=75000,
        env="PAYLA_SILVER_YEARLY_PRICE_NGN",
    )
    PAYLA_FOUNDING_SILVER_MONTHLY_PRICE_NGN: int = Field(
        default=7500,
        env="PAYLA_FOUNDING_SILVER_MONTHLY_PRICE_NGN",
    )
    PAYLA_FOUNDING_SILVER_YEARLY_PRICE_NGN: int = Field(
        default=75000,
        env="PAYLA_FOUNDING_SILVER_YEARLY_PRICE_NGN",
    )

        # ────────────────────────────────
    # 7c. REMINDER WORKER
    # ────────────────────────────────
    REMINDER_CHECK_INTERVAL_SECONDS: int = Field(
        default=60,
        env="REMINDER_CHECK_INTERVAL_SECONDS",
        description="Seconds between reminder_loop passes.",
    )
    REMINDER_MAX_RETRIES: int = Field(
        default=3,
        env="REMINDER_MAX_RETRIES",
        description="Send attempts per channel before giving up.",
    )
    REMINDER_RETRY_INTERVAL_SECONDS: int = Field(
        default=300,
        env="REMINDER_RETRY_INTERVAL_SECONDS",
        description="Seconds between retry attempts on a channel.",
    )
    REMINDER_LOCK_TIMEOUT_MINUTES: int = Field(
        default=10,
        env="REMINDER_LOCK_TIMEOUT_MINUTES",
        description=(
            "Minutes before a reminder lock is considered stale "
            "and can be re-acquired by another worker."
        ),
    )

    # ────────────────────────────────
    # 8. SECURITY
    # ────────────────────────────────
    SECRET_KEY: str = Field(
        default="change-me-in-production",
        env="SECRET_KEY",
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 1 week

    # ────────────────────────────────
    # 9. EMAIL (legacy — Gmail SMTP)
    # ────────────────────────────────
    GMAIL_USER: str = Field(..., env="GMAIL_USER")
    GMAIL_PASS: str = Field(..., env="GMAIL_PASS")
    LAYLA_USER: str = Field(..., env="LAYLA_USER")
    LAYLA_EMAIL_PASS: str = Field(..., env="LAYLA_EMAIL_PASS")
    APP_BASE_URL: AnyUrl = Field(..., env="APP_BASE_URL")

    # ────────────────────────────────
    # 10. WHATSAPP / SMS (legacy — Twilio)
    # ────────────────────────────────
    TWILIO_SID: str = Field(default="", env="TWILIO_SID")
    TWILIO_AUTH_TOKEN: str = Field(default="", env="TWILIO_AUTH_TOKEN")
    TWILIO_WHATSAPP_NUMBER: str = Field(
        default="",
        env="TWILIO_WHATSAPP_NUMBER",
    )
    TWILIO_SMS_NUMBER: str = Field(default="", env="TWILIO_SMS_NUMBER")

    BASE_URL: str = Field(default="", env="BASE_URL")

    # ────────────────────────────────
    # 11. CLOUDINARY
    # ────────────────────────────────
    CLOUDINARY_CLOUD_NAME: str = Field(
        ..., env="CLOUDINARY_CLOUD_NAME"
    )
    CLOUDINARY_API_KEY: str = Field(..., env="CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET: str = Field(
        ..., env="CLOUDINARY_API_SECRET"
    )


    class Config:
        case_sensitive = False
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# Create singleton
settings = Settings()