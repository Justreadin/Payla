"""
Payment + receipt integration test.

Seeds a Silver creator, their paylink, an invoice, and a payment
attempt. Simulates the webhook route's full sequence:
  1. _process_merchant_payment records the charge
  2. _create_payment_notification creates the in-app notification
  3. dispatch_payment_receipts fires the creator receipt

Asserts every side effect landed:
  - payment document written with the correct user_share
  - invoice flipped to paid
  - payment attempt closed
  - payout history created
  - user.total_earned and total_invoice_revenue incremented
  - in-app notification written
  - receipt marker written on the payment document
  - firing the same event again is idempotent

Run:
    python -m app.scripts.test_payment_receipt

Requires:
    PAYLA_FIREBASE_KEY in .env.
"""

import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure the backend root is importable regardless of CWD.
BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.firebase import db
from app.routers.webhooks import (
    _create_payment_notification,
    _process_merchant_payment,
)
from app.services import receipt_service
from app.services.receipt_service import dispatch_payment_receipts


# ── Test fixtures ──

TEST_SUFFIX = uuid.uuid4().hex[:8]
TEST_USER_ID = f"test_pay_{TEST_SUFFIX}"
TEST_USERNAME = f"payu{TEST_SUFFIX[:6]}"
TEST_EMAIL = f"{TEST_USERNAME}@test.payla.invalid"

TEST_INVOICE_ID = f"inv_test_{TEST_SUFFIX}"
TEST_REFERENCE = f"test_charge_{TEST_SUFFIX}"
TEST_ATTEMPT_ID = TEST_REFERENCE  # attempts use the reference as doc id

INVOICE_AMOUNT_NGN = 5000.00
INVOICE_AMOUNT_KOBO = int(INVOICE_AMOUNT_NGN * 100)


# ── Seed and cleanup ──

def seed():
    """Create user, paylink, invoice, and payment attempt documents."""
    now = datetime.now(timezone.utc)

    user_doc = {
        "_id": TEST_USER_ID,
        "firebase_uid": TEST_USER_ID,
        "full_name": "Test Pay User",
        "business_name": "Test Pay Co",
        "email": TEST_EMAIL,
        "email_verified": True,
        "username": TEST_USERNAME,
        "onboarding_complete": True,
        "plan": "silver",
        "subscription_status": "active",
        "subscription_end": now + timedelta(days=7),
        "preferred_domain": "ng",
        "manual_silver_override": False,
        "total_earned": 0.0,
        "total_invoice_revenue": 0.0,
        "total_paylink_revenue": 0.0,
        "paystack_subaccount_code": "ACCT_test_123",
        "created_at": now,
        "updated_at": now,
    }

    paylink_doc = {
        "user_id": TEST_USER_ID,
        "username": TEST_USERNAME,
        "display_name": "Test Pay Co",
        "description": "Your Payment Identity.",
        "currency": "NGN",
        "active": True,
        "link_url": f"https://payla.ng/@{TEST_USERNAME}",
        "preferred_domain": "ng",
        "paystack_subaccount_code": "ACCT_test_123",
        "total_received": 0.0,
        "total_transactions": 0,
        "created_at": now,
        "updated_at": now,
    }

    invoice_doc = {
        "sender_id": TEST_USER_ID,
        "sender_business_name": "Test Pay Co",
        "sender_phone": "+2348000000000",
        "amount": INVOICE_AMOUNT_NGN,
        "currency": "NGN",
        "description": "Test invoice",
        "due_date": now + timedelta(days=7),
        "client_phone": "",
        "client_email": "client@test.payla.invalid",
        "client_name": "Test Client",
        "status": "pending",
        "invoice_url": f"https://payla.ng/i/test_{TEST_SUFFIX}",
        "fee_payer": "merchant",
        "paystack_subaccount_code": "ACCT_test_123",
        "expected_charge_kobo": INVOICE_AMOUNT_KOBO,
        "merchant_amount_kobo": INVOICE_AMOUNT_KOBO,
        "created_at": now,
        "updated_at": now,
    }

    attempt_doc = {
        "reference": TEST_REFERENCE,
        "invoice_id": TEST_INVOICE_ID,
        "user_id": TEST_USER_ID,
        "expected_charge_kobo": INVOICE_AMOUNT_KOBO,
        "merchant_amount_kobo": INVOICE_AMOUNT_KOBO,
        "estimated_fee_kobo": 0,
        "fee_payer": "merchant",
        "currency": "NGN",
        "status": "initialized",
        "payer_email": "client@test.payla.invalid",
        "authorization_url": "https://checkout.paystack.com/test",
        "created_at": now,
        "updated_at": now,
    }

    db.collection("users").document(TEST_USER_ID).set(user_doc)
    db.collection("paylinks").document(TEST_USER_ID).set(paylink_doc)
    db.collection("invoices").document(TEST_INVOICE_ID).set(invoice_doc)
    db.collection("invoice_payment_attempts").document(TEST_ATTEMPT_ID).set(
        attempt_doc
    )

    print(
        f"Seeded user {TEST_USER_ID} (@{TEST_USERNAME}) "
        f"with invoice {TEST_INVOICE_ID}"
    )
    print(
        f"  Amount: ₦{INVOICE_AMOUNT_NGN:,.2f} "
        f"({INVOICE_AMOUNT_KOBO} kobo)"
    )
    print(f"  Reference: {TEST_REFERENCE}")


