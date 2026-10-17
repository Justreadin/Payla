# app/routers/payout.py

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Depends
from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.firebase import db
from app.models.payout_model import (
    DeleteResponse,
    PayoutAccountIn,
    PayoutAccountOut,
)
from app.models.user_model import User
from app.utils.name_match import match_name


router = APIRouter(prefix="/payout", tags=["Payout Settings"])
logger = logging.getLogger("payla")


# ==================== General Helpers ====================

def normalize_status(value: Optional[str]) -> str:
    """Normalize a status value for API responses."""
    return str(value or "processing").strip().lower()


def serialize_timestamp(value) -> Optional[str]:
    """Convert Firestore timestamps and datetimes into ISO strings."""
    if value is None:
        return None

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return None


def timestamp_sort_key(item: dict) -> str:
    return item.get("created_at") or ""


def build_history_item(
    reference: str,
    data: dict,
    source: str,
) -> dict:
    """
    Normalize a payment or payout document.

    payments.status represents the customer's payment status.
    payouts.status represents the merchant settlement status.
    These statuses must never be treated as interchangeable.
    """
    source_type = str(
        data.get("source_type")
        or data.get("type")
        or data.get("payout_type")
        or ""
    ).strip().lower()

    if source_type not in {"invoice", "paylink"}:
        if data.get("invoice_id"):
            source_type = "invoice"
        elif data.get("paylink_id"):
            source_type = "paylink"
        else:
            source_type = "payment"

    if source == "payout":
        # In the current webhook flow, a payout record is created
        # after a successful merchant payment.
        payment_status = "success"

        # The webhook stores settlement status in payouts.status.
        payout_status = normalize_status(data.get("status"))
    else:
        payment_status = normalize_status(data.get("status"))

        # Payment success alone does not establish settlement.
        payout_status = data.get("payout_status")

        if payout_status is not None:
            payout_status = normalize_status(payout_status)

    created_at = (
        data.get("created_at")
        or data.get("paid_at")
        or data.get("updated_at")
    )

    description = data.get("description")

    if not description:
        if source_type == "invoice":
            description = (
                data.get("invoice_number")
                or "Invoice payment"
            )
        elif source_type == "paylink":
            description = (
                data.get("paylink_name")
                or "Paylink payment"
            )
        else:
            description = "Payment"

    amount = data.get("user_share")

    if amount is None:
        amount = data.get("amount", 0)

    return {
        "reference": (
            data.get("reference")
            or data.get("paystack_reference")
            or reference
        ),
        "amount": amount,
        "source_type": source_type,
        "description": description,
        "status": payment_status,
        "payout_status": payout_status,
        "created_at": serialize_timestamp(created_at),
    }


# ==================== Bank Confirmation Helper ====================

def write_bank_confirmation(
    user_id: str,
    user_full_name: Optional[str],
    resolved_account_name: str,
    resolved_bank_name: str,
    account_number: str,
) -> str:
    """
    Run the fuzzy name match and write the trust fields to both the
    user document and the paylink document.

    Returns the computed match status.

    The user doc carries the canonical trust state. The paylink doc
    mirrors it so the public card can render the stamp without a
    second Firestore read.
    """
    status = match_name(user_full_name, resolved_account_name)
    now = datetime.now(timezone.utc)

    trust_updates = {
        "bank_confirmation_status": status,
        "bank_confirmed_name": resolved_account_name,
        "bank_confirmed_bank_name": resolved_bank_name,
        "bank_confirmed_account_last4": (
            account_number[-4:] if account_number else None
        ),
        "bank_confirmed_at": now,
        "bank_confirmation_attempted_at": now,
        "bank_confirmation_retry_count": 0,
    }

    try:
        db.collection("users").document(user_id).update(trust_updates)
    except Exception:
        logger.exception(
            "Failed to write bank confirmation to user %s",
            user_id,
        )
        raise

    # Mirror to the paylink document (if it exists).
    paylink_ref = db.collection("paylinks").document(user_id)
    try:
        if paylink_ref.get().exists:
            paylink_ref.update({
                "bank_confirmation_status": status,
                "bank_confirmed_name": resolved_account_name,
                "bank_confirmed_bank_name": resolved_bank_name,
                "bank_confirmed_account_last4": (
                    account_number[-4:] if account_number else None
                ),
            })
    except Exception:
        # The user write succeeded; the mirror is best-effort.
        # The retry job will re-mirror on its next pass.
        logger.exception(
            "Failed to mirror bank confirmation to paylink %s",
            user_id,
        )

    logger.info(
        "Bank confirmation for user %s: status=%s name=%r",
        user_id,
        status,
        resolved_account_name,
    )

    return status


