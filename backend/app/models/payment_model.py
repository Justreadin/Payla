# models/payment.py
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class Payment(BaseModel):
    """One payment (invoice or personal link)."""
    id: str = Field(..., alias="_id")
    user_id: str

    # Link to source
    invoice_id: Optional[str] = None   # if from an invoice
    paylink_id: Optional[str] = None   # if from @username link

    paystack_reference: str
    amount: float
    currency: Literal["NGN", "USD", "GBP", "EUR"] = "NGN"

    status: Literal["pending", "success", "failed", "refunded"] = "pending"
    channel: Optional[str] = None      # card, bank, ussd, mobile_money

    # Client info (only phone for reminders)
    client_phone: Optional[str] = None

    # Who pays Paystack fee
    fee_payer: Literal["client", "receiver"] = "client"

    # Timestamps
    paid_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Raw Paystack webhook (debug)
    raw_event: Optional[dict] = None

    class Config:
        orm_mode = True
        allow_population_by_field_name = True