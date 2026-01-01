import asyncio
from app.utils.firebase import firestore_run
from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from typing import List, Literal
from uuid import uuid4
from datetime import datetime, timezone
import httpx
from google.cloud import firestore
from pydantic import BaseModel
from app.models.invoice_model import InvoiceCreate, Invoice
from app.core.firebase import db
from app.models.user_model import User
from app.core.auth import get_current_user
from app.core.config import settings
# In your router file, update the imports:
from app.services.reminder_service import (
    schedule_reminders_for_invoice, 
    send_returning_client_notification # We will add this
)
from app.core.notifications import create_notification
from app.core.subscription import require_silver
#from app.tasks.payout import initiate_payout
from app.utils.crm import sync_client_to_crm
from google.cloud.firestore_v1.base_query import FieldFilter
router = APIRouter(prefix="/invoices", tags=["Invoices"])

class TempReminderPayload:
    preset: str = "standard"
    manual_dates: List[str] | None = None
    method_priority: List[str] = ["whatsapp", "sms", "email"]
    custom_message: str = ""  # Added to support the Reminder model's expectations

class StatusUpdate(BaseModel):
    status: str
    transaction_reference: str | None = None
    payer_email: str | None = None


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
        invoice_url=f"{settings.BACKEND_URL}/i/{short_id}",
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

    # 1. Check for Existing Relationship (Strict First Contact Logic)
    is_returning_client = False
    client_email = data.get("client_email")
    normalized_phone = normalize_phone(data.get("client_phone"))

    existing_base_query = db.collection("invoices").where(
        filter=FieldFilter("sender_id", "==", current_user.id)
    ).where(
        filter=FieldFilter("status", "in", ["pending", "paid", "overdue", "sent"])
    )

    if client_email:
        email_check = await firestore_run(
            existing_base_query.where(filter=FieldFilter("client_email", "==", client_email)).limit(1).get
        )
        if email_check:
            is_returning_client = True

    if not is_returning_client and normalized_phone:
        phone_check = await firestore_run(
            existing_base_query.where(filter=FieldFilter("client_phone", "==", normalized_phone)).limit(1).get
        )
        if phone_check:
            is_returning_client = True

    # 2. Initialize Paystack
    short_id = invoice_id.split("_")[-1]
    published_id = f"inv_{short_id}"

    paystack_payload = {
        "amount": int(float(data["amount"]) * 100),
        "email": client_email or "client@payla.vip",
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

    # --- NEW: SUBACCOUNT ROUTING ---
    # If the user has a subaccount, route the payment there automatically
    subaccount_code = getattr(current_user, "paystack_subaccount_code", None)
    if subaccount_code:
        paystack_payload["subaccount"] = subaccount_code
        # 'subaccount' means the creator (subaccount) bears the Paystack transaction fees
        paystack_payload["bearer"] = "subaccount"

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
        logger.error(f"Paystack Init Failed: {resp.text}")
        raise HTTPException(status_code=400, detail="Paystack initialization failed")

    paystack_data = resp.json()["data"]

    # 3. Save Published Invoice
    published_invoice = invoice.dict(by_alias=True)
    published_invoice.update({
        "_id": published_id,
        "amount": data["amount"],
        "currency": data["currency"],
        "description": data.get("description"),
        "due_date": data.get("due_date"),
        "status": "pending",
        "client_email": client_email,
        "client_phone": normalized_phone,
        "client_name": data.get("client_name"),
        "invoice_url": f"{settings.BACKEND_URL}/i/{short_id}",
        "payment_url": paystack_data["authorization_url"],
        "paystack_reference": paystack_data["reference"],
        "paystack_subaccount_code": subaccount_code, # Track which subaccount this was sent to
        "published_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "is_returning_client": is_returning_client 
    })

    published_invoice.pop("draft_data", None)

    await firestore_run(
        db.collection("invoices").document(published_id).set,
        published_invoice,
    )

    # 4. Handle Notifications
    if normalized_phone or client_email:
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
        .where(filter=FieldFilter("sender_id", "==", current_user.id))
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
            "sender_subaccount_code": getattr(user, "paystack_subaccount_code", None)
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
# 6. UPDATE STATUS (Verified & Secure)
# --------------------------------------------------------------
@router.patch("/{invoice_id}/status")
async def update_invoice_status(
    invoice_id: str,
    payload: StatusUpdate,
    background_tasks: BackgroundTasks # Added this
):
    # 1. Basic validation
    if payload.status != "paid":
        raise HTTPException(400, "Only 'paid' status updates are supported")
    
    if not payload.transaction_reference:
        raise HTTPException(400, "Transaction reference is required")

    # 2. Fetch Invoice
    ref = db.collection("invoices").document(invoice_id)
    doc = await firestore_run(ref.get)
    
    if not doc.exists:
        raise HTTPException(404, "Invoice not found")

    invoice_data = doc.to_dict()
    
    # 3. Race condition safety
    if invoice_data.get("status") == "paid":
        return {"message": "Invoice already processed", "status": "already_paid"}

    # 4. Paystack Verification
    async with httpx.AsyncClient(timeout=10) as client:
        verify_resp = await client.get(
            f"https://api.paystack.co/transaction/verify/{payload.transaction_reference}",
            headers={"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
        )
        
        if verify_resp.status_code != 200:
            raise HTTPException(400, "Could not verify payment with gateway")
            
        v_data = verify_resp.json()
        if not v_data.get("status") or v_data["data"]["status"] != "success":
            raise HTTPException(400, "Payment was not successful on Paystack")

        # Verify amount (Paystack returns in Kobo)
        paid_amount = v_data["data"]["amount"] / 100
        if paid_amount < float(invoice_data["amount"]):
            raise HTTPException(400, "Amount paid is less than invoice amount")

    # 5. Handle Payer Email (Fallback to Paystack's verified email)
    final_payer_email = (payload.payer_email or v_data["data"]["customer"]["email"]).lower()

    # 6. Prepare Update Data
    now = datetime.now(timezone.utc)
    update_data = {
        "status": "paid",
        "updated_at": now,
        "paid_at": now,
        "transaction_reference": payload.transaction_reference,
        "payer_email": final_payer_email
    }

    # 7. CRM Sync (Use the corrected variable name: invoice_data)
    # We await this to ensure marketing data is saved before response
    await sync_client_to_crm(
        merchant_id=invoice_data["sender_id"],
        email=final_payer_email,
        amount=float(invoice_data["amount"])
    )

    # 8. Trigger Payout (Background)
    amount = invoice_data.get("amount", 0)
    if invoice_data.get("payout_status") != "queued":
        background_tasks.add_task(initiate_payout, invoice_data["sender_id"], amount, invoice_id)
        update_data["payout_status"] = "queued"

    # 9. Save Update
    await firestore_run(ref.update, update_data)

    # 10. Notifications
    create_notification(
        user_id=invoice_data["sender_id"],
        title="Payment Received",
        message=f"Invoice {invoice_id} has been paid (₦{amount:,}).",
        type="success",
        link="/dashboard"
    )

    # 11. Customer Thank You & Receipt
    if invoice_data.get("client_phone") or invoice_data.get("client_email") or final_payer_email:
        sender_doc = await firestore_run(db.collection("users").document(invoice_data["sender_id"]).get)
        sender_user = sender_doc.to_dict() if sender_doc.exists else {}
        
        # We ensure the invoice_data reflects the 'paid' status for the notification
        invoice_data.update(update_data) 

        background_tasks.add_task(
            send_payment_success_notification,
            user=sender_user, 
            invoice=invoice_data
        )

    return {"message": "Success", "status": "paid"}

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