# ==================== Paystack Helpers ====================

async def resolve_account_name(
    bank_code: str,
    account_number: str,
) -> dict:
    """Resolve a bank account through Paystack."""

    url = "https://api.paystack.co/bank/resolve"

    headers = {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
    }

    params = {
        "account_number": account_number,
        "bank_code": bank_code,
    }

    async with httpx.AsyncClient(timeout=12.0) as client:
        try:
            response = await client.get(
                url,
                headers=headers,
                params=params,
            )

        except httpx.TimeoutException as exc:
            logger.warning(
                "Paystack account resolution timed out: %s",
                exc,
            )
            raise HTTPException(
                status_code=504,
                detail="Bank verification timed out. Please try again.",
            )

        except httpx.RequestError as exc:
            logger.error(
                "Paystack account resolution failed: %s",
                exc,
            )
            raise HTTPException(
                status_code=502,
                detail="Bank verification is temporarily unavailable.",
            )

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")

            logger.warning(
                "Paystack rate-limited account resolution; "
                "retry_after=%s",
                retry_after,
            )

            headers_out = (
                {"Retry-After": retry_after}
                if retry_after and retry_after.isdigit()
                else None
            )

            raise HTTPException(
                status_code=503,
                detail=(
                    "Bank verification is temporarily busy. "
                    "Please try again shortly."
                ),
                headers=headers_out,
            )

        if response.status_code in (401, 403):
            logger.error(
                "Paystack rejected account-resolution credentials: "
                "HTTP %s",
                response.status_code,
            )
            raise HTTPException(
                status_code=502,
                detail="Bank verification is temporarily unavailable.",
            )

        if response.status_code >= 500:
            logger.error(
                "Paystack account-resolution server error: HTTP %s",
                response.status_code,
            )
            raise HTTPException(
                status_code=502,
                detail="Bank verification is temporarily unavailable.",
            )

        try:
            data = response.json()
        except ValueError:
            logger.error(
                "Paystack returned invalid JSON during account "
                "resolution: HTTP %s",
                response.status_code,
            )
            raise HTTPException(
                status_code=502,
                detail=(
                    "Unexpected response from bank verification service."
                ),
            )

        if response.status_code != 200 or not data.get("status"):
            if response.status_code in (400, 404, 422):
                raise HTTPException(
                    status_code=400,
                    detail=data.get(
                        "message",
                        "Unable to verify this bank account.",
                    ),
                )

            logger.error(
                "Unexpected Paystack resolution response: HTTP %s",
                response.status_code,
            )
            raise HTTPException(
                status_code=502,
                detail="Bank verification could not be completed.",
            )

        account_data = data.get("data") or {}
        account_name = account_data.get("account_name")

        if not account_name:
            logger.error(
                "Paystack resolution succeeded without an account name"
            )
            raise HTTPException(
                status_code=502,
                detail=(
                    "Bank verification returned incomplete information."
                ),
            )

        bank_name = account_data.get("bank_name")

        # Fallback if Paystack omits the bank name in the resolve response.
        if not bank_name:
            try:
                banks_response = await client.get(
                    "https://api.paystack.co/bank",
                    headers=headers,
                )

                if banks_response.status_code == 200:
                    banks_data = banks_response.json()

                    if banks_data.get("status"):
                        matched_bank = next(
                            (
                                bank
                                for bank in banks_data.get("data", [])
                                if str(bank.get("code"))
                                == str(bank_code)
                            ),
                            None,
                        )

                        if matched_bank:
                            bank_name = matched_bank.get("name")

            except (httpx.RequestError, ValueError):
                logger.warning(
                    "Could not retrieve bank name for bank code %s",
                    bank_code,
                )

        return {
            "account_name": account_name,
            "bank_name": bank_name or "Unknown Bank",
        }


