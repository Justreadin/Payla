import logging
import math
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status, Request
from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.constants import (
    INAPPROPRIATE_WORDS,
    RESERVED_USERNAMES,
    USERNAME_PATTERN,
)
from app.core.firebase import db
from app.core.notifications import create_notification
from app.core.payla_urls import paylink_url
from app.core.analytics import (
    increment_daily_metric,
    increment_paylink_metric,
    log_paylink_event,
)
from app.core.paystack import create_permanent_payment_page
from app.models.paylink_model import (
    CreatePaylinkTransactionRequest,
    Paylink,
    PaylinkCreate,
)
from app.models.user_model import User

logger = logging.getLogger("payla")
router = APIRouter(prefix="/paylinks", tags=["Paylinks"])


# ─── PUBLIC PAYLINK FIELD WHITELIST ───
PUBLIC_PAYLINK_FIELDS = {
    "user_id",
    "username",
    "display_name",
    "description",
    "currency",
    "active",
    "link_url",
    "created_at",
    "bank_confirmation_status",
    # Derived at request time — not stored on the document.
    "silver_verified",
}

# ============================================================
# BOT / PREVIEW FILTER
# ============================================================
BOT_UA_FRAGMENTS = (
    "bot",
    "crawler",
    "spider",
    "preview",
    "whatsapp",
    "telegram",
    "slack",
    "discord",
    "facebookexternalhit",
    "twitterbot",
    "linkedinbot",
    "embedly",
    "quora link preview",
    "showyoubot",
    "outbrain",
    "pinterest",
    "vkShare",
    "W3C_Validator",
    "redditbot",
    "applebot",
    "skypeuripreview",
    "googlebot",
    "bingbot",
    "yandex",
    "duckduckbot",
    "baiduspider",
)


def _is_bot_request(request: Request) -> bool:
    """Return True when the request looks like a bot or link preview."""
    user_agent = (request.headers.get("user-agent") or "").strip().lower()

    if not user_agent:
        return True

    return any(fragment in user_agent for fragment in BOT_UA_FRAGMENTS)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_username(value: Any) -> str:
    if not isinstance(value, str):
        raise HTTPException(
            status_code=400,
            detail="Username must be a string",
        )

    username = value.strip().lower().lstrip("@")

    if not USERNAME_PATTERN.fullmatch(username):
        raise HTTPException(
            status_code=400,
            detail=(
                "Username must be 3-20 characters using letters, "
                "numbers, hyphens, or underscores"
            ),
        )

    if any(word in username for word in INAPPROPRIATE_WORDS):
        raise HTTPException(
            status_code=400,
            detail="Username contains inappropriate content",
        )

    return username


def _as_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}",
        )

    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}",
        ) from exc

    if not math.isfinite(result) or result <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must be greater than zero",
        )

    return round(result, 2)


def _paylink_ref(paylink_id: str):
    return db.collection("paylinks").document(paylink_id)


def _find_paylink_by_username(username: str):
    docs = (
        db.collection("paylinks")
        .where(filter=FieldFilter("username", "==", username))
        .limit(1)
        .get()
    )

    return docs[0] if docs else None


def _check_reserved_username(username: str) -> bool:
    return username in RESERVED_USERNAMES


def _project_public_paylink(data: dict) -> dict:
    """Strip a paylink document down to fields safe for the public route."""
    return {k: v for k, v in data.items() if k in PUBLIC_PAYLINK_FIELDS}


def _owner_has_silver(owner_data: dict) -> bool:
    """
    Evaluate whether the paylink owner currently has Silver entitlement.
    Never raises. Defaults to False on any failure.
    """
    if not owner_data:
        return False

    try:
        owner = User(**owner_data)
        return bool(owner.can_access_silver_features())
    except Exception:
        logger.exception("Silver check failed for paylink owner")
        return False


