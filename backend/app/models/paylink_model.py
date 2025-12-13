# models/paylink.py
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class PaylinkCreate(BaseModel):
    """Payload when user creates/updates their @username link."""
    username: str = Field(..., description="e.g. 'tunde' → payla.ng/@tunde")
    display_name: str = Field(..., description="Shown on link page")
    description: Optional[str] = "Fast, secure payments via Payla"
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
        orm_mode = True
        allow_population_by_field_name = True
        include = {
            "paystack_page_url",
            "paystack_reference"
        }

class CreatePaylinkTransactionRequest(BaseModel):
    paylink_username: str
    amount: float          # Amount the client wants to pay (e.g. 5000)
    payer_email: str
    payer_name: Optional[str] = None
    payer_phone: Optional[str] = None