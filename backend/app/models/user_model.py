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

    # ---------------- Payout & Banking (Subaccount Ready) ----------------
    payout_bank: Optional[str] = None            # e.g., "Access Bank"
    payout_bank_code: Optional[str] = None       # e.g., "044" (Required for Paystack)
    payout_account_number: str = ""              # 10 digits
    payout_account_name: Optional[str] = None    # Verified name from bank
    bank_verified: bool = False                  # Flag if Paystack verified the info

    # ---------------- Paystack Integration ----------------
    # Changed from subaccount_code to match Paystack naming: "SET_xxxxxx"
    paystack_subaccount_id: Optional[str] = None 
    paystack_customer_code: Optional[str] = None # For their own subscription billing
    subscription_id: Optional[str] = None 

    # ---------------- Plan / Subscription ----------------
    plan: Literal["free", "silver", "gold", "opal", "presell"] = "free"
    trial_end_date: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(days=14))
    
    presell_claimed: bool = False
    presell_eligible: bool = False
    presell_id: Optional[str] = None
    presell_end_date: Optional[datetime] = None
    
    plan_start_date: Optional[datetime] = None 
    next_billing_date: Optional[datetime] = None
    subscription_end: Optional[datetime] = None

    # ---------------- Stats & Flags ----------------
    international_enabled: bool = True
    total_invoices: int = 0
    total_earned: float = 0.0 # This is now the "Source of Truth" for dashboard

    # ---------------- Metadata ----------------
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # ---------------- Layla & Nudge Tracking ----------------
    billing_nudge_status: Literal["active", "72h_sent", "expired_sent"] = "active"
    last_nudge_date: Optional[datetime] = None
    onboarding_step: int = 0  

    # ---------------- UI Preferences ----------------
    default_invoice_theme: str = "midnight-void"
    custom_invoice_colors: Optional[Dict[str, str]] = None
    show_payla_footer: bool = True

    # ---------------- Helpers ----------------
    def is_trial_active(self) -> bool:
        if self.trial_end_date:
            return datetime.now(timezone.utc) < self.trial_end_date
        return False

    def is_subscription_active(self) -> bool:
        now = datetime.now(timezone.utc)
        if self.plan == "presell" and self.presell_end_date and now < self.presell_end_date:
            return True
        if self.subscription_end and now < self.subscription_end:
            return True
        return self.is_trial_active()

    def can_access_silver_features(self) -> bool:
        return self.is_subscription_active() or self.plan in ["silver", "gold", "opal", "presell"]

    def has_payout_setup(self) -> bool:
        """Helper to check if the user can receive money via subaccounts."""
        return bool(self.paystack_subaccount_id and self.bank_verified)

    def get_layla_status(self) -> str:
        if self.onboarding_step >= 5: return "Graduated"
        if self.onboarding_step == 0: return "Not Started"
        return f"Lesson {self.onboarding_step} of 5"

    model_config = {
        "from_attributes": True,
        "populate_by_name": True
    }