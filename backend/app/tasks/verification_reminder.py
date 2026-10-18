"""
Verification reminder: finds users who claimed a username or signed up
but never verified their email, and sends them a reminder.

Runs daily via worker.py. Idempotent: writes email_verified_reminder_sent_at
on each user document so a second run does not re-send.

Does not regenerate the verify_token. Both the original email and the
reminder should work. The user might check the older email first.

Dispatches a different reminder email based on signup_source:
  - founding -> send_founding_claim_reminder (username + Silver)
  - auth / null -> send_account_verification_reminder (plain)
"""

import logging
from datetime import datetime, timezone, timedelta

from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.firebase import db
from app.services.email_service import (
    send_founding_claim_reminder,
    send_account_verification_reminder,
)

logger = logging.getLogger("payla.verification_reminder")

REMINDER_THRESHOLD_HOURS = 72
REMINDER_MARKER = "email_verified_reminder_sent_at"
MAX_SENDS_PER_RUN = 200


def send_verification_reminders() -> dict:
    """
    Find users with email_verified: false, created more than 72 hours
    ago, that have not yet been reminded. Send the appropriate
    reminder email based on signup_source.

    Returns a summary dict for logging.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=REMINDER_THRESHOLD_HOURS)

    sent = 0
    skipped = 0
    failed = 0

    try:
        candidates = list(
            db.collection("users")
            .where(filter=FieldFilter("email_verified", "==", False))
            .where(filter=FieldFilter("created_at", "<", cutoff))
            .stream()
        )
    except Exception as exc:
        msg = str(exc)
        if "requires an index" in msg or "FAILED_PRECONDITION" in msg:
            logger.error(
                "Firestore composite index missing for "
                "(email_verified, created_at). Create it: %s",
                msg,
            )
        else:
            logger.exception("Verification reminder query failed")
        return {"sent": 0, "skipped": 0, "failed": 0, "error": "query"}

    logger.info(
        "Verification reminder: %d candidates older than %dh",
        len(candidates),
        REMINDER_THRESHOLD_HOURS,
    )

    for doc in candidates:
        if sent >= MAX_SENDS_PER_RUN:
            logger.warning(
                "Verification reminder hit per-run cap of %d, stopping. "
                "Remaining candidates will be processed on the next run.",
                MAX_SENDS_PER_RUN,
            )
            break

        data = doc.to_dict() or {}

        if data.get(REMINDER_MARKER):
            skipped += 1
            continue

        email = data.get("email")
        token = data.get("verify_token")
        username = data.get("username")
        source = data.get("signup_source") or "auth"

        if not email or not token:
            logger.warning(
                "Skipping reminder for user %s: missing email or token",
                doc.id,
            )
            skipped += 1
            continue

        if source == "founding" and not username:
            logger.warning(
                "Skipping founding reminder for user %s: no username",
                doc.id,
            )
            skipped += 1
            continue

        # Re-check immediately before sending: the user may have
        # verified between the query and now.
        try:
            fresh = db.collection("users").document(doc.id).get()
            fresh_data = fresh.to_dict() or {}
            if fresh_data.get("email_verified"):
                skipped += 1
                continue
            if fresh_data.get(REMINDER_MARKER):
                skipped += 1
                continue
            # Use the freshest token in case it was rotated.
            token = fresh_data.get("verify_token") or token
        except Exception:
            logger.exception(
                "Re-check failed for user %s, skipping", doc.id
            )
            skipped += 1
            continue

        try:
            if source == "founding":
                send_founding_claim_reminder(
                    email, token, username=username
                )
            else:
                send_account_verification_reminder(email, token)

            db.collection("users").document(doc.id).update({
                REMINDER_MARKER: now,
            })
            sent += 1
            logger.info(
                "Verification reminder sent to %s (source=%s)",
                email, source,
            )
        except Exception:
            logger.exception(
                "Verification reminder failed for %s", email
            )
            failed += 1

    logger.info(
        "Verification reminder complete: sent=%d skipped=%d failed=%d",
        sent, skipped, failed,
    )

    return {"sent": sent, "skipped": skipped, "failed": failed}