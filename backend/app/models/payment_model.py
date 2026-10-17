
from datetime import datetime, timezone
from typing import Optional, Literal, Dict, Any

from pydantic import BaseModel, Field


class Payment(BaseModel):
    """Recorded payment for an invoice or public Paylink."""

    id: str = Field(..., alias="_id")
    user_id: str
    invoice_id: Optional[str] = None
    paylink_id: Optional[str] = None

    # Paystack transaction reference
    paystack_reference: str

    # Gross amount charged to the customer
    amount: float

    # Amount allocated to the merchant after applicable fees
    user_share: Optional[float] = None

    currency: Literal["NGN", "USD", "GBP", "EUR"] = "NGN"
    status: Literal["pending", "success", "failed", "refunded"] = "pending"

    channel: Optional[str] = None
    client_phone: Optional[str] = None
    fee_payer: Literal["client", "receiver"] = "client"

    paid_at: Optional[datetime] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    raw_event: Optional[Dict[str, Any]] = None

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
        "extra": "ignore",
    }
