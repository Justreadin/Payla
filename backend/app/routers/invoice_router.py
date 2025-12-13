import asyncio
from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from typing import List, Literal
from uuid import uuid4
from datetime import datetime, timezone
import httpx
from google.cloud import firestore

from app.models.invoice_model import InvoiceCreate, Invoice
from app.core.firebase import db
from app.models.user_model import User
from app.core.auth import get_current_user
from app.core.config import settings
from app.services.reminder_service import schedule_reminders_for_invoice
from app.core.notifications import create_notification
from app.core.subscription import require_silver
from app.tasks.payout import initiate_payout

router = APIRouter(prefix="/invoices", tags=["Invoices"])

class TempReminderPayload:
    preset: str = "standard"
    manual_dates = None
    method_priority = ["whatsapp", "sms", "email"]

def clean_phone(raw: str | None) -> str:
    if not raw:
        return ""
    
    num = "".join(filter(str.isdigit, raw))

    if len(num) == 11 and num.startswith("0"):
        num = num[1:]
    elif len(num) == 10 and num.startswith("0"):
        num = num[1:]

    return num if len(num) == 10 else ""


# ----------------------------
# 1. CREATE DRAFT INVOICE
# ----------------------------
@router.post("/", response_model=Invoice, status_code=status.HTTP_201_CREATED)
async def create_invoice_draft(
    payload: InvoiceCreate,
    current_user: User = Depends(require_silver)
):
    short_id = f"{current_user.username}{str(uuid4())[:8]}"  # Embed username
    invoice_id = f"draft_{short_id}"
    
    draft_data = payload.dict()
    draft_data["client_phone"] = clean_phone(draft_data.get("client_phone"))

    invoice = Invoice(
        _id=invoice_id,
        sender_id=current_user.id,
        sender_business_name=current_user.business_name or current_user.full_name,
        sender_phone=current_user.phone_number or "",
        amount=payload.amount,
        currency=payload.currency,
        description=payload.description,
        due_date=payload.due_date,
        client_phone=draft_data["client_phone"],
        client_email=getattr(payload, "client_email", None),
        status="draft",
        draft_data=draft_data,
        invoice_url=f"/i/{short_id}",  # Public link includes username
        created_at=datetime.now(timezone.utc)
    )

    db.collection("invoices").document(invoice_id).set(invoice.dict(by_alias=True))
    return invoice


# ----------------------------
# 2. UPDATE DRAFT INVOICE
# ----------------------------
@router.patch("/{invoice_id}", response_model=Invoice)
async def update_invoice_draft(
    invoice_id: str,
    payload: InvoiceCreate,
    current_user: User = Depends(require_silver)
):
    ref = db.collection("invoices").document(invoice_id)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(404, "Invoice not found")

    inv = Invoice(**doc.to_dict())
    if inv.sender_id != current_user.id:
        raise HTTPException(403, "Not authorized")
    if inv.status != "draft":
        raise HTTPException(400, "Cannot edit published/paid invoice")

    draft_data = payload.dict()
    ref.update({
        "draft_data": draft_data,
        "updated_at": datetime.now(timezone.utc)
    })

    updated_doc = ref.get()
    return Invoice(**updated_doc.to_dict())


