
from datetime import datetime, timezone
from typing import Optional, Literal, Dict

from pydantic import BaseModel, EmailStr, Field


class User(BaseModel):
    """Payla user profile, payout configuration, analytics, and billing state."""

    # Profile
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
    preferred_domain: Literal["ng", "vip"] = "ng"
    verify_token: Optional[str] = None
    email_verified_reminder_sent_at: Optional[datetime] = None
    signup_source: Literal["auth", "founding", "landing", None] = None
    referred_by: Optional[str] = None 

    # Payout and banking
    payout_bank: Optional[str] = None
    payout_bank_code: Optional[str] = None
    payout_account_number: str = ""
    payout_account_name: Optional[str] = None
    bank_verified: bool = False

    # Bank confirmation (trust signal for the public paylink)
    bank_confirmation_status: Literal[
        "matched", "mismatch", "pending", "failed"
    ] = "pending"
    bank_confirmed_name: Optional[str] = None
    bank_confirmed_bank_name: Optional[str] = None
    bank_confirmed_account_last4: Optional[str] = None
    bank_confirmed_at: Optional[datetime] = None
    bank_confirmation_attempted_at: Optional[datetime] = None
    bank_confirmation_retry_count: int = 0

    # Paystack integration
    paystack_subaccount_id: Optional[str] = None
    paystack_customer_code: Optional[str] = None
    subscription_id: Optional[str] = None
    subscription_email_token: Optional[str] = None
    subscription_authorization_code: Optional[str] = None

    # Plan and subscription
    plan: Literal["free", "silver", "gold", "opal", "presell"] = "free"

    # Legacy field retained for old documents/API compatibility.
    # It does not grant access and has no automatic future-date default.
    trial_end_date: Optional[datetime] = None

    presell_claimed: bool = False
    presell_eligible: bool = False
    presell_id: Optional[str] = None
    presell_end_date: Optional[datetime] = None

    plan_start_date: Optional[datetime] = None
    next_billing_date: Optional[datetime] = None
    subscription_end: Optional[datetime] = None
    subscription_status: str = "inactive"
    billing_cycle: Optional[Literal["monthly", "yearly"]] = None
    paystack_plan_code: Optional[str] = None
    paystack_subscription_code: Optional[str] = None
    paystack_email_token: Optional[str] = None
    last_subscription_payment_reference: Optional[str] = None
    last_subscription_payment_at: Optional[datetime] = None
    cancel_at_period_end: bool = False
    subscription_cancel_requested_at: Optional[datetime] = None

    # Founding-member pricing protection
    founding_member_ever: bool = False
    founding_price_locked: bool = False
    founding_spot: Optional[int] = None
    founding_monthly_price_ngn: Optional[int] = None
    founding_yearly_price_ngn: Optional[int] = None

    # Internal operations only. Never accept this from public client input.
    manual_silver_override: bool = False

    # Stats and analytics
    international_enabled: bool = True
    total_invoices: int = 0
    total_earned: float = 0.0
    total_invoice_revenue: float = 0.0
    total_paylink_revenue: float = 0.0
    last_payout_at: Optional[datetime] = None

    # Metadata
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # Layla and nudge tracking
    billing_nudge_status: Literal[
        "active", "72h_sent", "expired_sent"
    ] = "active"
    last_nudge_date: Optional[datetime] = None
    onboarding_step: int = 0

    # UI preferences
    default_invoice_theme: str = "midnight-void"
    custom_invoice_colors: Optional[Dict[str, str]] = None
    show_payla_footer: bool = True

    # Invoice payment preferences
    # Applies to new invoices unless an individual invoice overrides it.
    default_invoice_fee_payer: Literal["merchant", "client"] = "merchant"

    @property
    def payout_bank_display(self) -> str:
        return self.payout_bank or "None"

    def is_trial_active(self) -> bool:
        """Legacy compatibility: trials never grant paid-feature access."""
        return False

    def is_subscription_active(self) -> bool:
        """Use the central subscription service as the source of truth."""
        from app.core.subscription import get_subscription_status

        result = get_subscription_status(self)
        return bool(result.get("is_active", False))

    def can_access_silver_features(self) -> bool:
        """Use the central entitlement rule, including manual overrides."""
        from app.core.subscription import can_access_silver_features

        return bool(can_access_silver_features(self))

    def has_payout_setup(self) -> bool:
        return bool(self.paystack_subaccount_id and self.bank_verified)

    def get_layla_status(self) -> str:
        if self.onboarding_step >= 5:
            return "Graduated"
        if self.onboarding_step == 0:
            return "Not Started"
        return f"Lesson {self.onboarding_step} of 5"

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
        "extra": "ignore",
    }
