# tasks/check_trials.py
from datetime import datetime
from app.core.firebase import db
import logging

logger = logging.getLogger("payla")

def check_expired_trials():
    now = datetime.utcnow()
    expired_users = (
        db.collection("users")
        .where("plan", "==", "free-trial")
        .where("trial_end_date", "<=", now)
        .stream()
    )

    count = 0
    for user_doc in expired_users:
        user_id = user_doc.id
        db.collection("users").document(user_id).update({
            "plan": "monthly",  # Auto-upgrade to prompt payment
            "updated_at": now
        })
        logger.info(f"Trial expired for user {user_id} → set to monthly")
        count += 1

    logger.info(f"check_expired_trials: {count} users upgraded")