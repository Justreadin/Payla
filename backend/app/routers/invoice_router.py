import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from typing import Any, List
from uuid import uuid4

import httpx
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    status,
)
from google.cloud.firestore_v1.base_query import FieldFilter
from pydantic import BaseModel, EmailStr, Field

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.firebase import db
from app.core.notifications import create_notification
from app.core.subscription import require_silver
from app.models.invoice_model import (
    Invoice,
    InvoiceCreate,
    PaymentInitializationRequest,
    StatusUpdate,
    TempReminderPayload,
)
from app.models.user_model import User
from app.services.reminder_service import schedule_reminders_for_invoice
from app.utils.firebase import firestore_run


logger = logging.getLogger("payla")
router = APIRouter(prefix="/invoices", tags=["Invoices"])


# ============================================================
# GENERAL HELPERS
# ============================================================

def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_phone(raw: str | None) -> str:
    """Normalize common Nigerian and international phone formats."""
    if not raw:
        return ""

    num = "".join(filter(str.isdigit, raw))

    if not num:
        return ""

    if raw.strip().startswith("+"):
        return f"+{num}"

    if num.startswith("234") and len(num) == 13:
        return f"+{num}"

    if num.startswith("91") and len(num) == 12:
        return f"+{num}"

    if num.startswith("1") and len(num) == 11:
        return f"+{num}"

    if num.startswith("0") and len(num) == 11:
        return f"+234{num[1:]}"

    if len(num) == 10:
        return f"+234{num}"

    return f"+{num}"


def _normalize_fee_payer(value: Any) -> str:
    """Normalize legacy and canonical fee-payer values."""
    return "client" if value == "client" else "merchant"


def _get_default_invoice_fee_payer(user_id: str) -> str:
    snapshot = db.collection("users").document(user_id).get()
    data = snapshot.to_dict() if snapshot.exists else {}

    return _normalize_fee_payer(
        (data or {}).get("default_invoice_fee_payer", "merchant")
    )


