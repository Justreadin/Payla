# app/models/profile_model.py
"""Profile update request model.

Restricts what a client is allowed to change through the profile
settings endpoint. Trust fields, plan fields, and analytics counters
are server-managed and cannot be set from this request.
"""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class ProfileUpdateRequest(BaseModel):
    """Fields a user is allowed to change through profile settings."""

    model_config = ConfigDict(extra="forbid")

    full_name: Optional[str] = None
    business_name: Optional[str] = None
    username: Optional[str] = None
    phone_number: Optional[str] = None
    tagline: Optional[str] = None

    # Account default for newly created invoices.
    # Individual invoices can override this preference.
    default_invoice_fee_payer: Optional[
        Literal["merchant", "client"]
    ] = None
    # Silver only. Free users attempting to set this to "vip"
    # are rejected at the endpoint, not by the model.
    preferred_domain: Optional[Literal["ng", "vip"]] = None