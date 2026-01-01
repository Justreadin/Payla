# models/paylink.py
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class PaylinkCreate(BaseModel):
    """Payload when user creates/updates their @username link."""
    username: str = Field(..., description="e.g. 'tunde' → payla.ng/@tunde")
    display_name: str = Field(..., description="Shown on link page")
    description: Optional[str] = "Description/Tagline"
    currency: Literal["NGN", "USD", "GBP", "EUR"] = "NGN"


# models/paylink_model.py  (or paylink.py)
class Paylink(BaseModel):
    id: str = Field(..., alias="_id")
    user_id: str

    username: str
    display_name: str
    description: str
    currency: Literal["NGN", "USD", "GBP", "EUR"]
    active: bool = True

    link_url: str
    paystack_page_url: Optional[str] = None        # ← NEW
    paystack_reference: Optional[str] = None       # ← NEW (permanent reference)

    total_received: float = 0.0
    total_transactions: int = 0
    last_payment_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True
        populate_by_name = True
        include = {
            "paystack_page_url",
            "paystack_reference"
        }

# models/paylink_model.py

class CreatePaylinkTransactionRequest(BaseModel):
    paylink_username: str
    amount: float              # The TOTAL (Gross) amount the client pays (e.g. 1229)
    amount_requested: Optional[float] = None    # The BASE (Net) amount the user wanted (e.g. 1200)
    payer_email: str
    payer_name: Optional[str] = None
    payer_phone: Optional[str] = None
    notes: Optional[str] = None # Added this to match your router's getattr usage