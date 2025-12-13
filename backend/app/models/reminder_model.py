# models/reminder_model.py
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal
from datetime import datetime


class ReminderSettings(BaseModel):
    id: str = Field(..., alias="_id")
    user_id: str

    methods: list[Literal["whatsapp", "sms", "email"]] = ["whatsapp", "sms"]  # Priority order
    frequency: Literal["daily", "every_two_days", "weekly", "on_due_date"] = "every_two_days"
    days_before_due: int = 3
    days_after_due: int = 1
    default_message: str = "Hi {name}! Your ₦{amount} invoice is due on {due_date}. Pay now: {link} 💸\n\n– Payla"
    email_subject: str = "Payment Reminder from {business_name}"
    active: bool = True

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        from_attributes = True


class ReminderCreate(BaseModel):
    # User-selected priority channel ordering
    method_priority: Optional[List[str]] = None
    
    # Custom message overrides
    custom_message: Optional[str] = None
    custom_email_subject: Optional[str] = None

    # What your service actually expects
    manual_dates: Optional[List[str]] = None   # ISO strings
    preset: Optional[str] = None     



class Reminder(BaseModel):
    id: str = Field(..., alias="_id")
    invoice_id: str
    user_id: str

    method: Literal["whatsapp", "sms", "email"]
    channel_used: Optional[Literal["whatsapp", "sms", "email"]] = None
    message: str
    status: Literal["pending", "sent", "failed", "delivered"] = "pending"

    next_send: datetime
    last_sent: Optional[datetime] = None
    delivery_sid: Optional[str] = None  # Twilio SID

    created_at: datetime = Field(default_factory=datetime.utcnow)