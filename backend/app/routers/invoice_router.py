import asyncio
from app.utils.firebase import firestore_run
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


def normalize_phone(raw: str | None) -> str:
    """
    Normalize phone number while preserving country code.
    Returns format: +COUNTRYCODEPHONENUMBER (e.g., +2348012345678 or +919041385402)
    """
    if not raw:
        return ""

    # Remove spaces, dashes, parentheses
    num = raw.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    
    # Keep only digits and leading +
    if num.startswith("+"):
        prefix = "+"
        num = "".join(filter(str.isdigit, num[1:]))
        num = prefix + num
    else:
        num = "".join(filter(str.isdigit, num))
    
    # Already has country code with +
    if num.startswith("+") and len(num) > 10:
        return num
    
    # Has country code but missing +
    if num.startswith("234") and len(num) == 13:  # Nigerian with 234
        return "+" + num
    elif num.startswith("91") and len(num) == 12:  # Indian with 91
        return "+" + num
    elif num.startswith("1") and len(num) == 11:  # US/Canada with 1
        return "+" + num
    
    # Starts with 0 (local format) - assume Nigerian
    if num.startswith("0") and len(num) == 11:
        return "+234" + num[1:]
    
    # 10 digits only - assume Nigerian
    if len(num) == 10:
        return "+234" + num
    
    # Return as-is if we can't determine
    return "+" + num if not num.startswith("+") else num


# ----------------------------
# 1. CREATE DRAFT INVOICE
# ----------------------------
@router.post("/", response_model=Invoice, status_code=status.HTTP_201_CREATED)
async def create_invoice_draft(
    payload: InvoiceCreate,
    current_user: User = Depends(require_silver),
):
    short_id = f"{current_user.username}{str(uuid4())[:8]}"
    invoice_id = f"draft_{short_id}"

    draft_data = payload.dict()
    draft_data["client_phone"] = normalize_phone(draft_data.get("client_phone"))

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
        invoice_url=f"/i/{short_id}",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    await firestore_run(
        db.collection("invoices").document(invoice_id).set,
        invoice.dict(by_alias=True),
    )

    return invoice


# ----------------------------
# 2. UPDATE DRAFT INVOICE
# ----------------------------
@router.patch("/{invoice_id}", response_model=Invoice)
async def update_invoice_draft(
    invoice_id: str,
    payload: InvoiceCreate,
    current_user: User = Depends(require_silver),
):
    ref = db.collection("invoices").document(invoice_id)
    doc = await firestore_run(ref.get)

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Invoice not found")

    invoice = Invoice(**doc.to_dict())

    if invoice.sender_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    if invoice.status != "draft":
        raise HTTPException(
            status_code=400,
            detail="Cannot edit published or paid invoice",
        )

    draft_data = payload.dict()
    draft_data["client_phone"] = normalize_phone(draft_data.get("client_phone"))

    await firestore_run(
        ref.update,
        {
            "draft_data": draft_data,
            "updated_at": datetime.now(timezone.utc),
        },
    )

    updated_doc = await firestore_run(ref.get)
    return Invoice(**updated_doc.to_dict())


