
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from app.services.receipt_service import dispatch_payment_receipts

from fastapi import APIRouter, HTTPException, Request, status
from firebase_admin import firestore

from app.core.config import settings
from app.services.subscription_webhooks import handle_subscription_event


logger = logging.getLogger("payla")
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
db = firestore.client()


SUBSCRIPTION_EVENTS = {
    "subscription.create",
    "subscription.disable",
    "subscription.not_renew",
    "subscription.expire",
    "invoice.create",
    "invoice.update",
    "invoice.payment_failed",
}

TRANSFER_EVENTS = {
    "transfer.success",
    "transfer.failed",
    "transfer.reversed",
}

SUCCESS_ATTEMPT_STATES = {"initializing", "initialized"}


# ============================================================
# GENERAL HELPERS
# ============================================================

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _verify_signature(payload: bytes, signature: Optional[str]) -> bool:
    secret = settings.PAYSTACK_SECRET_KEY

    if not secret or not signature:
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha512,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


def _amount_from_kobo(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Invalid payment amount")

    amount = Decimal(str(value))

    if not amount.is_finite() or amount < 0:
        raise ValueError("Invalid payment amount")

    if amount != amount.to_integral_value():
        raise ValueError("Invalid kobo amount")

    return float(amount / Decimal("100"))


def _naira_to_kobo(value: Any) -> int:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Invalid naira amount") from exc

    if not amount.is_finite() or amount < 0:
        raise ValueError("Invalid naira amount")

    kobo = amount * Decimal("100")

    if kobo != kobo.to_integral_value():
        raise ValueError("Amount cannot contain more than two decimal places")

    return int(kobo)


def _metadata(data: dict) -> dict:
    value = data.get("metadata")
    return value if isinstance(value, dict) else {}


def _customer_email(data: dict) -> Optional[str]:
    customer = data.get("customer")
    return customer.get("email") if isinstance(customer, dict) else None


def _reference(data: dict) -> Optional[str]:
    value = data.get("reference")
    return str(value).strip() if value else None


def _normalize_fee_payer(value: Any) -> str:
    # "receiver" is treated as the legacy equivalent of "merchant".
    return "client" if value == "client" else "merchant"


def _safe_amount(value: Any, default: float = 0.0) -> float:
    try:
        amount = Decimal(str(value))
        if amount.is_finite():
            return float(amount)
    except (InvalidOperation, TypeError, ValueError):
        pass
    return default


def _review_result(reason: str) -> dict:
    return {
        "processed": False,
        "reason": reason,
        "requires_review": True,
        "queue_payout": False,
    }


def _write_review_marker(
    transaction,
    marker_ref,
    reference: str,
    reason: str,
    now: datetime,
    existing_data: Optional[dict] = None,
) -> dict:
    """
    Preserve an auditable record of a verified charge that cannot yet
    be reconciled. Unlike a terminal ignored marker, review_required
    markers are eligible for reconciliation on a later delivery.
    """
    previous = existing_data or {}

    transaction.set(marker_ref, {
        **previous,
        "status": "review_required",
        "reference": reference,
        "reason": reason,
        "updated_at": now,
        "created_at": previous.get("created_at", now),
    })

    return _review_result(reason)


# ============================================================
# NOTIFICATIONS
# ============================================================

def _create_payment_notification(
    reference: str,
    user_id: str,
    title: str,
    message: str,
    notification_type: str,
    link: str = "/dashboard/payments",
) -> None:
    try:
        notification_id = f"payment_{reference}_{notification_type}"

        notification_ref = (
            db.collection("notifications").document(notification_id)
        )

        # Preserve the original creation time and read state on retries.
        existing = notification_ref.get()

        if existing.exists:
            existing_data = existing.to_dict() or {}
            notification_ref.set({
                **existing_data,
                "user_id": user_id,
                "title": title,
                "message": message,
                "type": notification_type,
                "reference": reference,
                "link": link,
                "updated_at": _now(),
            }, merge=True)
            return

        notification_ref.set({
            "user_id": user_id,
            "title": title,
            "message": message,
            "type": notification_type,
            "reference": reference,
            "link": link,
            "read": False,
            "created_at": _now(),
        })

    except Exception:
        # A notification failure must not undo a recorded payment.
        logger.exception(
            "Could not create %s notification for payment %s",
            notification_type,
            reference,
        )


# ============================================================
# SUBSCRIPTION EVENT CLASSIFICATION
# ============================================================

def _is_subscription_event(event: str, data: dict) -> bool:
    if event in SUBSCRIPTION_EVENTS:
        return True

    if event not in {"charge.success", "charge.failed"}:
        return False

    metadata = _metadata(data)
    reference = _reference(data)

    if data.get("subscription"):
        return True

    if metadata.get("type") == "subscription_initial":
        return True

    if reference and reference.startswith("payla-sub-"):
        return True

    if reference:
        try:
            pending = (
                db.collection("pending_subscriptions")
                .document(reference)
                .get()
            )
            if pending.exists:
                return True
        except Exception:
            # Fail closed: don't misclassify a subscription payment as
            # a normal merchant payment if classification is uncertain.
            logger.exception(
                "Could not classify payment reference %s",
                reference,
            )
            return True

    return False


# ============================================================
# PAYMENT RECORD
# ============================================================

def _payment_record(
    reference: str,
    user_id: str,
    invoice_id: Optional[str],
    paylink_id: Optional[str],
    amount: float,
    user_share: float,
    currency: str,
    channel: Optional[str],
    data: dict,
    event: str,
    fee_payer: str = "client",
) -> dict:
    metadata = _metadata(data)
    customer = data.get("customer")
    customer = customer if isinstance(customer, dict) else {}
    now = _now()

    return {
        "_id": reference,
        "user_id": user_id,
        "invoice_id": invoice_id,
        "paylink_id": paylink_id,
        "paystack_reference": reference,
        "amount": amount,
        "user_share": user_share,
        "currency": currency,
        "status": "success",
        "channel": channel,
        "client_phone": (
            metadata.get("payer_phone") or customer.get("phone")
        ),
        "client_email": _customer_email(data),
        "fee_payer": fee_payer,
        "paid_at": now,
        "created_at": now,
        "updated_at": now,
        "raw_event": event,
    }


# ============================================================
# PAYOUT HISTORY
# ============================================================

def _next_expected_arrival(now: datetime) -> datetime:
    """
    Estimate the next working-day arrival. This is not confirmation
    that funds have reached the merchant's bank account.
    """
    if now.weekday() == 4:
        return now + timedelta(days=3)

    if now.weekday() == 5:
        return now + timedelta(days=2)

    if now.weekday() == 6:
        return now + timedelta(days=1)

    return now + timedelta(days=1)


def _record_payout(
    user_id: str,
    amount: float,
    reference: str,
    payout_type: str,
    manual_payout: bool,
    source_id: Optional[str],
) -> None:
    """
    Create payout history exactly once.

    total_earned is deliberately not updated here; it is updated only
    by the successful-payment transaction.
    """
    payout_ref = db.collection("payouts").document(reference)
    user_ref = db.collection("users").document(user_id)

    if payout_type == "invoice":
        source_ref = (
            db.collection("invoices").document(source_id)
            if source_id
            else None
        )
    else:
        source_ref = (
            db.collection("paylink_transactions").document(reference)
            if source_id
            else None
        )

    now = _now()
    arrival_date = _next_expected_arrival(now)

    payout_entry = {
        "user_id": user_id,
        "reference": reference,
        "source_id": source_id,
        "amount": amount,
        "type": payout_type,
        "status": "pending" if manual_payout else "processing",
        "created_at": now,
        "arrival_date": arrival_date,
        "paid_at": None,
        "is_automated": not manual_payout,
        "settlement_method": (
            "manual" if manual_payout else "paystack_subaccount"
        ),
    }

    @firestore.transactional
    def apply_payout(transaction):
        payout_snapshot = next(transaction.get(payout_ref))

        # Existing payout documents must not increment revenue twice.
        if payout_snapshot.exists:
            return False

        user_snapshot = next(transaction.get(user_ref))
        source_snapshot = (
            next(transaction.get(source_ref))
            if source_ref is not None
            else None
        )

        if not user_snapshot.exists:
            raise ValueError(f"Merchant {user_id} does not exist")

        # All reads are completed before writes.
        transaction.create(payout_ref, payout_entry)

        updates = {
            "last_payout_at": now,
            "updated_at": now,
        }

        if payout_type == "invoice":
            updates["total_invoice_revenue"] = firestore.Increment(amount)
        else:
            updates["total_paylink_revenue"] = firestore.Increment(amount)

        transaction.update(user_ref, updates)

        if source_ref is not None and source_snapshot and source_snapshot.exists:
            transaction.update(source_ref, {
                "payout_status": (
                    "payout_pending"
                    if manual_payout
                    else "processing_by_paystack"
                ),
                "expected_payout_at": arrival_date,
                "payout_reference": reference,
                "updated_at": now,
            })

        return True

    created = apply_payout(db.transaction())

    logger.info(
        "%s payout history for reference %s",
        "Created" if created else "Already had",
        reference,
    )


# ============================================================
# PAYMENT RECONCILIATION HELPERS
# ============================================================

def _reconcile_existing_success(
    transaction,
    reference: str,
    existing_payment: dict,
    marker_data: dict,
    metadata: dict,
    now: datetime,
) -> dict:
    """
    Repair source/attempt state for an already recorded successful
    payment without incrementing total_earned again.

    All Firestore reads are completed before this function writes.
    """
    user_id = (
        existing_payment.get("user_id")
        or marker_data.get("user_id")
        or metadata.get("user_id")
    )

    invoice_id = (
        existing_payment.get("invoice_id")
        or marker_data.get("source_id")
        if marker_data.get("payout_type") == "invoice"
        else existing_payment.get("invoice_id")
    )

    paylink_id = existing_payment.get("paylink_id") or (
        marker_data.get("source_id")
        if marker_data.get("payout_type") == "paylink"
        else None
    )

    if not user_id:
        return _review_result("recovery_missing_user_id")

    user_ref = db.collection("users").document(str(user_id))
    user_snapshot = next(transaction.get(user_ref))

    invoice_ref = (
        db.collection("invoices").document(str(invoice_id))
        if invoice_id
        else None
    )
    paylink_ref = (
        db.collection("paylinks").document(str(paylink_id))
        if paylink_id
        else None
    )
    paylink_tx_ref = (
        db.collection("paylink_transactions").document(reference)
        if paylink_id
        else None
    )
    attempt_ref = (
        db.collection("invoice_payment_attempts").document(reference)
        if invoice_id
        else None
    )

    invoice_snapshot = (
        next(transaction.get(invoice_ref))
        if invoice_ref is not None
        else None
    )
    paylink_snapshot = (
        next(transaction.get(paylink_ref))
        if paylink_ref is not None
        else None
    )
    paylink_tx_snapshot = (
        next(transaction.get(paylink_tx_ref))
        if paylink_tx_ref is not None
        else None
    )
    attempt_snapshot = (
        next(transaction.get(attempt_ref))
        if attempt_ref is not None
        else None
    )

    if not user_snapshot.exists:
        return _review_result("recovery_merchant_not_found")

    payout_type = "invoice" if invoice_id else "paylink"
    source_id = str(invoice_id or paylink_id or "")
    source_data = {}

    if invoice_id:
        if not invoice_snapshot or not invoice_snapshot.exists:
            return _review_result("recovery_invoice_not_found")

        source_data = invoice_snapshot.to_dict() or {}

        if source_data.get("sender_id") != user_id:
            return _review_result("recovery_invoice_owner_mismatch")

        # A payment record with a different invoice amount is not safe
        # to reconcile automatically.
        try:
            invoice_kobo = _naira_to_kobo(source_data.get("amount"))
            paid_kobo = _naira_to_kobo(
                existing_payment.get("user_share")
            )
        except ValueError:
            return _review_result("recovery_invalid_invoice_amount")

        if invoice_kobo != paid_kobo:
            return _review_result("recovery_invoice_amount_mismatch")

        if attempt_snapshot and attempt_snapshot.exists:
            attempt_data = attempt_snapshot.to_dict() or {}

            if (
                attempt_data.get("invoice_id") != str(invoice_id)
                or attempt_data.get("user_id") != user_id
            ):
                return _review_result("recovery_attempt_mismatch")

    else:
        if not paylink_snapshot or not paylink_snapshot.exists:
            return _review_result("recovery_paylink_not_found")

        if not paylink_tx_snapshot or not paylink_tx_snapshot.exists:
            return _review_result("recovery_paylink_transaction_not_found")

        source_data = paylink_snapshot.to_dict() or {}
        tx_data = paylink_tx_snapshot.to_dict() or {}

        if source_data.get("user_id") != user_id:
            return _review_result("recovery_paylink_owner_mismatch")

        if (
            tx_data.get("user_id") != user_id
            or tx_data.get("paylink_id") != str(paylink_id)
        ):
            return _review_result("recovery_paylink_transaction_mismatch")

    user_data = user_snapshot.to_dict() or {}
    subaccount_code = (
        source_data.get("paystack_subaccount_code")
        or user_data.get("paystack_subaccount_code")
    )
    manual_payout = not bool(subaccount_code)

    repaired_marker = {
        **marker_data,
        "status": "success",
        "reference": reference,
        "user_id": user_id,
        "payment_record": existing_payment,
        "payout_type": payout_type,
        "source_id": source_id,
        "manual_payout": manual_payout,
        "updated_at": now,
        "created_at": marker_data.get("created_at", now),
        "recovered": True,
    }

    transaction.set(
        db.collection("processed_merchant_payments").document(reference),
        repaired_marker,
    )

    if invoice_id:
        transaction.update(invoice_ref, {
            "status": "paid",
            "paid_at": existing_payment.get("paid_at") or now,
            "paystack_reference": reference,
            "transaction_reference": reference,
            "payout_status": (
                "payout_pending"
                if manual_payout
                else "processing_by_paystack"
            ),
            "updated_at": now,
        })

        if attempt_snapshot and attempt_snapshot.exists:
            transaction.update(attempt_ref, {
                "status": "success",
                "paid_at": existing_payment.get("paid_at") or now,
                "updated_at": now,
            })

    else:
        transaction.update(paylink_tx_ref, {
            "status": "success",
            "paid_at": existing_payment.get("paid_at") or now,
            "paystack_reference": reference,
            "payout_status": (
                "payout_pending"
                if manual_payout
                else "processing_by_paystack"
            ),
            "updated_at": now,
        })

    return {
        "processed": True,
        "reason": "recovered_existing_success",
        "queue_payout": True,
        "user_id": user_id,
        "amount": _safe_amount(existing_payment.get("user_share")),
        "payout_type": payout_type,
        "source_id": source_id,
        "manual_payout": manual_payout,
    }


# ============================================================
# SUCCESSFUL MERCHANT PAYMENTS
# ============================================================

async def _process_merchant_payment(
    event: str,
    data: dict,
    reference: str,
) -> dict:
    metadata = _metadata(data)
    user_id = metadata.get("user_id")
    invoice_id = metadata.get("invoice_id")
    paylink_id = metadata.get("paylink_id")

    if not user_id:
        return _review_result("missing_user_id")

    # A payment must map to exactly one merchant source.
    if bool(invoice_id) == bool(paylink_id):
        return _review_result("missing_or_ambiguous_payment_source")

    try:
        gross_amount = _amount_from_kobo(data.get("amount"))
    except (ValueError, TypeError):
        return _review_result("invalid_amount")

    currency = str(data.get("currency") or "").upper()

    if currency != "NGN":
        return _review_result("unsupported_currency")

    marker_ref = (
        db.collection("processed_merchant_payments").document(reference)
    )
    payment_ref = db.collection("payments").document(reference)
    user_ref = db.collection("users").document(str(user_id))

    invoice_ref = (
        db.collection("invoices").document(str(invoice_id))
        if invoice_id else None
    )
    paylink_ref = (
        db.collection("paylinks").document(str(paylink_id))
        if paylink_id else None
    )
    paylink_tx_ref = (
        db.collection("paylink_transactions").document(reference)
        if paylink_id else None
    )
    attempt_ref = (
        db.collection("invoice_payment_attempts").document(reference)
        if invoice_id else None
    )

    now = _now()

    @firestore.transactional
    def apply_payment(transaction):
        marker_snapshot = next(transaction.get(marker_ref))
        payment_snapshot = next(transaction.get(payment_ref))

        marker_data = (
            marker_snapshot.to_dict() or {}
            if marker_snapshot.exists
            else {}
        )

        # A successful marker is not enough on its own. Recover the payment
        # document and repair invoice/attempt state before returning success.
        if (
            marker_snapshot.exists
            and marker_data.get("status") == "success"
        ):
            existing_payment = (
                payment_snapshot.to_dict()
                if payment_snapshot.exists
                else marker_data.get("payment_record")
            )

            if not isinstance(existing_payment, dict):
                return _review_result("successful_marker_missing_payment")

            return _reconcile_existing_success(
                transaction=transaction,
                reference=reference,
                existing_payment=existing_payment,
                marker_data=marker_data,
                metadata=metadata,
                now=now,
            )

        # If the payment exists but its marker was lost, recover it without
        # incrementing merchant earnings a second time.
        if (
            payment_snapshot.exists
            and (payment_snapshot.to_dict() or {}).get("status") == "success"
        ):
            return _reconcile_existing_success(
                transaction=transaction,
                reference=reference,
                existing_payment=payment_snapshot.to_dict() or {},
                marker_data=marker_data,
                metadata=metadata,
                now=now,
            )

        # A prior review_required marker is intentionally re-evaluated.
        # Other non-success markers may be re-evaluated too, so a previous
        # transient mismatch cannot permanently suppress a real charge.
        user_snapshot = next(transaction.get(user_ref))

        invoice_snapshot = (
            next(transaction.get(invoice_ref))
            if invoice_ref is not None
            else None
        )
        paylink_snapshot = (
            next(transaction.get(paylink_ref))
            if paylink_ref is not None
            else None
        )
        paylink_tx_snapshot = (
            next(transaction.get(paylink_tx_ref))
            if paylink_tx_ref is not None
            else None
        )
        attempt_snapshot = (
            next(transaction.get(attempt_ref))
            if attempt_ref is not None
            else None
        )

        if not user_snapshot.exists:
            return _write_review_marker(
                transaction, marker_ref, reference,
                "merchant_not_found", now, marker_data,
            )

        user_data = user_snapshot.to_dict() or {}
        fee_payer = "client"
        merchant_amount = gross_amount
        payout_type = "invoice" if invoice_id else "paylink"
        source_id = str(invoice_id or paylink_id)

        if invoice_id:
            if not invoice_snapshot or not invoice_snapshot.exists:
                return _write_review_marker(
                    transaction, marker_ref, reference,
                    "invoice_not_found", now, marker_data,
                )

            invoice_data = invoice_snapshot.to_dict() or {}

            if invoice_data.get("sender_id") != user_id:
                return _write_review_marker(
                    transaction, marker_ref, reference,
                    "invoice_owner_mismatch", now, marker_data,
                )

            if invoice_data.get("status") == "paid":
                existing_reference = (
                    invoice_data.get("paystack_reference")
                    or invoice_data.get("transaction_reference")
                )

                if existing_reference == reference:
                    # Same payment reference; repair its missing records
                    # only if an existing successful payment can be found.
                    return _write_review_marker(
                        transaction, marker_ref, reference,
                        "invoice_paid_but_payment_record_missing",
                        now, marker_data,
                    )

                return _write_review_marker(
                    transaction, marker_ref, reference,
                    "invoice_already_paid_by_another_reference",
                    now, marker_data,
                )

            fee_payer = "merchant"

            if attempt_snapshot and attempt_snapshot.exists:
                attempt_data = attempt_snapshot.to_dict() or {}

                if (
                    attempt_data.get("invoice_id") != str(invoice_id)
                    or attempt_data.get("user_id") != user_id
                ):
                    return _write_review_marker(
                        transaction, marker_ref, reference,
                        "invoice_attempt_owner_or_source_mismatch",
                        now, marker_data,
                    )

                attempt_currency = str(
                    attempt_data.get("currency") or ""
                ).upper()

                if attempt_currency != currency:
                    return _write_review_marker(
                        transaction, marker_ref, reference,
                        "invoice_attempt_currency_mismatch",
                        now, marker_data,
                    )

                if attempt_data.get("status") not in SUCCESS_ATTEMPT_STATES:
                    return _write_review_marker(
                        transaction, marker_ref, reference,
                        "invoice_attempt_not_payable",
                        now, marker_data,
                    )

                try:
                    expected_charge_kobo = int(
                        attempt_data["expected_charge_kobo"]
                    )
                    actual_charge_kobo = int(Decimal(str(data["amount"])))
                    merchant_amount_kobo = int(
                        attempt_data["merchant_amount_kobo"]
                    )
                    invoice_amount_kobo = _naira_to_kobo(
                        invoice_data.get("amount")
                    )
                except (
                    KeyError, ValueError, TypeError, InvalidOperation
                ):
                    return _write_review_marker(
                        transaction, marker_ref, reference,
                        "invalid_invoice_payment_attempt_amount",
                        now, marker_data,
                    )

                if (
                    expected_charge_kobo != actual_charge_kobo
                    or merchant_amount_kobo != invoice_amount_kobo
                    or merchant_amount_kobo > actual_charge_kobo
                ):
                    return _write_review_marker(
                        transaction, marker_ref, reference,
                        "invoice_attempt_amount_mismatch",
                        now, marker_data,
                    )

                fee_payer = _normalize_fee_payer(
                    attempt_data.get("fee_payer")
                )
                merchant_amount = merchant_amount_kobo / 100

            else:
                # Legacy compatibility: this branch is intentionally
                # restricted to invoices created by the older checkout flow.
                stored_reference = invoice_data.get("paystack_reference")

                if stored_reference and stored_reference != reference:
                    return _write_review_marker(
                        transaction, marker_ref, reference,
                        "invoice_reference_mismatch",
                        now, marker_data,
                    )

                try:
                    expected_kobo = _naira_to_kobo(
                        invoice_data.get("amount")
                    )
                    actual_kobo = int(Decimal(str(data["amount"])))
                except (
                    ValueError, TypeError, InvalidOperation
                ):
                    return _write_review_marker(
                        transaction, marker_ref, reference,
                        "invalid_legacy_invoice_amount",
                        now, marker_data,
                    )

                if expected_kobo != actual_kobo:
                    return _write_review_marker(
                        transaction, marker_ref, reference,
                        "legacy_invoice_amount_mismatch",
                        now, marker_data,
                    )

                merchant_amount = expected_kobo / 100

        else:
            if not paylink_snapshot or not paylink_snapshot.exists:
                return _write_review_marker(
                    transaction, marker_ref, reference,
                    "paylink_not_found", now, marker_data,
                )

            if not paylink_tx_snapshot or not paylink_tx_snapshot.exists:
                return _write_review_marker(
                    transaction, marker_ref, reference,
                    "paylink_transaction_not_found", now, marker_data,
                )

            paylink_data = paylink_snapshot.to_dict() or {}
            tx_data = paylink_tx_snapshot.to_dict() or {}

            if paylink_data.get("user_id") != user_id:
                return _write_review_marker(
                    transaction, marker_ref, reference,
                    "paylink_owner_mismatch", now, marker_data,
                )

            if (
                tx_data.get("user_id") != user_id
                or tx_data.get("paylink_id") != str(paylink_id)
            ):
                return _write_review_marker(
                    transaction, marker_ref, reference,
                    "paylink_transaction_mismatch", now, marker_data,
                )

            stored_reference = tx_data.get("paystack_reference")

            if stored_reference and stored_reference != reference:
                return _write_review_marker(
                    transaction, marker_ref, reference,
                    "paylink_reference_mismatch", now, marker_data,
                )

            try:
                expected_gross_kobo = _naira_to_kobo(
                    tx_data.get("amount_paid")
                )
                actual_gross_kobo = int(Decimal(str(data["amount"])))
                merchant_amount = _safe_amount(
                    tx_data.get("amount_requested"),
                    default=-1,
                )
                merchant_amount_kobo = _naira_to_kobo(merchant_amount)
            except (ValueError, TypeError, InvalidOperation):
                return _write_review_marker(
                    transaction, marker_ref, reference,
                    "invalid_paylink_amount", now, marker_data,
                )

            if expected_gross_kobo != actual_gross_kobo:
                return _write_review_marker(
                    transaction, marker_ref, reference,
                    "paylink_amount_mismatch", now, marker_data,
                )

            if merchant_amount_kobo > actual_gross_kobo:
                return _write_review_marker(
                    transaction, marker_ref, reference,
                    "merchant_amount_exceeds_payment", now, marker_data,
                )

        source_data = (
            invoice_data if invoice_id else paylink_data
        )
        subaccount_code = (
            source_data.get("paystack_subaccount_code")
            or user_data.get("paystack_subaccount_code")
        )
        manual_payout = not bool(subaccount_code)

        payment = _payment_record(
            reference=reference,
            user_id=str(user_id),
            invoice_id=str(invoice_id) if invoice_id else None,
            paylink_id=str(paylink_id) if paylink_id else None,
            amount=gross_amount,
            user_share=merchant_amount,
            currency=currency,
            channel=data.get("channel"),
            data=data,
            event=event,
            fee_payer=fee_payer,
        )

        # All required reads have occurred. Commit payment accounting
        # atomically so duplicate webhook deliveries cannot double-earn.
        transaction.set(payment_ref, payment)
        transaction.set(marker_ref, {
            "status": "success",
            "reference": reference,
            "user_id": str(user_id),
            "payment_record": payment,
            "payout_type": payout_type,
            "source_id": source_id,
            "manual_payout": manual_payout,
            "created_at": now,
            "updated_at": now,
        })

        transaction.update(user_ref, {
            "total_earned": firestore.Increment(merchant_amount),
            "updated_at": now,
        })

        if invoice_id:
            transaction.update(invoice_ref, {
                "status": "paid",
                "paid_at": now,
                "paystack_reference": reference,
                "transaction_reference": reference,
                "payout_status": (
                    "payout_pending"
                    if manual_payout
                    else "processing_by_paystack"
                ),
                "updated_at": now,
            })

            if attempt_snapshot and attempt_snapshot.exists:
                transaction.update(attempt_ref, {
                    "status": "success",
                    "paid_at": now,
                    "updated_at": now,
                })

        else:
            transaction.update(paylink_tx_ref, {
                "status": "success",
                "paid_at": now,
                "paystack_reference": reference,
                "payout_status": (
                    "payout_pending"
                    if manual_payout
                    else "processing_by_paystack"
                ),
                "updated_at": now,
            })

            transaction.update(paylink_ref, {
                "total_received": firestore.Increment(merchant_amount),
                "total_transactions": firestore.Increment(1),
                "last_payment_at": now,
                "updated_at": now,
            })

        return {
            "processed": True,
            "reason": "payment_recorded",
            "queue_payout": True,
            "user_id": str(user_id),
            "amount": merchant_amount,
            "payout_type": payout_type,
            "source_id": source_id,
            "manual_payout": manual_payout,
        }

    result = apply_payment(db.transaction())

    if result.get("queue_payout"):
        try:
            _record_payout(
                user_id=result["user_id"],
                amount=float(result["amount"]),
                reference=reference,
                payout_type=result["payout_type"],
                manual_payout=bool(result.get("manual_payout", False)),
                source_id=result.get("source_id"),
            )
        except Exception as exc:
            logger.exception(
                "Payment %s recorded but payout history failed",
                reference,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Payment recorded; payout history requires retry",
            ) from exc

    if result.get("requires_review"):
        logger.error(
            "Successful Paystack charge requires reconciliation: "
            "reference=%s reason=%s",
            reference,
            result.get("reason"),
        )

    return result


# ============================================================
# FAILED MERCHANT PAYMENTS
# ============================================================

def _process_failed_merchant_payment(
    event: str,
    data: dict,
    reference: str,
) -> dict:
    metadata = _metadata(data)
    user_id = metadata.get("user_id")
    invoice_id = metadata.get("invoice_id")
    paylink_id = metadata.get("paylink_id")

    if not user_id or bool(invoice_id) == bool(paylink_id):
        return {
            "processed": False,
            "reason": "missing_or_ambiguous_merchant_metadata",
        }

    try:
        amount = _amount_from_kobo(data.get("amount"))
    except (ValueError, TypeError):
        amount = 0.0

    payment_ref = db.collection("payments").document(reference)
    user_ref = db.collection("users").document(str(user_id))
    invoice_ref = (
        db.collection("invoices").document(str(invoice_id))
        if invoice_id else None
    )
    paylink_ref = (
        db.collection("paylinks").document(str(paylink_id))
        if paylink_id else None
    )
    attempt_ref = (
        db.collection("invoice_payment_attempts").document(reference)
        if invoice_id else None
    )
    now = _now()

    @firestore.transactional
    def record_failure(transaction):
        existing = next(transaction.get(payment_ref))

        if existing.exists:
            existing_data = existing.to_dict() or {}

            if existing_data.get("status") in {"success", "failed"}:
                return {
                    "created": False,
                    "reason": "already_handled",
                }

        user_snapshot = next(transaction.get(user_ref))
        source_snapshot = (
            next(transaction.get(invoice_ref))
            if invoice_ref is not None
            else next(transaction.get(paylink_ref))
        )
        attempt_snapshot = (
            next(transaction.get(attempt_ref))
            if attempt_ref is not None
            else None
        )

        if not user_snapshot.exists or not source_snapshot.exists:
            return {
                "created": False,
                "reason": "failure_source_not_found",
            }

        source_data = source_snapshot.to_dict() or {}

        if invoice_id:
            if source_data.get("sender_id") != user_id:
                return {
                    "created": False,
                    "reason": "failed_invoice_owner_mismatch",
                }

            fee_payer = "merchant"

            if attempt_snapshot and attempt_snapshot.exists:
                attempt_data = attempt_snapshot.to_dict() or {}

                if (
                    attempt_data.get("invoice_id") != str(invoice_id)
                    or attempt_data.get("user_id") != user_id
                ):
                    return {
                        "created": False,
                        "reason": "failed_invoice_attempt_mismatch",
                    }

                fee_payer = _normalize_fee_payer(
                    attempt_data.get("fee_payer")
                )
        else:
            if source_data.get("user_id") != user_id:
                return {
                    "created": False,
                    "reason": "failed_paylink_owner_mismatch",
                }

            fee_payer = "client"

        customer = data.get("customer")
        customer = customer if isinstance(customer, dict) else {}

        payment = {
            "_id": reference,
            "user_id": str(user_id),
            "invoice_id": str(invoice_id) if invoice_id else None,
            "paylink_id": str(paylink_id) if paylink_id else None,
            "paystack_reference": reference,
            "amount": amount,
            "user_share": 0,
            "currency": str(data.get("currency") or "NGN").upper(),
            "status": "failed",
            "channel": data.get("channel"),
            "client_phone": (
                metadata.get("payer_phone") or customer.get("phone")
            ),
            "client_email": _customer_email(data),
            "fee_payer": fee_payer,
            "paid_at": None,
            "created_at": now,
            "updated_at": now,
            "failure_message": data.get("gateway_response"),
            "raw_event": event,
        }

        transaction.set(payment_ref, payment)
        return {
            "created": True,
            "reason": "failed_charge_recorded",
        }

    result = record_failure(db.transaction())

    if result.get("created"):
        _create_payment_notification(
            reference=reference,
            user_id=str(user_id),
            title="Payment Attempt Failed",
            message=(
                "A payment attempt was unsuccessful. "
                "No merchant earnings were recorded."
            ),
            notification_type="payment_failed",
        )

    return {
        "processed": result.get("created", False),
        "reason": result.get("reason"),
    }


# ============================================================
# PAYSTACK TRANSFER EVENTS
# ============================================================

def _process_transfer_event(event: str, data: dict) -> dict:
    reference = _reference(data)

    if not reference:
        return {
            "processed": False,
            "reason": "missing_transfer_reference",
        }

    payout_ref = db.collection("payouts").document(reference)
    now = _now()

    status_by_event = {
        "transfer.success": "settled",
        "transfer.failed": "failed",
        "transfer.reversed": "reversed",
    }
    new_status = status_by_event[event]

    @firestore.transactional
    def update_transfer(transaction):
        payout_snapshot = next(transaction.get(payout_ref))

        if not payout_snapshot.exists:
            return {
                "processed": False,
                "reason": "payout_not_found",
            }

        payout_data = payout_snapshot.to_dict() or {}
        current_status = payout_data.get("status")

        # Do not let delayed events regress a settled payout.
        if current_status == "settled" and new_status != "reversed":
            return {
                "processed": False,
                "reason": "payout_already_settled",
                "status": current_status,
            }

        if current_status == "reversed" and new_status != "reversed":
            return {
                "processed": False,
                "reason": "payout_already_reversed",
                "status": current_status,
            }

        source_id = payout_data.get("source_id")
        payout_type = payout_data.get("type", "paylink")

        if payout_type == "invoice" and source_id:
            source_ref = db.collection("invoices").document(str(source_id))
        else:
            source_ref = (
                db.collection("paylink_transactions").document(reference)
            )

        source_snapshot = next(transaction.get(source_ref))

        transaction.update(payout_ref, {
            "status": new_status,
            "transfer_event": event,
            "transfer_status_updated_at": now,
            "transfer_failure_reason": (
                data.get("reason") if event != "transfer.success" else None
            ),
        })

        if source_snapshot.exists:
            transaction.update(source_ref, {
                "payout_status": new_status,
                "updated_at": now,
            })

        return {
            "processed": True,
            "reason": "transfer_status_updated",
            "status": new_status,
        }

    result = update_transfer(db.transaction())

    if not result.get("processed"):
        logger.warning(
            "Transfer event %s not applied to %s: %s",
            event,
            reference,
            result.get("reason"),
        )

    return result


# ============================================================
# CANONICAL PAYSTACK WEBHOOK
# URL: /api/webhooks/paystack if the app mounts this router at /api
# ============================================================

@router.post("/paystack")
async def paystack_webhook(request: Request):
    payload = await request.body()
    signature = request.headers.get("x-paystack-signature")

    if not _verify_signature(payload, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Paystack signature",
        )

    try:
        body = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    if not isinstance(body, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook payload",
        )

    event = body.get("event")
    data = body.get("data") or {}

    if not isinstance(event, str) or not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook structure",
        )

    logger.info("Paystack webhook received: %s", event)

    # 1. Subscription events.
    if _is_subscription_event(event, data):
        try:
            handled = handle_subscription_event(event, data)
        except Exception as exc:
            logger.exception("Subscription webhook processing failed")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Subscription event processing failed",
            ) from exc

        if not handled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Subscription event was not processed",
            )

        return {
            "status": "success",
            "event": event,
            "type": "subscription",
        }

    # 2. Transfer events.
    if event in TRANSFER_EVENTS:
        try:
            result = _process_transfer_event(event, data)
        except Exception as exc:
            logger.exception("Transfer webhook processing failed")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Transfer event processing failed",
            ) from exc

        return {
            "status": "success",
            "event": event,
            "result": result,
        }

    # 3. Merchant payment events.
    if event in {"charge.success", "charge.failed"}:
        reference = _reference(data)

        if not reference:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing payment reference",
            )

        if event == "charge.success":
            try:
                result = await _process_merchant_payment(
                    event=event,
                    data=data,
                    reference=reference,
                )
            except HTTPException:
                raise
            except Exception as exc:
                logger.exception(
                    "Successful payment processing failed for %s",
                    reference,
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Payment processing failed",
                ) from exc

            if result.get("requires_review"):
                # A verified charge must not be treated as fully reconciled
                # merely because its webhook was received successfully.
                # Return a retryable response while reconciliation is pending.
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=(
                        "Payment requires reconciliation; "
                        "retry processing later"
                    ),
                )

            if result.get("queue_payout"):
                metadata = _metadata(data)
                payer_name = (
                    metadata.get("payer_name")
                    or metadata.get("customer_name")
                    or "Your customer"
                )

                _create_payment_notification(
                    reference=reference,
                    user_id=result["user_id"],
                    title="Payment Received!",
                    message=(
                        f"{payer_name} paid "
                        f"₦{float(result['amount']):,.2f}. "
                        "Your payment has been recorded and settlement "
                        "is being processed."
                    ),
                    notification_type="payment_received",
                )
                
            try:
                payment_snapshot = (
                    db.collection("payments").document(reference).get()
                )
                payment_data = (
                    payment_snapshot.to_dict()
                    if payment_snapshot.exists
                    else {}
                )
                await dispatch_payment_receipts(
                    user_id=result["user_id"],
                    reference=reference,
                    amount=float(result["amount"]),
                    payment_data=payment_data,
                )
            except Exception:
                logger.exception(
                    "Receipt dispatch failed for %s; payment remains recorded",
                    reference,
                )

            return {
                "status": "success",
                "event": event,
                "result": result,
            }

        # charge.failed
        try:
            result = _process_failed_merchant_payment(
                event=event,
                data=data,
                reference=reference,
            )
        except Exception as exc:
            logger.exception(
                "Failed-charge processing failed for %s",
                reference,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed-charge processing failed",
            ) from exc

        return {
            "status": "success",
            "event": event,
            "result": result,
        }

    # 4. Ignore unsupported events.
    logger.info("Ignoring unsupported Paystack event: %s", event)

    return {
        "status": "success",
        "event": event,
        "message": "Event ignored",
    }
