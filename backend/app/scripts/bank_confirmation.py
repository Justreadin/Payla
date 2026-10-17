import sys
from pathlib import Path
from datetime import datetime, timezone
from app.core.firebase import db
from app.utils.name_match import match_name

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))


def backfill_bank_confirmations():
    users = db.collection("users").stream()
    count = 0
    skipped = 0

    for user_doc in users:
        user = user_doc.to_dict() or {}
        user_id = user_doc.id

        # Skip users who already have trust fields
        if user.get("bank_confirmed_name"):
            skipped += 1
            continue

        # We need the resolve data from the payout save
        account_name = user.get("payout_account_name")
        bank_name = user.get("payout_bank_name")
        account_number = user.get("payout_account_number")

        if not account_name or not bank_name or not account_number:
            print(f"SKIP {user_id}: incomplete payout data")
            skipped += 1
            continue

        status = match_name(user.get("full_name"), account_name)
        now = datetime.now(timezone.utc)

        trust_updates = {
            "bank_confirmation_status": status,
            "bank_confirmed_name": account_name,
            "bank_confirmed_bank_name": bank_name,
            "bank_confirmed_account_last4": account_number[-4:],
            "bank_confirmed_at": now,
            "bank_confirmation_attempted_at": now,
            "bank_confirmation_retry_count": 0,
        }

        db.collection("users").document(user_id).update(trust_updates)

        # Mirror to paylink doc
        paylink_ref = db.collection("paylinks").document(user_id)
        if paylink_ref.get().exists:
            paylink_ref.update({
                "bank_confirmation_status": status,
                "bank_confirmed_name": account_name,
                "bank_confirmed_bank_name": bank_name,
                "bank_confirmed_account_last4": account_number[-4:],
            })

        print(f"BACKFILLED {user_id}: status={status}")
        count += 1

    print(f"\nDone. {count} users backfilled, {skipped} skipped.")

# Run once
backfill_bank_confirmations()