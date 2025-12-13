# models/user_model.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Literal, Dict
from datetime import datetime, timedelta, timezone


class User(BaseModel):
    """Payla user — profile, payout, stats, auth, and subscription features."""

    # ---------------- Profile ----------------
    id: str = Field(..., alias="_id")
    firebase_uid: Optional[str] = None
    full_name: str
    email: EmailStr
    email_verified: bool = False
    phone_number: Optional[str] = None
    business_name: str = ""
    username: str = ""
    onboarding_complete: bool = False
    logo_url: Optional[str] = None
    tagline: Optional[str] = None
    verify_token: Optional[str] = None


    # ---------------- Payout ----------------
    payout_bank: Optional[str] = None
    payout_account_number: str = ""

    # ---------------- Paystack ----------------
    paystack_subaccount_code: Optional[str] = None
    subscription_id: Optional[str] = None         # Paystack subscription ID
    paystack_customer_code: Optional[str] = None # Paystack customer code

    # ---------------- Plan / Subscription ----------------
    plan: Literal["free", "silver", "gold", "opal"] = "free"
    trial_end_date: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(days=14))
    presell_end_date: Optional[datetime] = None        # Optional: 1 year from signup
    plan_start_date: Optional[datetime] = None         # When current plan started
    next_billing_date: Optional[datetime] = None       # For subscription renewal

    # Feature flags
    international_enabled: bool = True

    # ---------------- Stats ----------------
    total_invoices: int = 0
    total_earned: float = 0.0

    # ---------------- Metadata ----------------
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    default_invoice_theme: str = "midnight-void"
    custom_invoice_colors: Optional[Dict[str, str]] = None
    show_payla_footer: bool = True

    # ---------------- Helpers ----------------
    def is_trial_active(self) -> bool:
        """Return True if user is still in trial period."""
        if self.trial_end_date:
            return datetime.now(timezone.utc) < self.trial_end_date
        return False

    def is_subscription_active(self) -> bool:
        """Return True if user has an active subscription or trial."""
        if self.plan == "free":
            return self.is_trial_active()
        return self.subscription_id is not None or self.is_trial_active()

    def can_access_silver_features(self) -> bool:
        """Return True if user can access Silver features (trial or Silver+ plan)."""
        return self.is_subscription_active() and self.plan in ["silver", "gold", "opal"]

    class Config:
        orm_mode = True
        from_attributes = True
        allow_population_by_field_name = True
        populate_by_name = True
