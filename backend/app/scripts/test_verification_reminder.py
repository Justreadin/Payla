"""
Test the verification reminder task against the live Firestore.

Usage:
    python -m app.scripts.test_verification_reminder

What it does:
    1. Runs the reminder query and reports how many candidates it finds.
    2. If the composite index is missing, prints Firestore's exact
       index-creation URL and exits. This is the fastest way to get
       the right index.
    3. If the index exists, runs the full reminder task. Prints a
       summary (sent/skipped/failed) and lists what was sent.

The test is read-only by default. It does NOT send emails unless you
pass --send. This protects against accidentally emailing real
abandoned users while you're just testing the query.

The test does NOT write the reminder marker. That way you can run it
repeatedly without affecting production state. The real cron will
write the marker when it actually sends.

    python -m app.scripts.test_verification_reminder --send

The --send flag actually sends emails and writes the marker. Only use
it against a test environment, or when you're certain the candidate
list is safe to email.
"""

import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

from google.api_core import exceptions as google_exceptions
from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.firebase import db
from app.tasks.verification_reminder import (
    REMINDER_THRESHOLD_HOURS,
    send_verification_reminders,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("payla.test_verification_reminder")


def run_query_only() -> list:
    """
    Run the reminder query without sending anything. Returns the list
    of candidate documents. Raises if Firestore errors.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(
        hours=REMINDER_THRESHOLD_HOURS
    )

    logger.info(
        "Querying users where email_verified == False "
        "AND created_at < %s",
        cutoff.isoformat(),
    )

    return list(
        db.collection("users")
        .where(filter=FieldFilter("email_verified", "==", False))
        .where(filter=FieldFilter("created_at", "<", cutoff))
        .stream()
    )


def describe_candidate(doc) -> str:
    data = doc.to_dict() or {}
    email = data.get("email", "<no email>")
    username = data.get("username") or "-"
    source = data.get("signup_source") or "auth"
    created = data.get("created_at")
    age_days = "-"
    if isinstance(created, datetime):
        age_days = f"{(datetime.now(timezone.utc) - created).days}d"

    return (
        f"  uid={doc.id[:12]}  "
        f"email={email}  "
        f"username=@{username}  "
        f"source={source}  "
        f"age={age_days}"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Test the verification reminder task."
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help=(
            "Actually send reminder emails and write the marker. "
            "Without this flag, the script only queries and reports."
        ),
    )
    args = parser.parse_args()

    logger.info("Verification reminder test starting")

    # Step 1: query. Catch the index error specifically.
    try:
        candidates = run_query_only()
    except google_exceptions.FailedPrecondition as exc:
        msg = str(exc)
        logger.error("Firestore rejected the query.")
        logger.error("")
        logger.error("=" * 70)
        logger.error("MISSING COMPOSITE INDEX")
        logger.error("=" * 70)
        logger.error("")
        logger.error(
            "Firestore requires a composite index for this query."
        )
        logger.error("")
        logger.error("The error message from Firestore is:")
        logger.error("")
        logger.error(msg)
        logger.error("")
        logger.error(
            "If the message above contains a URL, open it in your "
            "browser. It will take you directly to the index creation "
            "page with all fields pre-filled. Click Create. The build "
            "takes a few minutes."
        )
        logger.error("")
        logger.error("If no URL appears, create the index manually:")
        logger.error("  Collection: users")
        logger.error("  Field 1: email_verified  (Ascending)")
        logger.error("  Field 2: created_at      (Ascending)")
        logger.error("  Query scope: Collection")
        logger.error("=" * 70)
        sys.exit(1)
    except Exception:
        logger.exception("Query failed for a reason other than index")
        sys.exit(1)

    logger.info("Query succeeded.")
    logger.info("Candidates: %d", len(candidates))

    if not candidates:
        logger.info(
            "No abandoned signups older than %dh. Nothing to do.",
            REMINDER_THRESHOLD_HOURS,
        )
        return

    logger.info("")
    logger.info("Candidate list:")
    for doc in candidates:
        logger.info(describe_candidate(doc))
    logger.info("")

    if not args.send:
        logger.info(
            "Read-only mode. No emails sent, no marker written. "
            "Pass --send to actually run the task."
        )
        return

    # Step 2: run the full task. This is the real code path.
    logger.info("Running the full reminder task (emails will be sent)...")
    try:
        summary = send_verification_reminders()
    except Exception:
        logger.exception("Reminder task raised")
        sys.exit(1)

    logger.info("")
    logger.info("Summary: %s", summary)
    logger.info("")

    if summary.get("error"):
        logger.error(
            "Task reported an error: %s", summary["error"]
        )
        sys.exit(1)

    if summary.get("failed"):
        logger.warning(
            "%d email(s) failed. Check the logs above for details.",
            summary["failed"],
        )

    if summary.get("sent") == 0 and summary.get("skipped") == len(
        candidates
    ):
        logger.info(
            "All candidates were skipped. Most likely because "
            "email_verified_reminder_sent_at is already set on "
            "each, meaning they were reminded in a previous run."
        )

    logger.info("Verification reminder test complete.")


if __name__ == "__main__":
    main()