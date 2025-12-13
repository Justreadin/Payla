# models/auth.py
from pydantic import BaseModel
from typing import Optional
from .user_model import User


class LoginRequest(BaseModel):
    id_token: str  # Firebase ID token


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    business_name: Optional[str] = None
    phone_number: Optional[str] = None
    username: Optional[str] = None
    payout_bank: Optional[str] = None
    payout_account_number: Optional[str] = None


class AuthResponse(BaseModel):
    user: User
    message: str = "Login successful"