async def create_or_update_subaccount(
    user_id: str,
    bank_code: str,
    account_number: str,
    payout_account_name: str,
) -> str:
    """Create or update the user's Paystack subaccount."""

    url = "https://api.paystack.co/subaccount"

    headers = {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }

    user_doc = (
        db.collection("users")
        .document(user_id)
        .get()
    )

    user_data = user_doc.to_dict() if user_doc.exists else {}
    subaccount_code = user_data.get("paystack_subaccount_code")

    payload = {
        "business_name": payout_account_name,
        "settlement_bank": bank_code,
        "account_number": account_number,
        "percentage_charge": 0,
        "description": f"Payla Payouts: {user_id}",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            if subaccount_code:
                response = await client.put(
                    f"{url}/{subaccount_code}",
                    json=payload,
                    headers=headers,
                )
            else:
                response = await client.post(
                    url,
                    json=payload,
                    headers=headers,
                )

        except httpx.TimeoutException as exc:
            logger.error(
                "Paystack subaccount request timed out: %s",
                exc,
            )
            raise HTTPException(
                status_code=504,
                detail="Bank account linking timed out. Please try again.",
            )

        except httpx.RequestError as exc:
            logger.error(
                "Paystack subaccount request failed: %s",
                exc,
            )
            raise HTTPException(
                status_code=502,
                detail="Could not connect to payment provider.",
            )

        try:
            data = response.json()
        except ValueError:
            logger.error(
                "Paystack returned invalid JSON for subaccount request"
            )
            raise HTTPException(
                status_code=502,
                detail="Unexpected response from payment provider.",
            )

        if (
            response.status_code in (200, 201)
            and data.get("status")
        ):
            returned_code = (
                (data.get("data") or {}).get("subaccount_code")
            )

            if returned_code:
                return returned_code

        logger.error(
            "Paystack subaccount request failed: HTTP %s",
            response.status_code,
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Could not link bank account with payment provider."
            ),
        )


# ==================== Payout Account Routes ====================

