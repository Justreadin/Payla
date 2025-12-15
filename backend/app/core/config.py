# core/config.py
import http
import os
from pydantic import Field, AnyUrl
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # ────────────────────────────────
    # 1. APP & ENVIRONMENT
    # ────────────────────────────────
    PROJECT_NAME: str = "Payla"
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    DEBUG: bool = Field(default=True, env="DEBUG")
    BACKEND_URL: str = 'http://127.0.0.1:8000'

    # ────────────────────────────────
    # 2. FRONTEND
    # ────────────────────────────────
    FRONTEND_URL: AnyUrl = Field(
        default="https://payla.ng",
        env="FRONTEND_URL",
        description="Base URL for client app (e.g. https://payla.ng)"
    )

    # ────────────────────────────────
    # 3. FIREBASE / FIRESTORE
    # ────────────────────────────────
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = Field(
        default=None,
        env="GOOGLE_APPLICATION_CREDENTIALS",
        description="Path to Firebase service account JSON"
    )
    # Base64-encoded Firebase service account JSON
    PAYLA_FIREBASE_KEY: Optional[str] = Field(
        default=None,
        env="PAYLA_FIREBASE_KEY",
        description="Base64-encoded Firebase service account JSON"
    )

    # ────────────────────────────────
    # 4. PAYSTACK
    # ────────────────────────────────
    PAYSTACK_SECRET_KEY: str = Field(..., env="PAYSTACK_SECRET_KEY")
    PAYSTACK_PUBLIC_KEY: str = Field(..., env="PAYSTACK_PUBLIC_KEY")
    PAYSTACK_SECRET_PAYLA: str = Field(..., env="PAYSTACK_SECRET_PAYLA")
    PAYSTACK_PUBLIC_PAYLA: str = Field(..., env="PAYSTACK_PUBLIC_PAYLA")
    PAYSTACK_WEBHOOK_URL: AnyUrl = Field(
        default_factory=lambda: f"{os.getenv('BACKEND_URL', 'http://localhost:8000')}/webhook/paystack"
    )

    # ────────────────────────────────
    # 5. WHATSAPP (Meta API)
    # ────────────────────────────────
    WHATSAPP_TOKEN: str = Field(..., env="WHATSAPP_TOKEN")
    WHATSAPP_PHONE_ID: str = Field(..., env="WHATSAPP_PHONE_ID")
    WHATSAPP_TEMPLATE_NAME: str = "payla_reminder"

    # ────────────────────────────────
    # 6. SMS (Termii)
    # ────────────────────────────────
    TERMII_API_KEY: str = Field(..., env="TERMII_API_KEY")
    TERMII_SENDER_ID: str = "Payla"

    # ────────────────────────────────
    # 7. TASK QUEUE (Celery / Cloud Tasks)
    # ────────────────────────────────
    CELERY_BROKER_URL: str = Field(
        default="redis://localhost:6379/0",
        env="CELERY_BROKER_URL"
    )
    CELERY_RESULT_BACKEND: str = Field(
        default="redis://localhost:6379/0",
        env="CELERY_RESULT_BACKEND"
    )

    # ────────────────────────────────
    # 8. SECURITY
    # ────────────────────────────────
    SECRET_KEY: str = Field(default="change-me-in-production", env="SECRET_KEY")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 1 week

    # ────────────────────────────────
    # 9. EMAIL (Gmail)
    # ────────────────────────────────
    GMAIL_USER: str = Field(..., env="GMAIL_USER")
    GMAIL_PASS: str = Field(..., env="GMAIL_PASS")
    LAYLA_USER: str = Field(..., env="LAYLA_USER")
    LAYLA_EMAIL_PASS: str = Field(..., env="LAYLA_EMAIL_PASS")
    APP_BASE_URL: AnyUrl = Field(..., env="APP_BASE_URL")

     # ────────────────────────────────
    # 9. WHatsapp (Twilio)
    # ────────────────────────────────

    TWILIO_SID: str
    TWILIO_AUTH_TOKEN: str
    TWILIO_WHATSAPP_NUMBER: str
    TWILIO_SMS_NUMBER: str
    RESEND_API_KEY: str
    BASE_URL: str

    class Config:
        case_sensitive = False
        env_file = ".env"
        env_file_encoding = "utf-8"


# Create singleton
settings = Settings()
