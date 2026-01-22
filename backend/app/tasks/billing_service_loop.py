# app/tasks/billing_loop.py
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from app.utils.billing_emails import BILLING_TEMPLATES, generate_billing_content
from app.services.billing_service import dispatch_billing_email # NEW INDEPENDENT SERVICE

db = firestore.client()
logger = logging.getLogger("payla.billing")

CHECK_INTERVAL = 3600 
BILLING_SENDER = "billing.noreply@payla.vip"

async def send_billing_email(user_id, user, template_key, new_status):
    """Handles the formatting and dispatch for billing only."""
    try:
        user_email = user.get("email")
        if not user_email:
            return

        context = {
            "user_name": (user.get("full_name") or "Creator").split()[0],
            "username": user.get("username") or "creator",
            "billing_url": "https://payla.ng/subscription",
        }

        html = generate_billing_content(template_key, context)
        subject = BILLING_TEMPLATES[template_key]["subject"].format(name=context["user_name"])

        # CALL THE INDEPENDENT DISPATCHER
        success = await dispatch_billing_email(
            to_email=user_email,
            subject=subject,
            html=html,
            sender=BILLING_SENDER
        )

        if success:
            db.collection("users").document(user_id).update({
                "billing_nudge_status": new_status,
                "last_nudge_date": datetime.now(timezone.utc)
            })
            logger.info(f"✅ Subscription nudge ({new_status}) sent to {user_email}")

    except Exception as e:
        logger.error(f"Failed to process billing nudge for {user_id}: {e}")

async def check_billing_status():
    now = datetime.now(timezone.utc)
    three_days_from_now = now + timedelta(days=3)

    # 1. EXPIRING SOON (The "72 Hour" Nudge)
    expiring_soon = db.collection("users")\
        .where(filter=FieldFilter("subscription_end", "<=", three_days_from_now))\
        .where(filter=FieldFilter("subscription_end", ">", now))\
        .where(filter=FieldFilter("billing_nudge_status", "==", "active"))\
        .stream()

    for doc in expiring_soon:
        user = doc.to_dict()
        await send_billing_email(doc.id, user, "trial_expiring_72h", "72h_sent")

    # 2. EXPIRED (The "Grace Period" Nudge)
    expired = db.collection("users")\
        .where(filter=FieldFilter("subscription_end", "<", now))\
        .where(filter=FieldFilter("billing_nudge_status", "in", ["active", "72h_sent"]))\
        .stream()

    for doc in expired:
        user = doc.to_dict()
        # Ensure at least 1 hour has passed since expiry to avoid webhook race conditions
        sub_end = user['subscription_end'].replace(tzinfo=timezone.utc) if user['subscription_end'].tzinfo is None else user['subscription_end']
        if (now - sub_end) >= timedelta(hours=1):
            await send_billing_email(doc.id, user, "sub_expired_24h", "expired_sent")

async def billing_service_loop():
    logger.info("🚀 Payla Billing Loop (Independent) Started")
    while True:
        try:
            await check_billing_status()
        except Exception as e:
            logger.error(f"Billing Loop Error: {e}")
        await asyncio.sleep(CHECK_INTERVAL)