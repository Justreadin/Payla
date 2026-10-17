# app/models/invoice_model.py
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field


FeePayer = Literal["merchant", "client"]


class InvoiceCreate(BaseModel):
    """Payload sent by the frontend when creating or updating an invoice."""

    amount: float = Field(..., gt=0)
    currency: Literal["NGN"] = "NGN"
    description: str
    due_date: datetime
    client_phone: Optional[str] = None
    client_email: Optional[str] = None
    client_name: Optional[str] = None

    # None means inherit the merchant's account-level default.
    fee_payer: Optional[FeePayer] = None


class Invoice(BaseModel):
    """Database representation of an invoice."""

    id: str = Field(..., alias="_id")
    sender_id: str

    amount: float = Field(..., gt=0)
    currency: Literal["NGN"] = "NGN"
    description: str
    due_date: datetime

    client_phone: str = ""
    client_email: Optional[str] = None
    client_name: Optional[str] = None

    sender_business_name: str
    sender_phone: str

    status: Literal[
        "draft",
        "pending",
        "paid",
        "overdue",
        "failed",
    ] = "draft"

    draft_data: Optional[dict] = None

    invoice_url: Optional[str] = None
    payment_url: Optional[str] = None
    published_at: Optional[datetime] = None

    paystack_reference: Optional[str] = None
    transaction_reference: Optional[str] = None

    # New invoices use merchant/client.
    # "receiver" remains accepted when loading legacy documents.
    # The router normalizes it to "merchant" before new writes.
    fee_payer: Literal["merchant", "client"] = "merchant"

    payment_channel: Optional[str] = None
    country: Optional[str] = None

    paystack_subaccount_code: Optional[str] = None
    sender_subaccount_code: Optional[str] = None

    payout_status: Optional[str] = None
    expected_payout_at: Optional[datetime] = None
    payout_reference: Optional[str] = None

    footer_note: str = "Secured by Payla"
    default_invoice_theme: str = "midnight-void"
    custom_invoice_colors: Optional[dict] = None
    show_payla_footer: bool = True

    is_returning_client: bool = False

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    paid_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        populate_by_name = True


# ============================================================
# Request models for the invoice router
# ============================================================

class TempReminderPayload(BaseModel):
    """
    Internal payload used when publishing an invoice triggers the
    default reminder schedule. Not exposed to clients.
    """

    preset: str = "standard"
    manual_dates: Optional[List[str]] = None
    method_priority: List[str] = Field(
        default_factory=lambda: ["whatsapp", "sms", "email"]
    )
    custom_message: str = ""


class StatusUpdate(BaseModel):
    """Client-initiated invoice status reconciliation payload."""

    status: str
    transaction_reference: Optional[str] = None
    payer_email: Optional[EmailStr] = None


class PaymentInitializationRequest(BaseModel):
    """Payload for initializing an invoice payment attempt."""

    payer_email: EmailStr