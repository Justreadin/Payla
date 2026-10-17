# app/models/onboarding_model.py
"""Onboarding payload model.

Onboarding creates a Free account. It deliberately has no plan field,
because a paid subscription must be granted only by the verified
subscription checkout flow.
"""

from pydantic import BaseModel, Field


class OnboardingPayload(BaseModel):
    """Payload for completing account onboarding."""

    username: str = Field(min_length=3, max_length=30)
    payout_bank: str = Field(min_length=1)
    payout_account_number: str = Field(min_length=1)
    business_name: str = Field(default="", max_length=120)

    # No plan field.
    # Onboarding must never grant a paid subscription.