def cleanup():
    """Delete every document the test created."""
    docs_to_delete = [
        ("users", TEST_USER_ID),
        ("paylinks", TEST_USER_ID),
        ("invoices", TEST_INVOICE_ID),
        ("invoice_payment_attempts", TEST_ATTEMPT_ID),
        ("payments", TEST_REFERENCE),
        ("payouts", TEST_REFERENCE),
        ("processed_merchant_payments", TEST_REFERENCE),
        ("notifications", f"payment_{TEST_REFERENCE}_payment_received"),
    ]

    for collection, doc_id in docs_to_delete:
        try:
            db.collection(collection).document(doc_id).delete()
        except Exception:
            pass

    print(f"Cleaned up test data for {TEST_USER_ID}")


# ── Webhook payload ──

def build_charge_success_payload() -> tuple[str, dict, str]:
    """Build a realistic charge.success event for the seeded invoice."""
    return (
        "charge.success",
        {
            "id": 1234567890,
            "reference": TEST_REFERENCE,
            "status": "success",
            "amount": INVOICE_AMOUNT_KOBO,
            "currency": "NGN",
            "channel": "card",
            "paid_at": datetime.now(timezone.utc).isoformat(),
            "customer": {
                "email": "client@test.payla.invalid",
                "customer_code": "CUS_test_client",
            },
            "metadata": {
                "invoice_id": TEST_INVOICE_ID,
                "user_id": TEST_USER_ID,
                "type": "invoice",
                "payer_email": "client@test.payla.invalid",
                "payer_name": "Test Client",
                "fee_payer": "merchant",
                "invoice_amount_kobo": INVOICE_AMOUNT_KOBO,
            },
        },
        TEST_REFERENCE,
    )


# ── Read helpers ──

def read(collection: str, doc_id: str) -> dict:
    snap = db.collection(collection).document(doc_id).get()
    return snap.to_dict() or {} if snap.exists else {}


def check(label: str, actual, expected) -> bool:
    ok = actual == expected
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}: expected={expected!r} actual={actual!r}")
    return ok


# ── Fake receipt sender ──

async def _fake_send_via_resend(to_email, subject, html, sender):
    """Stand-in for receipt_service._send_via_resend. Never hits Resend."""
    print(f"  [MOCK] receipt would send to {to_email} from {sender}")
    return True


# ── Main ──