@router.post(
    "/account",
    response_model=PayoutAccountOut,
)
async def save_payout_account(
    payload: PayoutAccountIn,
    current_user: User = Depends(get_current_user),
):
    user_id = current_user.id
    user_ref = db.collection("users").document(user_id)

    user_doc = user_ref.get()
    user_data = user_doc.to_dict() if user_doc.exists else {}

    existing_bank = user_data.get("payout_bank")
    existing_account = user_data.get("payout_account_number")
    subaccount_code = user_data.get("paystack_subaccount_code")

    # Reuse an existing account only when its stored verification
    # state is already true.
    if (
        existing_bank == payload.bank_code
        and existing_account == payload.account_number
        and subaccount_code
        and user_data.get("payout_verified") is True
    ):
        # Even on the fast path, ensure trust fields are current.
        # If they're missing (e.g. account existed before this feature
        # shipped), backfill them now.
        if not user_data.get("bank_confirmed_name"):
            try:
                write_bank_confirmation(
                    user_id=user_id,
                    user_full_name=user_data.get("full_name"),
                    resolved_account_name=user_data.get(
                        "payout_account_name", ""
                    ),
                    resolved_bank_name=user_data.get(
                        "payout_bank_name", "Unknown Bank"
                    ),
                    account_number=existing_account,
                )
            except Exception:
                # Non-fatal — the retry job will pick it up.
                logger.exception(
                    "Backfill of trust fields failed for existing "
                    "account of user %s",
                    user_id,
                )

        return PayoutAccountOut(
            bank_code=existing_bank,
            account_number=existing_account,
            account_name=user_data.get("payout_account_name", ""),
            bank_name=user_data.get(
                "payout_bank_name",
                "Unknown Bank",
            ),
            subaccount_code=subaccount_code,
            is_verified=True,
            updated_at=user_data.get(
                "updated_at",
                datetime.now(timezone.utc),
            ),
        )

    # Resolve the submitted bank details before creating/updating
    # the Paystack subaccount.
    resolved = await resolve_account_name(
        payload.bank_code,
        payload.account_number,
    )

    new_subaccount_code = await create_or_update_subaccount(
        user_id=user_id,
        bank_code=payload.bank_code,
        account_number=payload.account_number,
        payout_account_name=resolved["account_name"],
    )

    now = datetime.now(timezone.utc)

    update_data = {
        "payout_bank": payload.bank_code,
        "payout_account_number": payload.account_number,
        "payout_account_name": resolved["account_name"],
        "payout_bank_name": resolved["bank_name"],
        "paystack_subaccount_code": new_subaccount_code,
        "bank_verified": True,
        "payout_verified": True,
        "updated_at": now,
    }

    user_ref.update(update_data)

    # ── Bank confirmation ──
    # Run the fuzzy match and mirror the trust fields.
    try:
        write_bank_confirmation(
            user_id=user_id,
            user_full_name=user_data.get("full_name"),
            resolved_account_name=resolved["account_name"],
            resolved_bank_name=resolved["bank_name"],
            account_number=payload.account_number,
        )
    except Exception:
        # Non-fatal — the retry job will pick it up on its next pass.
        logger.exception(
            "Bank confirmation write failed for user %s; "
            "retry job will handle it.",
            user_id,
        )

    return PayoutAccountOut(
        bank_code=payload.bank_code,
        account_number=payload.account_number,
        account_name=resolved["account_name"],
        bank_name=resolved["bank_name"],
        subaccount_code=new_subaccount_code,
        is_verified=True,
        updated_at=now,
    )


@router.get(
    "/account",
    response_model=Optional[PayoutAccountOut],
)
async def get_payout_account(
    current_user: User = Depends(get_current_user),
):
    doc = (
        db.collection("users")
        .document(current_user.id)
        .get()
    )

    if not doc.exists:
        return None

    data = doc.to_dict() or {}

    if not data.get("payout_account_number"):
        return None

    return PayoutAccountOut(
        bank_code=data.get("payout_bank", ""),
        account_number=data.get("payout_account_number", ""),
        account_name=data.get("payout_account_name", ""),
        bank_name=data.get(
            "payout_bank_name",
            "Unknown Bank",
        ),
        subaccount_code=data.get("paystack_subaccount_code"),
        is_verified=data.get("payout_verified") is True,
        updated_at=data.get(
            "updated_at",
            datetime.now(timezone.utc),
        ),
    )


@router.delete(
    "/account",
    response_model=DeleteResponse,
)
async def remove_payout_account(
    current_user: User = Depends(get_current_user),
):
    ref = db.collection("users").document(current_user.id)

    ref.update({
        "payout_bank": firestore.DELETE_FIELD,
        "payout_account_number": firestore.DELETE_FIELD,
        "payout_account_name": firestore.DELETE_FIELD,
        "payout_bank_name": firestore.DELETE_FIELD,
        "bank_verified": False,
        "payout_verified": False,
        # Clear trust fields on removal. The stamp drops until a
        # new account is verified. Tenure data on the paylink doc
        # remains untouched.
        "bank_confirmation_status": firestore.DELETE_FIELD,
        "bank_confirmed_name": firestore.DELETE_FIELD,
        "bank_confirmed_bank_name": firestore.DELETE_FIELD,
        "bank_confirmed_account_last4": firestore.DELETE_FIELD,
        "bank_confirmed_at": firestore.DELETE_FIELD,
        "bank_confirmation_attempted_at": firestore.DELETE_FIELD,
        "bank_confirmation_retry_count": firestore.DELETE_FIELD,
        "updated_at": datetime.now(timezone.utc),
    })

    # Mirror the removal to the paylink doc.
    paylink_ref = db.collection("paylinks").document(current_user.id)
    if paylink_ref.get().exists:
        paylink_ref.update({
            "bank_confirmation_status": firestore.DELETE_FIELD,
            "bank_confirmed_name": firestore.DELETE_FIELD,
            "bank_confirmed_bank_name": firestore.DELETE_FIELD,
            "bank_confirmed_account_last4": firestore.DELETE_FIELD,
        })

    # Keep paystack_subaccount_code so a later account update can reuse
    # the existing subaccount where Paystack permits it.
    logger.info(
        "Payout account removed for user %s",
        current_user.id,
    )

    return DeleteResponse()