# --------------------------------------------------------------
# Helper: Ensure a permanent Paystack page exists
# --------------------------------------------------------------
async def ensure_paystack_page(paylink: dict) -> dict:
    if paylink.get("paystack_page_url") and paylink.get("paystack_reference"):
        return paylink

    username = paylink.get("username")
    display_name = paylink.get("display_name")
    user_id = paylink.get("user_id")
    paylink_id = paylink.get("_id") or user_id

    if not username or not user_id or not paylink_id:
        logger.warning("Cannot create Paystack page: incomplete Paylink record")
        return paylink

    try:
        user_snapshot = db.collection("users").document(user_id).get()

        if not user_snapshot.exists:
            logger.warning(
                "User %s not found while preparing Paylink",
                user_id,
            )
            return paylink

        user_data = user_snapshot.to_dict() or {}
        subaccount_code = (
            user_data.get("paystack_subaccount_code")
            or user_data.get("paystack_subaccount_id")
        )

        if not subaccount_code:
            logger.info(
                "Paystack page creation deferred for @%s: no subaccount",
                username,
            )
            return paylink

        page_data = await create_permanent_payment_page(
            username,
            display_name or user_data.get("business_name") or user_data.get("full_name") or username,
            subaccount_code,
        )

        page_url = page_data.get("url")
        page_reference = page_data.get("reference")

        if not page_url or not page_reference:
            logger.error(
                "Paystack returned an incomplete page response for @%s",
                username,
            )
            return paylink

        update_payload = {
            "paystack_page_url": page_url,
            "paystack_reference": page_reference,
            "paystack_subaccount_code": subaccount_code,
            "updated_at": _now(),
        }

        _paylink_ref(paylink_id).set(update_payload, merge=True)
        paylink.update(update_payload)

    except Exception:
        logger.exception(
            "Failed to prepare Paystack page for @%s",
            username,
        )

    return paylink


# --------------------------------------------------------------
# 1. CREATE OR UPDATE PAYLINK
# --------------------------------------------------------------
@router.post(
    "/",
    response_model=Paylink,
    status_code=status.HTTP_201_CREATED,
)
async def create_or_update_paylink(
    payload: PaylinkCreate,
    current_user=Depends(get_current_user),
):
    user = current_user
    username = _normalize_username(payload.username)

    if _check_reserved_username(username):
        raise HTTPException(
            status_code=400,
            detail="This username is reserved",
        )

    paylink_id = user.id
    doc_ref = _paylink_ref(paylink_id)

    existing_snapshot = doc_ref.get()
    existing_data = existing_snapshot.to_dict() or {}

    existing_domain = existing_data.get("preferred_domain", "ng")

    # The request may carry a preferred_domain when the user is
    # changing both username and domain in the same save. Silver
    # entitlement is re-checked here so a crafted request cannot
    # set .vip for a Free user.
    requested_domain = getattr(payload, "preferred_domain", None)

    if requested_domain == "vip":
        if not user.can_access_silver_features():
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "subscription_required",
                    "message": (
                        "The payla.vip domain is available on Payla Silver."
                    ),
                },
            )
        existing_domain = "vip"
    elif requested_domain == "ng":
        existing_domain = "ng"

    link_url = paylink_url(username, existing_domain)

    existing_username = _find_paylink_by_username(username)

    if existing_username and existing_username.id != paylink_id:
        raise HTTPException(
            status_code=409,
            detail="This username is already taken",
        )

    now = _now()

    paylink_data = Paylink(
        _id=paylink_id,
        user_id=paylink_id,
        username=username,
        display_name=(
            existing_data.get("display_name")
            or user.business_name
            or user.full_name
        ),
        description=(
            existing_data.get("description")
            or user.tagline
            or "Your Payment Identity"
        ),
        currency=payload.currency,
        active=existing_data.get("active", True),
        link_url=link_url,
        preferred_domain=existing_domain,
        total_received=existing_data.get("total_received", 0.0),
        total_transactions=existing_data.get("total_transactions", 0),
        created_at=existing_data.get("created_at") or now,
        updated_at=now,
    )

    serialized = paylink_data.dict(by_alias=True)
    doc_ref.set(serialized, merge=True)

    saved_data = doc_ref.get().to_dict() or {}
    saved_data["_id"] = paylink_id

    saved_data = await ensure_paystack_page(saved_data)

    return Paylink(**saved_data)


# --------------------------------------------------------------
# 2. CHECK USERNAME AVAILABILITY
# --------------------------------------------------------------
@router.post("/check-username")
async def check_username_availability(payload: dict):
    raw_username = payload.get("username")

    if not isinstance(raw_username, str) or not raw_username.strip():
        raise HTTPException(
            status_code=400,
            detail="Username is required",
        )

    username = _normalize_username(raw_username)

    if _check_reserved_username(username):
        return {
            "available": False,
            "message": "This username is reserved",
        }

    existing = _find_paylink_by_username(username)
    if existing:
        return {
            "available": False,
            "message": f"@{username} is already taken",
        }

    pending_query = (
        db.collection("pending_payments")
        .where(filter=FieldFilter("username", "==", username))
        .limit(1)
        .get()
    )

    confirmed_query = (
        db.collection("confirmed_users")
        .where(filter=FieldFilter("username", "==", username))
        .limit(1)
        .get()
    )

    if pending_query or confirmed_query:
        return {
            "available": False,
            "message": f"@{username} is already taken",
        }

    return {
        "available": True,
        "username": username,
        "message": f"@{username} is available",
    }


