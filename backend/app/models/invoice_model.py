from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime

class InvoiceCreate(BaseModel):
    """Payload sent from the frontend when a user creates an invoice."""
    amount: float = Field(..., gt=0, description="Amount in the selected currency")
    currency: Literal["NGN", "USD", "GBP", "EUR"] = "NGN"
    description: str = Field(..., description="What the payment is for")
    due_date: datetime = Field(..., description="When the payment is due")
    client_phone: Optional[str] = None
    client_email: Optional[str] = None  

class Invoice(BaseModel):
    """Database representation of an invoice."""
    id: str = Field(..., alias="_id")
    sender_id: str

    amount: float
    currency: Literal["NGN", "USD", "GBP", "EUR"]
    description: str
    due_date: datetime
    client_phone: str
    client_email: Optional[str] = None  

    sender_business_name: str
    sender_phone: str

    status: Literal["draft", "pending", "paid", "overdue", "failed"] = "draft"
    draft_data: Optional[dict] = None
    invoice_url: Optional[str] = None
    published_at: Optional[datetime] = None
    payment_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    paid_at: Optional[datetime] = None
    paystack_reference: Optional[str] = None

    fee_payer: Literal["receiver", "client"] = "client"
    payment_channel: Optional[str] = None
    country: Optional[str] = None

    footer_note: str = "Secured by Payla"
    default_invoice_theme: str = "midnight-void"
    custom_invoice_colors: Optional[dict] = None
    show_payla_footer: bool = True

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