@router.get("/banks")
async def get_banks():
    url = "https://api.paystack.co/bank"

    headers = {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                url,
                headers=headers,
            )

        except httpx.TimeoutException as exc:
            logger.warning(
                "Paystack bank-list request timed out: %s",
                exc,
            )
            raise HTTPException(
                status_code=504,
                detail="Bank service timed out. Please try again.",
            )

        except httpx.RequestError as exc:
            logger.error(
                "Failed to retrieve banks: %s",
                exc,
            )
            raise HTTPException(
                status_code=502,
                detail="Bank service unavailable.",
            )

        try:
            data = response.json()
        except ValueError:
            raise HTTPException(
                status_code=502,
                detail="Unexpected response from bank service.",
            )

        if response.status_code == 429:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Bank service is temporarily busy. "
                    "Please try again shortly."
                ),
            )

        if response.status_code == 200 and data.get("status"):
            return {"banks": data.get("data", [])}

        logger.error(
            "Paystack bank-list request failed: HTTP %s",
            response.status_code,
        )

        raise HTTPException(
            status_code=502,
            detail="Failed to load banks.",
        )


@router.get("/resolve")
async def resolve_payout_account(
    bank: str,
    account: str,
    current_user: User = Depends(get_current_user),
):
    if len(account) != 10 or not account.isdigit():
        raise HTTPException(
            status_code=400,
            detail="Invalid account number.",
        )

    resolved = await resolve_account_name(bank, account)

    return {
        "account_name": resolved["account_name"],
        "bank_name": resolved.get(
            "bank_name",
            "Unknown Bank",
        ),
    }


# ==================== Earnings ====================

@router.get("/earnings")
async def earnings(
    current_user: User = Depends(get_current_user),
):
    user_doc = (
        db.collection("users")
        .document(current_user.id)
        .get()
    )

    user_data = user_doc.to_dict() if user_doc.exists else {}

    # Keep the existing earnings calculation unchanged.
    return {
        "total_earnings": user_data.get("total_earned", 0.0),
        "available_for_payout": 0,
        "display_available": "Automated (T+1)",
        "payout_method": user_data.get(
            "payout_bank_name",
            "your bank",
        ),
        "next_payout": "Next working day",
        "is_automated": True,
        "fee_structure": "Your Clients Pay Fees",
    }


# ==================== Payout History ====================

@router.get("/history")
async def payout_history(
    current_user: User = Depends(get_current_user),
):
    user_id = current_user.id
    history_by_reference = {}

    # Payout records supply merchant settlement information.
    payout_docs = (
        db.collection("payouts")
        .where(filter=FieldFilter("user_id", "==", user_id))
        .stream()
    )

    for doc in payout_docs:
        data = doc.to_dict() or {}

        item = build_history_item(
            doc.id,
            data,
            "payout",
        )

        reference = item["reference"]

        if reference:
            history_by_reference[reference] = item

    # Payment records are canonical for payment status and merchant share.
    # Failed payment attempts may not have a corresponding payout record.
    payment_docs = (
        db.collection("payments")
        .where(filter=FieldFilter("user_id", "==", user_id))
        .stream()
    )

    for doc in payment_docs:
        data = doc.to_dict() or {}

        item = build_history_item(
            doc.id,
            data,
            "payment",
        )

        reference = item["reference"]

        if not reference:
            continue

        existing = history_by_reference.get(reference)

        if existing:
            # Keep settlement status from the payout document.
            item["payout_status"] = existing.get("payout_status")

        # Prefer payment data for amount, source, description and payment
        # status while retaining settlement status from the payout record.
        history_by_reference[reference] = item

    history = sorted(
        history_by_reference.values(),
        key=timestamp_sort_key,
        reverse=True,
    )[:20]

    return {
        "history": history,
        "payouts": history,
        "has_more": len(history_by_reference) > 20,
    }