# --------------------------------------------------------------
# 3. GET MY PAYLINK
# --------------------------------------------------------------
@router.get("/me", response_model=Paylink)
async def get_my_paylink(current_user=Depends(get_current_user)):
    doc_ref = _paylink_ref(current_user.id)
    snapshot = doc_ref.get()

    if not snapshot.exists:
        raise HTTPException(
            status_code=404,
            detail="Paylink not found. Create one first.",
        )

    data = snapshot.to_dict() or {}
    data["_id"] = snapshot.id

    data = await ensure_paystack_page(data)

    data["display_name"] = (
        current_user.business_name
        or current_user.full_name
        or data.get("display_name")
    )

    return Paylink(**data)


# --------------------------------------------------------------
# 4. GET PUBLIC PAYLINK BY USERNAME
# --------------------------------------------------------------
@router.get("/{username}")
async def get_paylink_by_username(username: str):
    username_clean = _normalize_username(username)
    snapshot = _find_paylink_by_username(username_clean)

    if not snapshot:
        raise HTTPException(
            status_code=404,
            detail="Paylink not found",
        )

    data = snapshot.to_dict() or {}

    if not data.get("active", True):
        raise HTTPException(
            status_code=404,
            detail="Paylink is currently inactive",
        )

    owner_id = data.get("user_id")
    if not owner_id:
        logger.error("Paylink %s has no owner ID", snapshot.id)
        raise HTTPException(
            status_code=500,
            detail="Paylink owner information is incomplete",
        )

    owner_snapshot = db.collection("users").document(owner_id).get()

    if not owner_snapshot.exists:
        raise HTTPException(
            status_code=404,
            detail="Paylink owner not found",
        )

    owner_data = owner_snapshot.to_dict() or {}

    data["display_name"] = (
        owner_data.get("business_name")
        or owner_data.get("full_name")
        or data.get("display_name")
    )

    data["silver_verified"] = _owner_has_silver(owner_data)

    data = await ensure_paystack_page(data)

    return _project_public_paylink(data)


# --------------------------------------------------------------
# 4b. GET RECIPIENT BANK DETAILS
# --------------------------------------------------------------
@router.get("/{username}/recipient")
async def get_paylink_recipient(username: str):
    username_clean = _normalize_username(username)
    paylink_snapshot = _find_paylink_by_username(username_clean)

    if not paylink_snapshot:
        raise HTTPException(
            status_code=404,
            detail="Paylink not found",
        )

    paylink_data = paylink_snapshot.to_dict() or {}

    if not paylink_data.get("active", True):
        raise HTTPException(
            status_code=404,
            detail="Paylink not found",
        )

    bank_confirmed_name = paylink_data.get("bank_confirmed_name")
    bank_confirmed_bank_name = paylink_data.get("bank_confirmed_bank_name")
    bank_confirmed_last4 = paylink_data.get("bank_confirmed_account_last4")

    if not bank_confirmed_name:
        owner_id = paylink_data.get("user_id")

        if owner_id:
            owner_snapshot = (
                db.collection("users")
                .document(owner_id)
                .get()
            )

            if owner_snapshot.exists:
                owner_data = owner_snapshot.to_dict() or {}

                bank_confirmed_name = (
                    owner_data.get("bank_confirmed_name")
                    or owner_data.get("payout_account_name")
                )
                bank_confirmed_bank_name = (
                    owner_data.get("bank_confirmed_bank_name")
                    or owner_data.get("payout_bank_name")
                )

                last4 = (
                    owner_data.get("bank_confirmed_account_last4")
                    or (
                        owner_data.get("payout_account_number", "")[-4:]
                        if owner_data.get("payout_account_number")
                        else None
                    )
                )
                bank_confirmed_last4 = last4

                if bank_confirmed_name:
                    try:
                        paylink_snapshot.reference.update({
                            "bank_confirmed_name": bank_confirmed_name,
                            "bank_confirmed_bank_name": bank_confirmed_bank_name,
                            "bank_confirmed_account_last4": bank_confirmed_last4,
                        })
                    except Exception:
                        logger.exception(
                            "Could not mirror trust fields to paylink @%s",
                            username_clean,
                        )

    if not bank_confirmed_name:
        logger.error(
            "Active paylink @%s has no bank_confirmed_name and no "
            "payout fallback. Bank confirmation may not have run.",
            username_clean,
        )
        raise HTTPException(
            status_code=503,
            detail="Recipient details are temporarily unavailable.",
        )

    return {
        "name": bank_confirmed_name,
        "bank_name": bank_confirmed_bank_name,
        "account_last4": bank_confirmed_last4,
    }


