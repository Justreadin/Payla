# app/models/payout_model.py
"""Payout account models.

Request and response shapes for the payout settings endpoints in
app/routers/payout_router.py. Kept separate from User because these
are API contracts, not stored documents.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, validator


class PayoutAccountIn(BaseModel):
    """Payload for saving a payout bank account."""

    bank_code: str = Field(
        ...,
        description="Paystack bank code",
    )
    account_number: str = Field(
        ...,
        min_length=10,
        max_length=10,
        pattern=r"^\d{10}$",
        description="10-digit bank account number",
    )

    @validator("account_number")
    def validate_account(cls, value):
        if not value.isdigit():
            raise ValueError("Account number must contain only digits")
        return value


class PayoutAccountOut(BaseModel):
    """Response shape for a saved payout bank account."""

    bank_code: str
    account_number: str
    account_name: str
    bank_name: str
    subaccount_code: Optional[str] = None
    is_verified: bool = False
    updated_at: datetime


class DeleteResponse(BaseModel):
    """Generic delete confirmation."""

    message: str = "Payout account removed successfully"