# ==================== Payout Status ====================

@router.get("/transaction/{reference}/payout_status")
async def get_payout_status(
    reference: str,
    current_user: User = Depends(get_current_user),
):
    user_id = current_user.id

    payout_data = None
    payment_data = None
    transaction_data = None
    invoice_data = None

    # 1. Look up the merchant settlement record.
    payout_doc = (
        db.collection("payouts")
        .document(reference)
        .get()
    )

    if payout_doc.exists:
        candidate = payout_doc.to_dict() or {}

        if candidate.get("user_id") != user_id:
            raise HTTPException(
                status_code=404,
                detail="Transaction not found",
            )

        payout_data = candidate

    # 2. Look up the customer payment record.
    payment_doc = (
        db.collection("payments")
        .document(reference)
        .get()
    )

    if payment_doc.exists:
        candidate = payment_doc.to_dict() or {}

        if candidate.get("user_id") != user_id:
            raise HTTPException(
                status_code=404,
                detail="Transaction not found",
            )

        payment_data = candidate

    # 3. Support legacy paylink transaction records.
    if payment_data is None and payout_data is None:
        transaction_doc = (
            db.collection("paylink_transactions")
            .document(reference)
            .get()
        )

        if transaction_doc.exists:
            candidate = transaction_doc.to_dict() or {}

            if candidate.get("user_id") != user_id:
                raise HTTPException(
                    status_code=404,
                    detail="Transaction not found",
                )

            transaction_data = candidate

    # 4. Support legacy invoice records.
    # Invoice ownership in the webhook schema uses sender_id.
    if (
        payment_data is None
        and payout_data is None
        and transaction_data is None
    ):
        invoice_docs = (
            db.collection("invoices")
            .where(
                filter=FieldFilter(
                    "transaction_reference", "==", reference
                )
            )
            .limit(1)
            .stream()
        )

        for invoice_doc in invoice_docs:
            candidate = invoice_doc.to_dict() or {}

            if candidate.get("sender_id") != user_id:
                raise HTTPException(
                    status_code=404,
                    detail="Transaction not found",
                )

            invoice_data = candidate
            break

    if (
        payment_data is None
        and payout_data is None
        and transaction_data is None
        and invoice_data is None
    ):
        raise HTTPException(
            status_code=404,
            detail="Transaction not found",
        )

    # Payment status and payout status are independent.
    if payment_data is not None:
        payment_status = normalize_status(
            payment_data.get("status")
        )
    elif transaction_data is not None:
        payment_status = normalize_status(
            transaction_data.get("status")
        )
    elif invoice_data is not None:
        payment_status = normalize_status(
            invoice_data.get("status")
        )
    else:
        # The current webhook creates payout records only after successful
        # merchant payment processing. payouts.status is not payment status.
        payment_status = "success"

    if payout_data is not None:
        # Webhook stores processing/pending/settled/failed/reversed here.
        payout_status = normalize_status(
            payout_data.get("status")
        )
    else:
        source_data = transaction_data or invoice_data or {}

        payout_status = (
            normalize_status(source_data.get("payout_status"))
            if source_data.get("payout_status") is not None
            else None
        )

    return {
        "reference": reference,
        "status": payment_status,
        "payout_status": payout_status,
    }