# ----------------------------
# 3. PUBLISH INVOICE
# ----------------------------
@router.post("/{invoice_id}/publish", response_model=Invoice)
async def publish_invoice(
    invoice_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_silver),
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    draft_ref = db.collection("invoices").document(invoice_id)
    draft_doc = await firestore_run(draft_ref.get)

    if not draft_doc.exists:
        raise HTTPException(status_code=404, detail="Invoice not found")

    invoice = Invoice(**draft_doc.to_dict())

    if invoice.sender_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    if invoice.status != "draft":
        raise HTTPException(status_code=400, detail="Invoice already published")

    data = invoice.draft_data or {
        "amount": invoice.amount,
        "currency": invoice.currency,
        "client_email": invoice.client_email,
        "client_phone": invoice.client_phone,
        "description": invoice.description,
        "due_date": invoice.due_date,
        "client_name": getattr(invoice, "client_name", None),
    }

    if not data.get("amount") or not data.get("currency"):
        raise HTTPException(status_code=400, detail="Incomplete invoice data")

    short_id = invoice_id.split("_")[-1]
    published_id = f"inv_{short_id}"

    # Normalize phone before Paystack
    normalized_phone = normalize_phone(data.get("client_phone"))

    paystack_payload = {
        "amount": int(float(data["amount"]) * 100),
        "email": data.get("client_email") or "client@payla.vip",
        "currency": data["currency"],
        "reference": published_id,
        "callback_url": f"{settings.FRONTEND_URL}/i/{short_id}/paid",
        "metadata": {
            "invoice_id": published_id,
            "user_id": current_user.id,
            "type": "invoice",
            "client_phone": normalized_phone,
        },
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://api.paystack.co/transaction/initialize",
            json=paystack_payload,
            headers={
                "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
                "Content-Type": "application/json",
            },
        )

    if resp.status_code != 200 or not resp.json().get("status"):
        raise HTTPException(status_code=400, detail="Paystack initialization failed")

    paystack_data = resp.json()["data"]

    published_invoice = invoice.dict(by_alias=True)
    published_invoice.update({
        "_id": published_id,
        "amount": data["amount"],
        "currency": data["currency"],
        "description": data.get("description"),
        "due_date": data.get("due_date"),
        "status": "pending",
        "client_email": data.get("client_email"),
        "client_phone": normalized_phone,  # Use normalized phone
        "client_name": data.get("client_name"),
        "invoice_url": f"/i/{short_id}",
        "payment_url": paystack_data["authorization_url"],
        "paystack_reference": paystack_data["reference"],
        "published_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    published_invoice.pop("draft_data", None)

    await firestore_run(
        db.collection("invoices").document(published_id).set,
        published_invoice,
    )

    # Schedule reminders with normalized phone
    if normalized_phone or data.get("client_email"):
        background_tasks.add_task(
            schedule_reminders_for_invoice,
            invoice_id=published_id,
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

    updated_doc = await firestore_run(
        db.collection("invoices").document(published_id).get
    )

    return Invoice(**updated_doc.to_dict())


# --------------------------------------------------------------
# 4. GET USER'S INVOICES
# --------------------------------------------------------------
@router.get("/", response_model=List[Invoice])
async def get_my_invoices(current_user=Depends(get_current_user)):
    now = datetime.now(timezone.utc)

    docs = await firestore_run(
        db.collection("invoices")
        .where("sender_id", "==", current_user.id)
        .stream
    )

    invoices = []

    for doc in docs:
        inv = Invoice(**doc.to_dict())

        if inv.due_date and inv.due_date.tzinfo is None:
            inv.due_date = inv.due_date.replace(tzinfo=timezone.utc)

        if inv.status == "pending" and inv.due_date and inv.due_date < now:
            await firestore_run(
                db.collection("invoices")
                .document(inv._id)
                .update,
                {"status": "overdue", "updated_at": now},
            )
            inv.status = "overdue"

        invoices.append(inv)

    return invoices


# --------------------------------------------------------------
# 5. GET SINGLE INVOICE
# --------------------------------------------------------------
@router.get("/{invoice_id}", response_model=dict)
async def get_invoice(invoice_id: str):
    ref = db.collection("invoices").document(invoice_id)
    doc = await firestore_run(ref.get)

    if not doc.exists:
        raise HTTPException(404, "Invoice not found")

    invoice = Invoice(**doc.to_dict())
    now = datetime.now(timezone.utc)

    if invoice.due_date and invoice.due_date.tzinfo is None:
        invoice.due_date = invoice.due_date.replace(tzinfo=timezone.utc)

    if invoice.status == "pending" and invoice.due_date and invoice.due_date < now:
        await firestore_run(
            ref.update,
            {"status": "overdue", "updated_at": now},
        )
        invoice.status = "overdue"

    response = invoice.dict(by_alias=True)

    user_doc = await firestore_run(
        db.collection("users")
        .document(invoice.sender_id)
        .get
    )

    if user_doc.exists:
        user = User(**user_doc.to_dict())
        response.update({
            "sender_username": user.username,
            "sender_logo": user.custom_invoice_colors.get("logo")
            if user.custom_invoice_colors else None,
            "sender_email": user.email,
        })

    response["message"] = {
        "paid": "This invoice has been paid. Thank you!",
        "overdue": "This invoice is overdue.",
        "failed": "Payment failed. Please try again.",
        "draft": "This is a draft. Publish to send.",
    }.get(invoice.status)

    if invoice.status == "paid":
        response["payment_url"] = None

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
    doc = await firestore_run(ref.get())
    if not doc.exists:
        raise HTTPException(404, "Invoice not found")

    now = datetime.now(timezone.utc)
    update_data = {"status": status, "updated_at": now}
    if status == "paid":
        update_data["paid_at"] = now
        invoice_data = doc.to_dict()
        amount = invoice_data.get("amount", 0)
        payout_status = invoice_data.get("payout_status")
        if payout_status != "queued":
            asyncio.create_task(initiate_payout(invoice_data["sender_id"], amount, invoice_id))
            update_data["payout_status"] = "queued"

    await firestore_run(ref.update, update_data)
    return {"message": f"Invoice {invoice_id} → {status}"}


# --------------------------------------------------------------
# 7. DELETE INVOICE
# --------------------------------------------------------------
@router.delete("/{invoice_id}", response_model=dict)
async def delete_invoice(invoice_id: str, current_user: User = Depends(get_current_user)):
    ref = db.collection("invoices").document(invoice_id)
    doc = await firestore_run(ref.get)
    if not doc.exists:
        raise HTTPException(404, "Invoice not found")

    invoice = Invoice(**doc.to_dict())
    if invoice.sender_id != current_user.id:
        raise HTTPException(403, "Not authorized to delete this invoice")

    await firestore_run(ref.delete)
    return {"success": True, "message": "Invoice deleted successfully"}