def main() -> int:
    print("=" * 60)
    print("Payment + receipt integration test")
    print("=" * 60)

    all_passed = True

    try:
        seed()

        # ── Phase 1: record the payment ──
        print("\n[1] Process charge.success")
        event, data, reference = build_charge_success_payload()

        result = asyncio.run(
            _process_merchant_payment(
                event=event,
                data=data,
                reference=reference,
            )
        )
        print(f"  _process_merchant_payment returned: {result}")

        all_passed &= check("processed", result.get("processed"), True)
        all_passed &= check("reason", result.get("reason"), "payment_recorded")
        all_passed &= check("queue_payout", result.get("queue_payout"), True)
        all_passed &= check("amount", result.get("amount"), INVOICE_AMOUNT_NGN)

        # Simulate the notification side effect the webhook route
        # creates after _process_merchant_payment returns. The
        # transaction is decoupled from the notification by design,
        # so the test must call the notification function explicitly.
        if result.get("queue_payout"):
            metadata = data.get("metadata") or {}
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
            print("  Created in-app notification (mirrors webhook route)")

        # ── Phase 2: verify all the writes ──
        print("\n[2] Verify payment document")
        payment = read("payments", TEST_REFERENCE)
        all_passed &= check("payment.status", payment.get("status"), "success")
        all_passed &= check(
            "payment.user_id", payment.get("user_id"), TEST_USER_ID
        )
        all_passed &= check(
            "payment.invoice_id", payment.get("invoice_id"), TEST_INVOICE_ID
        )
        all_passed &= check(
            "payment.amount", payment.get("amount"), INVOICE_AMOUNT_NGN
        )
        all_passed &= check(
            "payment.user_share", payment.get("user_share"), INVOICE_AMOUNT_NGN
        )
        all_passed &= check("payment.currency", payment.get("currency"), "NGN")
        all_passed &= check(
            "payment.fee_payer", payment.get("fee_payer"), "merchant"
        )

        print("\n[3] Verify invoice state")
        invoice = read("invoices", TEST_INVOICE_ID)
        all_passed &= check("invoice.status", invoice.get("status"), "paid")
        all_passed &= check(
            "invoice.paystack_reference",
            invoice.get("paystack_reference"),
            TEST_REFERENCE,
        )
        all_passed &= check(
            "invoice.transaction_reference",
            invoice.get("transaction_reference"),
            TEST_REFERENCE,
        )
        all_passed &= check(
            "invoice.payout_status",
            invoice.get("payout_status"),
            "processing_by_paystack",
        )

        print("\n[4] Verify payment attempt closed")
        attempt = read("invoice_payment_attempts", TEST_ATTEMPT_ID)
        all_passed &= check("attempt.status", attempt.get("status"), "success")

        print("\n[5] Verify payout history")
        payout = read("payouts", TEST_REFERENCE)
        all_passed &= check("payout exists", bool(payout), True)
        all_passed &= check(
            "payout.user_id", payout.get("user_id"), TEST_USER_ID
        )
        all_passed &= check("payout.type", payout.get("type"), "invoice")
        all_passed &= check(
            "payout.amount", payout.get("amount"), INVOICE_AMOUNT_NGN
        )
        all_passed &= check(
            "payout.settlement_method",
            payout.get("settlement_method"),
            "paystack_subaccount",
        )

        print("\n[6] Verify user totals")
        user = read("users", TEST_USER_ID)
        all_passed &= check(
            "user.total_earned", user.get("total_earned"), INVOICE_AMOUNT_NGN
        )
        all_passed &= check(
            "user.total_invoice_revenue",
            user.get("total_invoice_revenue"),
            INVOICE_AMOUNT_NGN,
        )
        all_passed &= check(
            "user.total_paylink_revenue",
            user.get("total_paylink_revenue"),
            0.0,
        )

        print("\n[7] Verify in-app notification")
        notification = read(
            "notifications", f"payment_{TEST_REFERENCE}_payment_received"
        )
        all_passed &= check("notification exists", bool(notification), True)
        all_passed &= check(
            "notification.user_id", notification.get("user_id"), TEST_USER_ID
        )
        all_passed &= check(
            "notification.type",
            notification.get("type"),
            "payment_received",
        )

        # ── Phase 3: dispatch receipts ──
        print("\n[8] Dispatch payment receipts (mocked Resend)")
        original_sender = receipt_service._send_via_resend
        receipt_service._send_via_resend = _fake_send_via_resend

        try:
            receipt_result = asyncio.run(
                dispatch_payment_receipts(
                    user_id=TEST_USER_ID,
                    reference=TEST_REFERENCE,
                    amount=INVOICE_AMOUNT_NGN,
                    payment_data=payment,
                )
            )
            print(f"  dispatch_payment_receipts returned: {receipt_result}")
        finally:
            receipt_service._send_via_resend = original_sender

        all_passed &= check(
            "creator_alert_sent",
            receipt_result.get("creator_alert_sent"),
            True,
        )

        print("\n[9] Verify receipt marker on payment document")
        payment_after_receipt = read("payments", TEST_REFERENCE)
        all_passed &= check(
            "payment.receipt_sent_at present",
            bool(payment_after_receipt.get("receipt_sent_at")),
            True,
        )
        all_passed &= check(
            "payment.receipt_status",
            payment_after_receipt.get("receipt_status"),
            "sent",
        )

        # ── Phase 4: idempotency ──
        print("\n[10] Idempotency: fire the same charge again")
        result_again = asyncio.run(
            _process_merchant_payment(
                event=event,
                data=data,
                reference=reference,
            )
        )
        print(f"  second call returned: {result_again}")

        all_passed &= check(
            "second_processed", result_again.get("processed"), True
        )
        all_passed &= check(
            "second_reason",
            result_again.get("reason"),
            "recovered_existing_success",
        )

        user_after = read("users", TEST_USER_ID)
        all_passed &= check(
            "user.total_earned unchanged",
            user_after.get("total_earned"),
            INVOICE_AMOUNT_NGN,
        )
        all_passed &= check(
            "user.total_invoice_revenue unchanged",
            user_after.get("total_invoice_revenue"),
            INVOICE_AMOUNT_NGN,
        )

    finally:
        cleanup()

    print("\n" + "=" * 60)
    if all_passed:
        print("RESULT: ALL TESTS PASSED")
        print("=" * 60)
        return 0
    else:
        print("RESULT: SOME TESTS FAILED")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())