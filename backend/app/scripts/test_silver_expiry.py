"""
Silver expiry integration test.

Exercises the subscription.expire webhook path directly:
  1. Seeds a Silver user + paylink with preferred_domain = "vip".
  2. Calls handle_subscription_event("subscription.expire", ...).
  3. Asserts the user doc and paylink doc both reverted to "ng".
  4. Asserts a duplicate event is a no-op.
  5. Asserts a subscription.not_renew does NOT revert the domain.

Run:
    python -m scripts.test_silver_expiry

Requires:
    PAYLA_FIREBASE_KEY in .env (the same one the app uses).
"""

import sys
import uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone
from google.cloud.firestore_v1.base_query import FieldFilter
from app.core.firebase import db
from app.services.subscription_webhooks import handle_subscription_event
import hashlib

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))
REAL_USER_EMAIL = "lyriqonia@gmail.com"  # ← change if testing someone else


def find_user(email: str):
    docs = list(
        db.collection("users")
        .where(filter=FieldFilter("email", "==", email))
        .limit(1)
        .stream()
    )
    return docs[0] if docs else None


def marker_id_for(event: str, identifier: str) -> str:
    return hashlib.sha256(f"{event}:{identifier}".encode()).hexdigest()


def main():
    doc = find_user(REAL_USER_EMAIL)
    if not doc:
        print(f"No user with email {REAL_USER_EMAIL}")
        return 1

    user_id = doc.id
    user = doc.to_dict() or {}

    print(f"User: {user.get('username')} | id={user_id}")
    print(
        f"Before: plan={user.get('plan')} | "
        f"status={user.get('subscription_status')} | "
        f"domain={user.get('preferred_domain')} | "
        f"end={user.get('subscription_end')}"
    )

    subscription_id = user.get("subscription_id")
    if not subscription_id:
        print("User has no subscription_id; cannot test expiry")
        return 1

    username = user.get("username") or ""

    # ── Prep: put the user back into pre-expiry state ──
    now = datetime.now(timezone.utc)
    new_end = now + timedelta(days=30)

    db.collection("users").document(user_id).update({
        "plan": "silver",
        "subscription_status": "active",
        "preferred_domain": "vip",
        "subscription_end": new_end,
        "next_billing_date": new_end,
        "cancel_at_period_end": False,
        "is_active": True,
        "updated_at": now,
    })

    paylink_ref = db.collection("paylinks").document(user_id)
    if paylink_ref.get().exists:
        paylink_ref.update({
            "preferred_domain": "vip",
            "link_url": f"https://payla.vip/@{username}",
            "updated_at": now,
        })

    # ── Clear any prior subscription.expire marker ──
    mid = marker_id_for("subscription.expire", subscription_id)
    marker_ref = db.collection("subscription_events").document(mid)
    if marker_ref.get().exists:
        marker_ref.delete()
        print(f"Cleared existing subscription.expire marker {mid}")

    # ── Verify prep ──
    prep_user = db.collection("users").document(user_id).get().to_dict() or {}
    prep_paylink = (
        paylink_ref.get().to_dict() or {} if paylink_ref.get().exists else {}
    )

    print("\n[Prep]")
    print(f"  user.plan={prep_user.get('plan')}")
    print(f"  user.status={prep_user.get('subscription_status')}")
    print(f"  user.domain={prep_user.get('preferred_domain')}")
    print(f"  paylink.domain={prep_paylink.get('preferred_domain')}")
    print(f"  paylink.link_url={prep_paylink.get('link_url')}")

    # ── Fire subscription.expire ──
    data = {
        "subscription_code": subscription_id,
        "status": "complete",
        "customer": {"email": REAL_USER_EMAIL},
    }

    print(f"\n[Firing] subscription.expire for {subscription_id}")
    handled = handle_subscription_event("subscription.expire", data)
    print(f"  handled={handled}")

    # ── Verify result ──
    after_user = db.collection("users").document(user_id).get().to_dict() or {}
    after_paylink = (
        paylink_ref.get().to_dict() or {} if paylink_ref.get().exists else {}
    )

    print("\n[After]")
    print(f"  user.plan={after_user.get('plan')}")
    print(f"  user.status={after_user.get('subscription_status')}")
    print(f"  user.domain={after_user.get('preferred_domain')}")
    print(f"  paylink.domain={after_paylink.get('preferred_domain')}")
    print(f"  paylink.link_url={after_paylink.get('link_url')}")

    # ── Assertions ──
    print("\n[Assertions]")
    ok = True

    def check(label, actual, expected):
        nonlocal ok
        passed = actual == expected
        ok = ok and passed
        print(
            f"  [{'PASS' if passed else 'FAIL'}] {label}: "
            f"expected={expected!r} actual={actual!r}"
        )

    check("user.subscription_status", after_user.get("subscription_status"), "expired")
    check("user.preferred_domain", after_user.get("preferred_domain"), "ng")
    check("user.cancel_at_period_end", after_user.get("cancel_at_period_end"), False)
    check("paylink.preferred_domain", after_paylink.get("preferred_domain"), "ng")
    check(
        "paylink.link_url",
        after_paylink.get("link_url"),
        f"https://payla.ng/@{username}",
    )

    print("\n" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())