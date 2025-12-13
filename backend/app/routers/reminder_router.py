from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import List
from app.models.reminder_model import ReminderSettings, ReminderCreate, Reminder
from app.core.firebase import db
from app.core.auth import get_current_user
from app.services.reminder_service import schedule_reminders_for_invoice

from app.core.subscription import require_silver

router = APIRouter(prefix="/reminders", tags=["Reminders"])


@router.get("/settings", response_model=ReminderSettings)
async def get_settings(user=Depends(get_current_user)):
    doc = db.collection("reminder_settings").document(user.id).get()

    if not doc.exists:
        default = ReminderSettings(_id=user.id, user_id=user.id)
        db.collection("reminder_settings").document(user.id).set(default.dict(by_alias=True))
        return default

    return ReminderSettings(**doc.to_dict())


@router.put("/settings", response_model=ReminderSettings, dependencies=[Depends(require_silver)])
async def update_settings(settings: ReminderSettings, user=Depends(get_current_user)):

    # FIX: Assign correct Pydantic field
    settings._id = user.id
    settings.user_id = user.id

    settings.updated_at = datetime.utcnow()

    db.collection("reminder_settings").document(user.id).set(
        settings.dict(by_alias=True), merge=True
    )

    return settings


@router.post("/invoice/{invoice_id}", response_model=List[Reminder], dependencies=[Depends(require_silver)])
async def create_invoice_reminders(
    invoice_id: str,
    payload: ReminderCreate,
    background: BackgroundTasks,
    user=Depends(get_current_user)
):
    inv_doc = db.collection("invoices").document(invoice_id).get()

    if not inv_doc.exists:
        raise HTTPException(404, "Invoice not found")

    invoice = inv_doc.to_dict()

    if invoice.get("sender_id") != user.id:
        raise HTTPException(403, "Unauthorized")

    # Optional but recommended:
    if invoice.get("status") in ("paid", "cancelled"):
        raise HTTPException(400, "Cannot add reminders to a completed or cancelled invoice")

    reminders = await schedule_reminders_for_invoice(invoice_id, payload, user.id)

    return reminders