# --------------------------------------------------------------
# 5. DEACTIVATE PAYLINK
# --------------------------------------------------------------
@router.patch("/me/deactivate")
async def deactivate_paylink(current_user=Depends(get_current_user)):
    ref = _paylink_ref(current_user.id)

    if not ref.get().exists:
        raise HTTPException(
            status_code=404,
            detail="No Paylink to deactivate",
        )

    ref.update({
        "active": False,
        "updated_at": _now(),
    })

    create_notification(
        user_id=current_user.id,
        title="Paylink Deactivated",
        message=(
            "Your Paylink has been deactivated. You won't receive "
            "payments until it is reactivated."
        ),
        type="info",
        link="/dashboard/paylinks",
    )

    return {"message": "Paylink deactivated"}


# --------------------------------------------------------------
# 6. ACTIVATE PAYLINK
# --------------------------------------------------------------
@router.patch("/me/activate")
async def activate_paylink(current_user=Depends(get_current_user)):
    ref = _paylink_ref(current_user.id)

    if not ref.get().exists:
        raise HTTPException(
            status_code=404,
            detail="No Paylink to activate",
        )

    ref.update({
        "active": True,
        "updated_at": _now(),
    })

    create_notification(
        user_id=current_user.id,
        title="Paylink Activated",
        message="Your Paylink is active and can receive payments.",
        type="success",
        link="/dashboard/paylinks",
    )

    return {"message": "Paylink activated"}


# --------------------------------------------------------------
# 7. CREATE PUBLIC PAYLINK TRANSACTION
# --------------------------------------------------------------
@router.post("/{username}/transaction")
async def create_paylink_transaction(
    username: str,
    req: CreatePaylinkTransactionRequest,
):
    username_clean = _normalize_username(username)
    paylink_snapshot = _find_paylink_by_username(username_clean)

    if not paylink_snapshot:
        raise HTTPException(
            status_code=404,
            detail="Paylink not found",
        )

    paylink_data = paylink_snapshot.to_dict() or {}

    if not paylink_data.get("active", True):
        raise HTTPException(
            status_code=404,
            detail="Paylink is currently inactive",
        )

    user_id = paylink_data.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=500,
            detail="Paylink owner information is incomplete",
        )

    user_snapshot = db.collection("users").document(user_id).get()

    if not user_snapshot.exists:
        raise HTTPException(
            status_code=404,
            detail="Owner profile not found",
        )

    user_data = user_snapshot.to_dict() or {}

    subaccount_code = (
        user_data.get("paystack_subaccount_code")
        or user_data.get("paystack_subaccount_id")
    )

    if not subaccount_code:
        raise HTTPException(
            status_code=400,
            detail="This creator has not completed their settlement setup.",
        )

    total_to_charge = _as_float(req.amount, "amount")

    requested_raw = getattr(req, "amount_requested", None)
    requested_amount = (
        _as_float(requested_raw, "amount_requested")
        if requested_raw is not None
        else total_to_charge
    )

    if requested_amount > total_to_charge:
        raise HTTPException(
            status_code=400,
            detail="Requested amount cannot exceed the total charge",
        )

    total_kobo_float = round(total_to_charge * 100)
    if not math.isclose(total_kobo_float, total_to_charge * 100, abs_tol=1e-7):
        raise HTTPException(
            status_code=400,
            detail="Amount cannot be represented in kobo",
        )

    requested_kobo = round(requested_amount * 100)
    total_kobo = int(total_kobo_float)
    payla_buffer_kobo = total_kobo - requested_kobo

    if total_kobo <= 0:
        raise HTTPException(
            status_code=400,
            detail="Payment amount must be greater than zero",
        )

    reference = f"payla_{uuid.uuid4().hex}"

    now = _now()
    transaction_data = {
        "paylink_id": paylink_snapshot.id,
        "user_id": user_id,
        "paylink_username": username_clean,
        "amount_requested": requested_amount,
        "amount_paid": total_to_charge,
        "payer_email": req.payer_email,
        "payer_name": getattr(req, "payer_name", None) or "Anonymous",
        "payer_phone": getattr(req, "payer_phone", None) or "",
        "paystack_reference": reference,
        "paystack_subaccount_code": subaccount_code,
        "status": "pending",
        "payout_status": "split_automated",
        "created_at": now,
        "updated_at": now,
        "metadata": {
            "type": "paylink",
            "user_id": user_id,
            "paylink_id": paylink_snapshot.id,
            "paylink_username": username_clean,
            "requested_amount": requested_amount,
            "amount_requested": requested_amount,
            "notes": getattr(req, "notes", None),
        },
    }

    db.collection("paylink_transactions").document(reference).set(
        transaction_data
    )

    bank_confirmed_name = user_data.get("bank_confirmed_name")
    bank_confirmed_bank_name = user_data.get("bank_confirmed_bank_name")
    bank_confirmed_last4 = user_data.get("bank_confirmed_account_last4")

    recipient = None
    if bank_confirmed_name:
        recipient = {
            "name": bank_confirmed_name,
            "bank_name": bank_confirmed_bank_name,
            "account_last4": bank_confirmed_last4,
        }

    return {
        "reference": reference,
        "email": req.payer_email,
        "amount_kobo": total_kobo,
        "public_key": settings.PAYSTACK_PUBLIC_KEY,
        "subaccount": subaccount_code,
        "bearer": "subaccount",
        "transaction_charge": payla_buffer_kobo,
        "metadata": transaction_data["metadata"],
        "recipient": recipient,
    }


