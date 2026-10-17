# app/models/founding_model.py
"""Founding member signup and verification models."""

import re
from typing import Optional
from app.core.constants import (
    INAPPROPRIATE_WORDS,
    RESERVED_USERNAMES,
    USERNAME_PATTERN,
)

from pydantic import BaseModel, EmailStr, validator


class FoundingSignupRequest(BaseModel):
    """Payload for creating a founding member account."""

    username: str
    email: EmailStr
    password: str

    @validator("username")
    def validate_username(cls, v):
        v = v.lower().strip()

        if not USERNAME_PATTERN.fullmatch(v):
            raise ValueError(
                "Username must be 3-20 characters using lowercase "
                "letters, numbers, hyphens, or underscores"
            )

        if v in RESERVED_USERNAMES:
            raise ValueError("This username is reserved")

        if any(word in v for word in INAPPROPRIATE_WORDS):
            raise ValueError("Username contains inappropriate content")

        return v

    @validator("password")
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class FoundingSignupResponse(BaseModel):
    """Response after a successful founding signup."""

    success: bool
    message: str
    requires_verification: bool = True
    email: str
    username: str


class ResendVerificationRequest(BaseModel):
    """Payload for resending a verification email."""

    email: EmailStr


class FoundingStatusResponse(BaseModel):
    """Response shape for the founding status lookup."""

    exists: bool
    verified: bool = False
    founding_member: bool = False
    plan: str = "free"
    username: Optional[str] = None
    message: Optional[str] = None