def _naira_to_kobo(value: Any) -> int:
    """Convert a naira amount to integer kobo without rounding."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Invalid naira amount")

    if not amount.is_finite() or amount <= 0:
        raise ValueError("Amount must be positive and finite")

    kobo = amount * Decimal("100")

    if kobo != kobo.to_integral_value():
        raise ValueError("Amount cannot have more than two decimal places")

    return int(kobo)


def _invoice_document_id(invoice_id: str) -> str:
    """Resolve public short IDs and canonical invoice IDs."""
    if invoice_id.startswith("inv_"):
        return invoice_id
    return f"inv_{invoice_id}"


def _short_invoice_id(invoice_id: str) -> str:
    return invoice_id.removeprefix("inv_")


def _serialize_invoice(doc) -> Invoice:
    data = doc.to_dict() or {}
    data.setdefault("_id", doc.id)
    return Invoice(**data)


def _estimated_paystack_fee_kobo(gross_kobo: int) -> int:
    """Estimate the standard local NGN transaction fee in kobo."""
    if gross_kobo <= 0:
        raise ValueError("Payment amount must be positive")

    percentage_fee = int(
        (Decimal(gross_kobo) * Decimal("0.015"))
        .to_integral_value(rounding=ROUND_CEILING)
    )

    fixed_fee = 10_000 if gross_kobo >= 250_000 else 0

    return min(percentage_fee + fixed_fee, 200_000)


def _client_fee_gross_up_kobo(
    invoice_kobo: int,
) -> tuple[int, int]:
    """
    Find the smallest gross charge whose estimated net proceeds
    cover the invoice amount.

    Returns (gross_charge_kobo, estimated_fee_kobo).
    """
    if invoice_kobo <= 0:
        raise ValueError("Invoice amount must be positive")

    low = invoice_kobo
    high = invoice_kobo + 210_000

    while high - _estimated_paystack_fee_kobo(high) < invoice_kobo:
        high *= 2

    while low < high:
        mid = (low + high) // 2

        if mid - _estimated_paystack_fee_kobo(mid) >= invoice_kobo:
            high = mid
        else:
            low = mid + 1

    gross_kobo = low
    fee_kobo = _estimated_paystack_fee_kobo(gross_kobo)

    return gross_kobo, fee_kobo


# ============================================================
# 1. CREATE DRAFT INVOICE
# ============================================================

@router.post(
    "/",
    response_model=Invoice,
    status_code=status.HTTP_201_CREATED,
)
async def create_invoice_draft(
    payload: InvoiceCreate,
    current_user: User = Depends(require_silver),
):
    short_id = f"{current_user.username}{str(uuid4())[:8]}"
    invoice_id = f"draft_{short_id}"

    draft_data = payload.dict()

    fee_payer = _normalize_fee_payer(
        draft_data.get("fee_payer")
        or _get_default_invoice_fee_payer(current_user.id)
    )
    draft_data["fee_payer"] = fee_payer
    draft_data["client_phone"] = normalize_phone(
        draft_data.get("client_phone")
    )

    now = _now()

    invoice = Invoice(
        _id=invoice_id,
        sender_id=current_user.id,
        sender_business_name=(
            current_user.business_name or current_user.full_name
        ),
        sender_phone=current_user.phone_number or "",
        amount=payload.amount,
        currency=payload.currency,
        description=payload.description,
        due_date=payload.due_date,
        client_phone=draft_data["client_phone"],
        client_email=payload.client_email,
        status="draft",
        draft_data=draft_data,
        fee_payer=fee_payer,
        invoice_url=f"{settings.BACKEND_URL}/i/{short_id}",
        created_at=now,
        updated_at=now,
    )

    await firestore_run(
        db.collection("invoices").document(invoice_id).set,
        invoice.dict(by_alias=True),
    )

    return invoice


# ============================================================
# 2. UPDATE DRAFT INVOICE
# ============================================================

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

    invoice = _serialize_invoice(doc)

    if invoice.sender_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    if invoice.status != "draft":
        raise HTTPException(
            status_code=400,
            detail="Cannot edit a published invoice",
        )

    draft_data = payload.dict()
    draft_data["client_phone"] = normalize_phone(
        draft_data.get("client_phone")
    )

    existing_draft = invoice.draft_data or {}

    # None means inherit the current account preference.
    if payload.fee_payer is None:
        fee_payer = _get_default_invoice_fee_payer(current_user.id)
    else:
        fee_payer = _normalize_fee_payer(payload.fee_payer)

    draft_data["fee_payer"] = fee_payer

    now = _now()

    await firestore_run(
        ref.update,
        {
            "amount": payload.amount,
            "currency": payload.currency,
            "description": payload.description,
            "due_date": payload.due_date,
            "client_phone": draft_data["client_phone"],
            "client_email": payload.client_email,
            "draft_data": draft_data,
            "fee_payer": fee_payer,
            "updated_at": now,
        },
    )

    updated_doc = await firestore_run(ref.get)
    return _serialize_invoice(updated_doc)


# ============================================================
# 3. PUBLISH INVOICE
# Publishing does NOT initialize Paystack.
# ============================================================

@router.post("/{invoice_id}/publish", response_model=Invoice)
async def publish_invoice(
    invoice_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_silver),
):
    draft_ref = db.collection("invoices").document(invoice_id)
    draft_doc = await firestore_run(draft_ref.get)

    if not draft_doc.exists:
        raise HTTPException(status_code=404, detail="Invoice not found")

    invoice = _serialize_invoice(draft_doc)

    if invoice.sender_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    if invoice.status != "draft":
        raise HTTPException(
            status_code=400,
            detail="Invoice already published",
        )

    data = invoice.draft_data or {
        "amount": invoice.amount,
        "currency": invoice.currency,
        "client_email": invoice.client_email,
        "client_phone": invoice.client_phone,
        "description": invoice.description,
        "due_date": invoice.due_date,
        "client_name": getattr(invoice, "client_name", None),
        "fee_payer": invoice.fee_payer,
    }

    try:
        _naira_to_kobo(data.get("amount"))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid invoice amount",
        ) from exc

    currency = str(data.get("currency") or "").upper()
    if currency != "NGN":
        raise HTTPException(
            status_code=400,
            detail="Only NGN invoices are supported",
        )

    fee_payer = _normalize_fee_payer(
        data.get("fee_payer")
        or invoice.fee_payer
        or _get_default_invoice_fee_payer(current_user.id)
    )

    client_email = data.get("client_email")
    normalized_phone = normalize_phone(data.get("client_phone"))

    # Returning-client detection.
    is_returning_client = False

    existing_base_query = (
        db.collection("invoices")
        .where(
            filter=FieldFilter("sender_id", "==", current_user.id)
        )
        .where(
            filter=FieldFilter(
                "status",
                "in",
                ["pending", "paid", "overdue", "sent"],
            )
        )
    )

    if client_email:
        email_results = await firestore_run(
            existing_base_query
            .where(
                filter=FieldFilter("client_email", "==", client_email)
            )
            .limit(1)
            .get
        )
        is_returning_client = bool(email_results)

    if not is_returning_client and normalized_phone:
        phone_results = await firestore_run(
            existing_base_query
            .where(
                filter=FieldFilter(
                    "client_phone", "==", normalized_phone
                )
            )
            .limit(1)
            .get
        )
        is_returning_client = bool(phone_results)

    short_id = invoice_id.removeprefix("draft_")
    published_id = f"inv_{short_id}"
    now = _now()

    published_invoice = invoice.dict(by_alias=True)
    published_invoice.update({
        "_id": published_id,
        "amount": data["amount"],
        "currency": currency,
        "description": data.get("description"),
        "due_date": data.get("due_date"),
        "status": "pending",
        "client_email": client_email,
        "client_phone": normalized_phone,
        "client_name": data.get("client_name"),
        "invoice_url": f"{settings.BACKEND_URL}/i/{short_id}",
        "payment_url": None,
        "paystack_reference": None,
        "paystack_subaccount_code": getattr(
            current_user, "paystack_subaccount_code", None
        ),
        "sender_subaccount_code": getattr(
            current_user, "paystack_subaccount_code", None
        ),
        "fee_payer": fee_payer,
        "expected_charge_kobo": None,
        "published_at": now,
        "updated_at": now,
        "is_returning_client": is_returning_client,
    })

    published_invoice.pop("draft_data", None)

    # Do not overwrite an existing published invoice.
    published_ref = db.collection("invoices").document(published_id)

    try:
        await firestore_run(
            published_ref.create,
            published_invoice,
        )
    except Exception:
        logger.exception(
            "Could not create published invoice %s",
            published_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Could not publish invoice",
        )

    # Preserve reminders.
    if normalized_phone or client_email:
        background_tasks.add_task(
            schedule_reminders_for_invoice,
            invoice_id=published_id,
            payload=TempReminderPayload(),
            user_id=current_user.id,
        )

    # Preserve the existing notification behaviour.
    try:
        create_notification(
            user_id=current_user.id,
            title="Invoice Sent",
            message=f"Invoice of ₦{float(data['amount']):,.2f} sent",
            type="success",
            link="/dashboard/invoice",
        )
    except Exception:
        logger.exception(
            "Invoice %s was published, but notification creation failed",
            published_id,
        )

    published_doc = await firestore_run(published_ref.get)
    return _serialize_invoice(published_doc)


# ============================================================
# 4. INITIALIZE INVOICE CHECKOUT
# ============================================================

@router.post(
    "/{invoice_id}/initialize-payment",
    status_code=status.HTTP_200_OK,
)
async def initialize_invoice_payment(
    invoice_id: str,
    payload: PaymentInitializationRequest,
):
    canonical_id = _invoice_document_id(invoice_id)
    short_id = _short_invoice_id(canonical_id)

    invoice_ref = db.collection("invoices").document(canonical_id)
    invoice_snapshot = await firestore_run(invoice_ref.get)

    if not invoice_snapshot.exists:
        raise HTTPException(
            status_code=404,
            detail="Invoice not found",
        )

    invoice = invoice_snapshot.to_dict() or {}

    if invoice.get("status") != "pending":
        raise HTTPException(
            status_code=400,
            detail="This invoice is not available for payment",
        )

    # Check the invoice due date.
    if invoice.get("due_date"):
        due_date = invoice["due_date"]

        if due_date.tzinfo is None:
            due_date = due_date.replace(tzinfo=timezone.utc)

        if due_date < _now():
            await firestore_run(
                invoice_ref.update,
                {
                    "status": "overdue",
                    "updated_at": _now(),
                },
            )

            raise HTTPException(
                status_code=400,
                detail="This invoice is overdue",
            )

    fee_payer = _normalize_fee_payer(
        invoice.get("fee_payer")
    )

    client_fees_enabled = settings.PAYSTACK_CLIENT_INVOICE_FEES_ENABLED

    if fee_payer == "client" and not client_fees_enabled:
        raise HTTPException(
            status_code=409,
            detail=(
                "Client-paid fees are temporarily unavailable. "
                "Please contact the invoice sender."
            ),
        )

    user_id = invoice.get("sender_id")

    if not user_id:
        raise HTTPException(
            status_code=400,
            detail="Invoice merchant information is missing",
        )

    # The invoice amount is the merchant's intended amount.
    try:
        merchant_amount_kobo = _naira_to_kobo(
            invoice.get("amount")
        )
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid invoice amount",
        ) from exc

    if merchant_amount_kobo <= 0:
        raise HTTPException(
            status_code=400,
            detail="Invoice amount must be greater than zero",
        )

    # Determine the gross amount Paystack should charge.
    #
    # Merchant pays:
    #   Gross charge = invoice amount
    #
    # Client pays:
    #   Gross charge = invoice amount + estimated transaction fee
    estimated_fee_kobo = 0

    if fee_payer == "client":
        try:
            (
                expected_charge_kobo,
                estimated_fee_kobo,
            ) = _client_fee_gross_up_kobo(
                merchant_amount_kobo
            )
        except (ValueError, ArithmeticError) as exc:
            logger.exception(
                "Could not calculate invoice payment gross-up: %s",
                canonical_id,
            )
            raise HTTPException(
                status_code=400,
                detail=(
                    "Could not calculate the payment amount. "
                    "Please contact the invoice sender."
                ),
            ) from exc
    else:
        expected_charge_kobo = merchant_amount_kobo

    # Reuse an existing initialized attempt only if it belongs to
    # the same invoice configuration and amount.
    previous_reference = invoice.get("paystack_reference")

    if previous_reference:
        previous_attempt_ref = (
            db.collection("invoice_payment_attempts")
            .document(previous_reference)
        )

        previous_attempt = await firestore_run(
            previous_attempt_ref.get
        )

        if previous_attempt.exists:
            previous_data = previous_attempt.to_dict() or {}

            previous_status = previous_data.get("status")

            if previous_status == "initializing":
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "A payment initialization is already "
                        "in progress"
                    ),
                )

            if (
                previous_status == "initialized"
                and previous_data.get("authorization_url")
            ):
                same_configuration = (
                    previous_data.get("invoice_id") == canonical_id
                    and previous_data.get("user_id") == user_id
                    and _normalize_fee_payer(
                        previous_data.get("fee_payer")
                    ) == fee_payer
                    and previous_data.get("merchant_amount_kobo")
                    == merchant_amount_kobo
                    and previous_data.get("expected_charge_kobo")
                    == expected_charge_kobo
                )

                if same_configuration:
                    return {
                        "status": "success",
                        "reference": previous_reference,
                        "authorization_url": (
                            previous_data["authorization_url"]
                        ),
                        "access_code": previous_data.get(
                            "access_code"
                        ),
                    }

                # Do not silently reuse a checkout URL with a
                # different amount or fee-payer configuration.
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "An existing payment attempt must be "
                        "resolved before a new checkout can be created"
                    ),
                )

    # Create a new payment attempt.
    reference = f"invpay_{uuid4().hex}"
    now = _now()

    attempt_ref = (
        db.collection("invoice_payment_attempts")
        .document(reference)
    )

    attempt_data = {
        "reference": reference,
        "invoice_id": canonical_id,
        "user_id": user_id,

        # Actual requested charge and merchant's invoice amount
        # are deliberately stored separately.
        "expected_charge_kobo": expected_charge_kobo,
        "merchant_amount_kobo": merchant_amount_kobo,

        "estimated_fee_kobo": estimated_fee_kobo,
        "fee_payer": fee_payer,
        "currency": "NGN",
        "status": "initializing",
        "payer_email": str(payload.payer_email),
        "created_at": now,
        "updated_at": now,
    }

    await firestore_run(
        attempt_ref.create,
        attempt_data,
    )

    try:
        user_snapshot = await firestore_run(
            db.collection("users").document(user_id).get
        )

        user_data = (
            user_snapshot.to_dict()
            if user_snapshot.exists
            else {}
        ) or {}

        subaccount_code = (
            invoice.get("paystack_subaccount_code")
            or user_data.get("paystack_subaccount_code")
        )

        paystack_payload = {
            "email": str(payload.payer_email),
            "amount": expected_charge_kobo,
            "currency": "NGN",
            "reference": reference,
            "callback_url": (
                f"{str(settings.FRONTEND_URL).rstrip('/')}"
                f"/invoice_receipt.html"
                f"?invoice_id={short_id}&reference={reference}"
            ),
            "metadata": {
                "invoice_id": canonical_id,
                "user_id": user_id,
                "type": "invoice",
                "payer_email": str(payload.payer_email),
                "payer_phone": invoice.get("client_phone"),

                # Observability only. The webhook should use the
                # persisted attempt record as its source of truth.
                "fee_payer": fee_payer,
                "invoice_amount_kobo": merchant_amount_kobo,
            },
        }

        if subaccount_code:
            paystack_payload["subaccount"] = subaccount_code
            paystack_payload["bearer"] = "subaccount"

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                "https://api.paystack.co/transaction/initialize",
                headers={
                    "Authorization": (
                        f"Bearer {settings.PAYSTACK_SECRET_KEY}"
                    ),
                    "Content-Type": "application/json",
                },
                json=paystack_payload,
            )

        try:
            response_data = response.json()
        except ValueError:
            response_data = {}

        checkout = response_data.get("data") or {}

        logger.error(
            "Paystack initialization rejected: reference=%s "
            "http_status=%s response=%s",
            reference,
            response.status_code,
            response_data,
        )

        if (
            response.status_code >= 400
            or not response_data.get("status")
            or not checkout.get("authorization_url")
        ):
            await firestore_run(
                attempt_ref.update,
                {
                    "status": "failed",
                    "failure_reason": (
                        "paystack_initialization_failed"
                    ),
                    "updated_at": _now(),
                },
            )

            raise HTTPException(
                status_code=502,
                detail="Could not initialize payment",
            )

        # Save the checkout details on the attempt first.
        await firestore_run(
            attempt_ref.update,
            {
                "status": "initialized",
                "authorization_url": checkout["authorization_url"],
                "access_code": checkout.get("access_code"),
                "updated_at": _now(),
            },
        )

        # Keep the canonical invoice amount unchanged.
        # expected_charge_kobo reflects the requested Paystack charge.
        await firestore_run(
            invoice_ref.update,
            {
                "payment_url": checkout["authorization_url"],
                "paystack_reference": reference,
                "expected_charge_kobo": expected_charge_kobo,
                "merchant_amount_kobo": merchant_amount_kobo,
                "updated_at": _now(),
            },
        )

        logger.info(
            (
                "Invoice checkout initialized: reference=%s "
                "fee_payer=%s invoice_kobo=%s charge_kobo=%s "
                "estimated_fee_kobo=%s"
            ),
            reference,
            fee_payer,
            merchant_amount_kobo,
            expected_charge_kobo,
            estimated_fee_kobo,
        )

        return {
            "status": "success",
            "reference": reference,
            "authorization_url": checkout["authorization_url"],
            "access_code": checkout.get("access_code"),
        }

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception(
            "Invoice payment initialization failed: %s",
            reference,
        )

        try:
            await firestore_run(
                attempt_ref.update,
                {
                    "status": "failed",
                    "failure_reason": "initialization_error",
                    "updated_at": _now(),
                },
            )
        except Exception:
            logger.exception(
                "Could not update failed attempt %s",
                reference,
            )

        raise HTTPException(
            status_code=502,
            detail="Could not initialize payment",
        ) from exc


# ============================================================
# 5. GET USER INVOICES
# ============================================================

@router.get("/", response_model=List[Invoice])
async def get_my_invoices(
    current_user: User = Depends(get_current_user),
):
    now = _now()

    docs = await firestore_run(
        db.collection("invoices")
        .where(filter=FieldFilter("sender_id", "==", current_user.id))
        .stream
    )

    invoices = []

    for doc in docs:
        data = doc.to_dict() or {}
        data.setdefault("_id", doc.id)
        inv = Invoice(**data)

        due_date = inv.due_date
        if due_date and due_date.tzinfo is None:
            due_date = due_date.replace(tzinfo=timezone.utc)

        if inv.status == "pending" and due_date and due_date < now:
            await firestore_run(
                db.collection("invoices").document(doc.id).update,
                {"status": "overdue", "updated_at": now},
            )
            inv.status = "overdue"

        invoices.append(inv)

    return invoices


# ============================================================
# 6. GET PUBLIC INVOICE
# ============================================================

@router.get("/{invoice_id}", response_model=dict)
async def get_invoice(invoice_id: str):
    actual_id = _invoice_document_id(invoice_id)
    ref = db.collection("invoices").document(actual_id)
    doc = await firestore_run(ref.get)

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Invoice not found")

    invoice_data = doc.to_dict() or {}
    now = _now()

    due_date = invoice_data.get("due_date")
    if due_date and due_date.tzinfo is None:
        due_date = due_date.replace(tzinfo=timezone.utc)

    if (
        invoice_data.get("status") == "pending"
        and due_date
        and due_date < now
    ):
        await firestore_run(
            ref.update,
            {"status": "overdue", "updated_at": now},
        )
        invoice_data["status"] = "overdue"

    sender_id = invoice_data.get("sender_id")
    if sender_id:
        user_doc = await firestore_run(
            db.collection("users").document(sender_id).get
        )

        if user_doc.exists:
            user_data = user_doc.to_dict() or {}
            custom_colors = user_data.get("custom_invoice_colors") or {}

            invoice_data.update({
                "sender_username": user_data.get("username"),
                "sender_logo": custom_colors.get("logo"),
                "sender_email": user_data.get("email"),
                "sender_subaccount_code": user_data.get(
                    "paystack_subaccount_code"
                ),
            })

    invoice_data["message"] = {
        "paid": "This invoice has been paid. Thank you!",
        "overdue": "This invoice is overdue.",
        "failed": "Payment failed. Please try again.",
        "draft": "This is a draft. Publish to send.",
    }.get(invoice_data.get("status"))

    if invoice_data.get("status") == "paid":
        invoice_data["payment_url"] = None

    return invoice_data


# ============================================================
# 7. VERIFY PAYMENT STATUS
# Webhook owns payment side effects and accounting.
# ============================================================

@router.patch("/{invoice_id}/status")
async def update_invoice_status(
    invoice_id: str,
    payload: StatusUpdate,
):
    if payload.status != "paid":
        raise HTTPException(
            status_code=400,
            detail="Only 'paid' status updates are supported",
        )

    reference = payload.transaction_reference
    if not reference:
        raise HTTPException(
            status_code=400,
            detail="Transaction reference is required",
        )

    canonical_id = _invoice_document_id(invoice_id)
    invoice_ref = db.collection("invoices").document(canonical_id)
    invoice_doc = await firestore_run(invoice_ref.get)

    if not invoice_doc.exists:
        raise HTTPException(status_code=404, detail="Invoice not found")

    invoice_data = invoice_doc.to_dict() or {}

    if invoice_data.get("status") == "paid":
        if (
            invoice_data.get("paystack_reference") == reference
            or invoice_data.get("transaction_reference") == reference
        ):
            return {
                "message": "Invoice already processed",
                "status": "already_paid",
            }

    # New-flow attempts must exist and belong to this exact invoice.
    attempt_ref = (
        db.collection("invoice_payment_attempts").document(reference)
    )
    attempt_doc = await firestore_run(attempt_ref.get)
    attempt_data = attempt_doc.to_dict() if attempt_doc.exists else None

    if attempt_data:
        if (
            attempt_data.get("invoice_id") != canonical_id
            or attempt_data.get("user_id") != invoice_data.get("sender_id")
        ):
            raise HTTPException(
                status_code=400,
                detail="Payment attempt does not belong to this invoice",
            )

        if attempt_data.get("status") == "failed":
            raise HTTPException(
                status_code=400,
                detail="This payment attempt failed to initialize",
            )

        expected_kobo = attempt_data.get("expected_charge_kobo")
    else:
        # Legacy reference compatibility.
        expected_reference = (
            invoice_data.get("paystack_reference")
            or invoice_data.get("transaction_reference")
        )

        if expected_reference != reference:
            raise HTTPException(
                status_code=400,
                detail="Transaction reference does not match this invoice",
            )

        try:
            expected_kobo = _naira_to_kobo(invoice_data.get("amount"))
        except ValueError as exc:
            raise HTTPException(
                status_code=500,
                detail="Invoice amount is invalid",
            ) from exc

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            verify_resp = await client.get(
                "https://api.paystack.co/transaction/verify/"
                f"{reference}",
                headers={
                    "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"
                },
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not reach Paystack to verify payment",
        ) from exc

    if verify_resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Could not verify payment with Paystack",
        )

    try:
        response_data = verify_resp.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail="Invalid verification response from Paystack",
        ) from exc

    if not response_data.get("status"):
        raise HTTPException(
            status_code=502,
            detail="Paystack could not verify this transaction",
        )

    payment_details = response_data.get("data") or {}

    if payment_details.get("status") != "success":
        raise HTTPException(
            status_code=400,
            detail="Payment was not successful on Paystack",
        )

    if payment_details.get("reference") != reference:
        raise HTTPException(
            status_code=400,
            detail="Verified transaction reference does not match",
        )

    metadata = payment_details.get("metadata") or {}

    if metadata.get("invoice_id") != canonical_id:
        raise HTTPException(
            status_code=400,
            detail="Transaction does not belong to this invoice",
        )

    if metadata.get("user_id") != invoice_data.get("sender_id"):
        raise HTTPException(
            status_code=400,
            detail="Transaction merchant does not match this invoice",
        )

    try:
        actual_kobo = int(payment_details["amount"])
        expected_kobo = int(expected_kobo)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=500,
            detail="Invoice or payment amount is invalid",
        ) from exc

    if actual_kobo != expected_kobo:
        raise HTTPException(
            status_code=400,
            detail="Payment amount does not match the payment attempt",
        )

    expected_currency = str(
        (attempt_data or {}).get(
            "currency",
            invoice_data.get("currency", "NGN"),
        )
    ).upper()

    actual_currency = str(
        payment_details.get("currency", "")
    ).upper()

    if actual_currency != expected_currency:
        raise HTTPException(
            status_code=400,
            detail="Payment currency does not match the invoice",
        )

    # The webhook is still responsible for marking paid, recording
    # merchant earnings, and creating payout history.
    latest_doc = await firestore_run(invoice_ref.get)
    latest_data = latest_doc.to_dict() or {}

    if latest_data.get("status") == "paid":
        return {
            "message": "Invoice payment confirmed",
            "status": "paid",
        }

    return {
        "message": "Payment verified; awaiting webhook processing",
        "status": latest_data.get("status", "pending"),
        "payment_verified": True,
        "reference": reference,
    }


# ============================================================
# 8. DELETE INVOICE
# ============================================================

@router.delete("/{invoice_id}", response_model=dict)
async def delete_invoice(
    invoice_id: str,
    current_user: User = Depends(get_current_user),
):
    ref = db.collection("invoices").document(invoice_id)
    doc = await firestore_run(ref.get)

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Invoice not found")

    invoice = _serialize_invoice(doc)

    if invoice.sender_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to delete this invoice",
        )

    if invoice.status == "paid":
        raise HTTPException(
            status_code=400,
            detail="A paid invoice cannot be deleted",
        )

    await firestore_run(ref.delete)

    return {
        "success": True,
        "message": "Invoice deleted successfully",
    }