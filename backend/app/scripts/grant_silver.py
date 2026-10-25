"""
Manually grant Silver access to a user.

Usage:
    python -m app.scripts.grant_silver email@example.com
    python -m app.scripts.grant_silver email@example.com --days 90
    python -m app.scripts.grant_silver email@example.com --days 365
"""

import argparse
import logging
from datetime import datetime, timedelta, timezone

from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.firebase import db

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("payla.grant_silver")

def grant_silver(email: str, days: int = 30):
    email = email.lower().strip()
    
    logger.info(f"Searching for user: {email}")
    
    # 1. Find the user
    users = list(
        db.collection("users")
        .where(filter=FieldFilter("email", "==", email))
        .limit(1)
        .stream()
    )
    
    if not users:
        logger.error(f"User with email {email} not found.")
        return False
        
    user_doc = users[0]
    user_id = user_doc.id
    user_data = user_doc.to_dict() or {}
    
    now = datetime.now(timezone.utc)
    sub_end = now + timedelta(days=days)
    
    # 2. Prepare the update
    updates = {
        "plan": "silver",
        "subscription_status": "active",
        "subscription_end": sub_end,
        "next_billing_date": sub_end,
        "plan_start_date": now,
        "cancel_at_period_end": False,
        "manual_silver_override": False, # Using actual dates, not the override flag
        "updated_at": now
    }
    
    # 3. Update Firestore
    try:
        db.collection("users").document(user_id).update(updates)
        logger.info(f"✅ Successfully granted Silver to {email} (@{user_data.get('username', 'unknown')})")
        logger.info(f"   Expires: {sub_end.isoformat()}")
        logger.info(f"   Duration: {days} days")
        return True
    except Exception as e:
        logger.error(f"Failed to update user: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Grant Silver access to a user.")
    parser.add_argument("email", help="The email address of the user")
    parser.add_argument(
        "--days", 
        type=int, 
        default=30, 
        help="Number of days to grant Silver for (default: 30)"
    )
    
    args = parser.parse_args()
    grant_silver(args.email, args.days)