# ----------------------------
# 3. PUBLISH INVOICE
# ----------------------------
@router.post("/{invoice_id}/publish", response_model=Invoice)
async def publish_invoice(
    invoice_id: str,
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(require_silver)
):
    if current_user is None:
        raise HTTPException(401, "Unauthorized")

    if background_tasks is None:
        background_tasks = BackgroundTasks()

    invoice_ref = db.collection("invoices").document(invoice_id)
    invoice_doc = invoice_ref.get()

    if not invoice_doc.exists:
        raise HTTPException(404, "Invoice not found")

    invoice = Invoice(**invoice_doc.to_dict())

    if invoice.sender_id != current_user.id:
        raise HTTPException(403, "Not authorized")

    if invoice.status != "draft":
        raise HTTPException(400, "Invoice already published")

    data = invoice.draft_data
    if not data:
        raise HTTPException(400, "Missing draft data")

    if not data.get("client_phone") and not data.get("client_email"):
        raise HTTPException(
            400,
            "Add at least one client contact before publishing"
        )

    short_id = invoice_id.split("_")[-1]

    # Initialize Paystack
    paystack_payload = {
        "amount": int(data["amount"] * 100),
        "email": data.get("client_email") or "client@payla.vip",
        "currency": data["currency"],
        "reference": invoice_id,
        "callback_url": f"{settings.FRONTEND_URL}/i/{short_id}/paid",
        "metadata": {
            "invoice_id": invoice_id,
            "user_id": current_user.id,
            "type": "invoice",
            "client_phone": clean_phone(data.get("client_phone")),
        }
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.paystack.co/transaction/initialize",
            json=paystack_payload,
            headers={"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
        )

    if resp.status_code != 200 or not resp.json().get("status"):
        raise HTTPException(400, "Paystack initialization failed")

    paystack_data = resp.json()["data"]

    # 🔥 Convert draft → published invoice
    invoice_ref.update({
        "amount": data["amount"],
        "currency": data["currency"],
        "description": data.get("description"),
        "due_date": data["due_date"],
        "status": "pending",
        "client_email": data.get("client_email"),
        "client_phone": clean_phone(data.get("client_phone")),
        "client_name": data.get("client_name"),
        "invoice_url": f"/i/{short_id}",
        "payment_url": paystack_data["authorization_url"],
        "paystack_reference": paystack_data["reference"],
        "published_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "draft_data": firestore.DELETE_FIELD,  # ❌ draft is gone
    })

    # Background tasks
    background_tasks.add_task(
        initiate_payout,
        user_id=current_user.id,
        amount_ngn=data["amount"],
        reference=invoice_id,
    )

    background_tasks.add_task(
        schedule_reminders_for_invoice,
        invoice_id=invoice_id,
        payload=TempReminderPayload(),
        user_id=current_user.id,
    )

    create_notification(
        user_id=current_user.id,
        title="Invoice Sent",
        message=f"Invoice of ₦{data['amount']:,} sent",
        type="success",
        link="/dashboard/invoice",
    )

    updated_doc = invoice_ref.get()
    return Invoice(**updated_doc.to_dict())


# --------------------------------------------------------------
# 4. GET USER'S INVOICES
# --------------------------------------------------------------
@router.get("/", response_model=List[Invoice])
async def get_my_invoices(current_user=Depends(get_current_user)):
    user = current_user
    docs = db.collection("invoices").where("sender_id", "==", user.id).stream()

    invoices = []
    now = datetime.now(timezone.utc)

    for doc in docs:
        data = doc.to_dict()
        inv = Invoice(**data)

        if inv.due_date and inv.due_date.tzinfo is None:
            inv.due_date = inv.due_date.replace(tzinfo=timezone.utc)

        if inv.status == "pending" and inv.due_date and inv.due_date < now:
            db.collection("invoices").document(inv._id).update({
                "status": "overdue",
                "updated_at": now
            })
            inv.status = "overdue"

        invoices.append(inv)

    return invoices

# --------------------------------------------------------------
# 5. GET SINGLE INVOICE
# --------------------------------------------------------------
@router.get("/{invoice_id}", response_model=dict)
async def get_invoice(invoice_id: str):
    doc = db.collection("invoices").document(invoice_id).get()
    if not doc.exists:
        raise HTTPException(404, "Invoice not found")

    invoice_data = doc.to_dict()
    invoice = Invoice(**invoice_data)
    now = datetime.now(timezone.utc)

    if invoice.due_date and invoice.due_date.tzinfo is None:
        invoice.due_date = invoice.due_date.replace(tzinfo=timezone.utc)

    if invoice.status == "pending" and invoice.due_date and invoice.due_date < now:
        db.collection("invoices").document(invoice_id).update({
            "status": "overdue",
            "updated_at": now
        })
        invoice.status = "overdue"

    response = invoice.dict(by_alias=True)

    user_doc = db.collection("users").document(invoice.sender_id).get()
    if user_doc.exists:
        user_data = user_doc.to_dict()
        user = User(**user_data)
        response["sender_username"] = user.username
        response["sender_logo"] = user.custom_invoice_colors.get("logo") if user.custom_invoice_colors else None
        response["sender_email"] = user.email
    else:
        response["sender_username"] = ""
        response["sender_logo"] = None
        response["sender_email"] = "user@company.com"

    if invoice.status == "paid":
        response["payment_url"] = None
        response["message"] = "This invoice has been paid. Thank you!"
    elif invoice.status == "overdue":
        response["message"] = "This invoice is overdue."
    elif invoice.status == "failed":
        response["message"] = "Payment failed. Please try again."
    elif invoice.status == "draft":
        response["message"] = "This is a draft. Publish to send."

    return response

# --------------------------------------------------------------
# 6. UPDATE STATUS
# --------------------------------------------------------------
@router.patch("/{invoice_id}/status", include_in_schema=False)
async def update_invoice_status(
    invoice_id: str,
    status: Literal["pending", "paid", "overdue", "failed"],
    current_user=Depends(get_current_user)
):
    allowed = ["pending", "paid", "overdue", "failed"]
    if status not in allowed:
        raise HTTPException(400, "Invalid status")

    ref = db.collection("invoices").document(invoice_id)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(404, "Invoice not found")

    now = datetime.now(timezone.utc)
    update_data = {"status": status, "updated_at": now}
    if status == "paid":
        update_data["paid_at"] = now

    ref.update(update_data)
    return {"message": f"Invoice {invoice_id} → {status}"}

# --------------------------------------------------------------
# 7. DELETE INVOICE
# --------------------------------------------------------------
@router.delete("/{invoice_id}", response_model=dict)
async def delete_invoice(invoice_id: str, current_user: User = Depends(get_current_user)):
    ref = db.collection("invoices").document(invoice_id)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(404, "Invoice not found")

    invoice = Invoice(**doc.to_dict())
    if invoice.sender_id != current_user.id:
        raise HTTPException(403, "Not authorized to delete this invoice")

    ref.delete()
    return {"success": True, "message": "Invoice deleted successfully"}