# --------------------------------------------------------------
# 8. GET PUBLIC TRANSACTION STATUS
# --------------------------------------------------------------
@router.get("/{username}/transaction/{reference}")
async def get_paylink_transaction_status(
    username: str,
    reference: str,
):
    username_clean = _normalize_username(username)

    snapshot = (
        db.collection("paylink_transactions")
        .document(reference)
        .get()
    )

    if not snapshot.exists:
        raise HTTPException(
            status_code=404,
            detail="Transaction not found",
        )

    txn = snapshot.to_dict() or {}

    if (txn.get("paylink_username") or "").lower() != username_clean:
        raise HTTPException(
            status_code=404,
            detail="Transaction not found",
        )

    return {
        "reference": txn.get("paystack_reference") or reference,
        "status": txn.get("status", "pending"),
        "amount": txn.get("amount_paid"),
        "currency": txn.get("currency", "NGN"),
        "created_at": txn.get("created_at"),
        "paid_at": txn.get("paid_at"),
    }


# --------------------------------------------------------------
# 9. TRACK PUBLIC PAYLINK PAGE VIEW — SILVER FEATURE
# --------------------------------------------------------------
@router.post("/{username}/analytics/view")
async def track_page_view(username: str, request: Request):
    username_clean = _normalize_username(username)
    snapshot = _find_paylink_by_username(username_clean)

    if not snapshot:
        raise HTTPException(status_code=404, detail="Paylink not found")

    data = snapshot.to_dict() or {}

    if not data.get("active", True):
        raise HTTPException(status_code=404, detail="Paylink not found")

    owner_id = data.get("user_id")
    if not owner_id:
        raise HTTPException(status_code=404, detail="Paylink owner not found")

    owner_snapshot = db.collection("users").document(owner_id).get()
    if not owner_snapshot.exists:
        raise HTTPException(status_code=404, detail="Paylink owner not found")

    owner_data = owner_snapshot.to_dict() or {}

    if not _owner_has_silver(owner_data):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Paylink analytics requires a Silver subscription.",
        )

    if _is_bot_request(request):
        return {"success": True, "tracked": False}

    paylink_id = snapshot.id
    increment_paylink_metric(paylink_id, "page_views")
    increment_daily_metric(paylink_id, "page_views")
    log_paylink_event(paylink_id, "page_view")

    return {"success": True, "tracked": True}


# --------------------------------------------------------------
# 10. TRACK PUBLIC TRANSFER CLICK — SILVER FEATURE
# --------------------------------------------------------------
@router.post("/{username}/analytics/transfer")
async def track_transfer_click(username: str):
    username_clean = _normalize_username(username)
    snapshot = _find_paylink_by_username(username_clean)

    if not snapshot:
        raise HTTPException(status_code=404, detail="Paylink not found")

    data = snapshot.to_dict() or {}

    if not data.get("active", True):
        raise HTTPException(status_code=404, detail="Paylink not found")

    owner_id = data.get("user_id")
    if not owner_id:
        raise HTTPException(status_code=404, detail="Paylink owner not found")

    owner_snapshot = db.collection("users").document(owner_id).get()
    if not owner_snapshot.exists:
        raise HTTPException(status_code=404, detail="Paylink owner not found")

    owner_data = owner_snapshot.to_dict() or {}

    if not _owner_has_silver(owner_data):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Paylink analytics requires a Silver subscription.",
        )

    paylink_id = snapshot.id
    increment_paylink_metric(paylink_id, "transfer_clicks")
    increment_daily_metric(paylink_id, "transfer_clicks")
    log_paylink_event(paylink_id, "transfer_click")

    return {"success": True}