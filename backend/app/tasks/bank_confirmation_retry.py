"""
Payla — Scheduled bank-confirmation retry.

Runs every 4 hours. Picks up users whose bank confirmation is
'failed' or 'pending' and retries the Paystack account resolution.

Respects a 72-hour grace window: if the previous successful match
is still within the window, we do NOT downgrade the status even if
the current retry fails.
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from google.cloud.firestore_v1 import FieldFilter

from app.core.config import settings
from app.core.firebase import db
from app.utils.name_match import match_name


logger = logging.getLogger("payla.retry")

GRACE_HOURS = 72
RETRY_INTERVAL_HOURS = 4
BATCH_SIZE = 25
PAYSTACK_RESOLVE_TIMEOUT = 10


async def _resolve_account(
    bank_code: str,
    account_number: str,
) -> dict | None:
    """Call Paystack's resolve endpoint."""
    url = (
        f"https://api.paystack.co/bank/resolve"
        f"?account_number={account_number}&bank_code={bank_code}"
    )
    headers = {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
    }

    try:
        async with httpx.AsyncClient(
            timeout=PAYSTACK_RESOLVE_TIMEOUT
        ) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json().get("data")
    except Exception as exc:
        logger.warning(
            "Paystack resolve failed for bank=%s acct=%s: %s",
            bank_code,
            account_number[-4:] if account_number else "????",
            exc,
        )
        return None


def _ensure_utc(value):
    """Firestore sometimes returns naive datetimes. Coerce to UTC."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    return None


async def retry_bank_confirmation():
    """Main retry loop. Called by the scheduler."""
    now = datetime.now(timezone.utc)

    users_ref = db.collection("users")

    query = (
        users_ref
        .where(filter=FieldFilter(
            "bank_confirmation_status", "in", ["failed", "pending"]
        ))
        .limit(BATCH_SIZE)
    )

    try:
        candidates = list(query.stream())
    except Exception as exc:
        logger.error("Bank-confirmation query failed: %s", exc)
        return

    if not candidates:
        return

    logger.info(
        "Bank-confirmation retry: %d candidates",
        len(candidates),
    )

    for user_doc in candidates:
        user = user_doc.to_dict() or {}
        user_id = user_doc.id

        bank_code = (
            user.get("bank_code")
            or user.get("payout_bank_code")
        )
        account_number = (
            user.get("account_number")
            or user.get("payout_account_number")
        )

        if not bank_code or not account_number:
            # No account on file — cannot resolve. Leave status
            # as-is so the user still sees a tenure mark.
            continue

        # Skip if we already tried very recently
        attempted = _ensure_utc(
            user.get("bank_confirmation_attempted_at")
        )
        if attempted and (now - attempted) < timedelta(
            hours=RETRY_INTERVAL_HOURS
        ):
            continue

        resolved = await _resolve_account(bank_code, account_number)

        updates = {
            "bank_confirmation_attempted_at": now,
            "bank_confirmation_retry_count": (
                user.get("bank_confirmation_retry_count", 0) + 1
            ),
        }

        if resolved and resolved.get("account_name"):
            account_name = resolved["account_name"]
            status = match_name(user.get("full_name"), account_name)

            updates["bank_confirmation_status"] = status
            updates["bank_confirmed_name"] = account_name
            updates["bank_confirmed_at"] = now
            updates["bank_confirmed_bank_name"] = resolved.get("bank_name")
            updates["bank_confirmed_account_last4"] = (
                account_number[-4:]
            )
            updates["bank_confirmation_retry_count"] = 0

            logger.info(
                "User %s: bank name matched=%s",
                user_id,
                status,
            )
        else:
            # Lookup failed — check grace window
            last_confirmed = _ensure_utc(
                user.get("bank_confirmed_at")
            )

            if last_confirmed and (now - last_confirmed) < timedelta(
                hours=GRACE_HOURS
            ):
                logger.info(
                    "User %s: lookup failed but in grace window; "
                    "keeping previous status.",
                    user_id,
                )
                # Still record the attempt but do not change status
                db.collection("users").document(user_id).update({
                    "bank_confirmation_attempted_at": now,
                    "bank_confirmation_retry_count": updates[
                        "bank_confirmation_retry_count"
                    ],
                })
                continue

            updates["bank_confirmation_status"] = "failed"

            logger.info(
                "User %s: grace window expired, marked failed.",
                user_id,
            )

        # Apply to user doc
        try:
            db.collection("users").document(user_id).update(updates)
        except Exception as exc:
            logger.error(
                "Failed to update user %s: %s", user_id, exc
            )
            continue

        # Mirror to paylink doc
        try:
            paylink_ref = db.collection("paylinks").document(user_id)
            if paylink_ref.get().exists:
                paylink_ref.update({
                    k: v
                    for k, v in updates.items()
                    if k in (
                        "bank_confirmation_status",
                        "bank_confirmed_name",
                        "bank_confirmed_bank_name",
                        "bank_confirmed_account_last4",
                    )
                })
        except Exception as exc:
            logger.error(
                "Failed to mirror trust fields to paylink %s: %s",
                user_id,
                exc,
            )


_scheduler: AsyncIOScheduler | None = None


def start_scheduler():
    """Called from app startup."""
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        logger.info("Bank-confirmation scheduler already running.")
        return

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        retry_bank_confirmation,
        "interval",
        hours=RETRY_INTERVAL_HOURS,
        id="bank_confirmation_retry",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info(
        "Bank-confirmation retry scheduler started "
        "(interval: %dh).",
        RETRY_INTERVAL_HOURS,
    )


def stop_scheduler():
    """Called from app shutdown."""
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Bank-confirmation scheduler stopped.")