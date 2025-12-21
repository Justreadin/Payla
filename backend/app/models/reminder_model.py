# models/reminder_model.py
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal
from datetime import datetime


class ReminderSettings(BaseModel):
    id: str = Field(..., alias="_id")
    user_id: str

    methods: list[Literal["whatsapp", "sms", "email"]] = ["whatsapp", "sms"]
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
    method_priority: Optional[List[str]] = None
    channels: Optional[List[Literal["whatsapp", "sms", "email"]]] = None
    
    custom_message: Optional[str] = None
    custom_email_subject: Optional[str] = None

    manual_dates: Optional[List[str]] = None
    preset: Optional[str] = None     


class Reminder(BaseModel):
    id: str = Field(..., alias="_id")
    invoice_id: str
    user_id: str

    # SOURCE OF TRUTH
    channels_selected: List[Literal["whatsapp", "sms", "email"]]

    # TRACK PROGRESS
    channel_used: List[Literal["whatsapp", "sms", "email"]] = []

    message: str
    status: Literal["pending", "sent", "failed", "cancelled", "delivered"] = "pending"

    next_send: datetime
    last_sent: Optional[datetime] = None
    delivery_sid: Optional[str] = None
    
    # ✅ ADD THIS - matches your schedule_reminders_for_invoice
    active: bool = True
    
    # ✅ ADD THESE - for lock mechanism
    locked: bool = False
    locked_at: Optional[datetime] = None
    
    # ✅ ADD THESE - for tracking failures/cancellations
    failed_reason: Optional[str] = None
    cancelled_reason: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True
        from_attributes = True