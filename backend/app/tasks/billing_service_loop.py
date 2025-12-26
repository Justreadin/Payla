import asyncio
import logging
from datetime import datetime, timezone, timedelta
from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from app.tasks.reminder_service_loop import send_single_channel
from app.utils.billing_emails import BILLING_TEMPLATES, generate_billing_content

db = firestore.client()
logger = logging.getLogger("payla.billing")

# Run check once every hour
CHECK_INTERVAL = 3600 
BILLING_SENDER = "billing.noreply@payla.vip"

async def check_billing_status():
    # Use timezone-aware 'now'
    now = datetime.now(timezone.utc)
    
    # Define the "Danger Zone" for upcoming expirations
    three_days_from_now = now + timedelta(days=3)
    
    logger.info(f"Checking billing status at {now.isoformat()}")

    # 1. EXPIRING IN 72 HOURS (3 Days)
    # We look for active users whose sub ends in the next 3 days
    expiring_soon = db.collection("users")\
        .where(filter=FieldFilter("subscription_end", "<=", three_days_from_now))\
        .where(filter=FieldFilter("subscription_end", ">", now))\
        .where(filter=FieldFilter("billing_nudge_status", "==", "active"))\
        .stream()

    for doc in expiring_soon:
        user = doc.to_dict()
        user_id = doc.id
        
        sub_end = user['subscription_end']
        if sub_end.tzinfo is None:
            sub_end = sub_end.replace(tzinfo=timezone.utc)

        diff = sub_end - now
        
        # Only trigger if they are strictly in the 2-3 day window
        if 2 <= diff.days <= 3:
            # Note: Using your premium pricing 
            # (Context can still be passed if template uses it)
            await send_billing_email(
                user_id, 
                user, 
                "trial_expiring_72h", 
                "72h_sent"
            )

    # 2. EXPIRED (Grace Period Entry)
    # BULLETPROOF: We target ANYONE who has passed their end date 
    # but hasn't received the 'expired_sent' nudge yet.
    expired_grace = db.collection("users")\
        .where(filter=FieldFilter("subscription_end", "<", now))\
        .where(filter=FieldFilter("billing_nudge_status", "in", ["active", "72h_sent"]))\
        .stream()

    for doc in expired_grace:
        user = doc.to_dict()
        user_id = doc.id
        
        # Double check the timestamp in logic to ensure they are at least 
        # 1 hour past expiry to avoid racing with renewal webhooks
        sub_end = user['subscription_end']
        if sub_end.tzinfo is None:
            sub_end = sub_end.replace(tzinfo=timezone.utc)
            
        if (now - sub_end) >= timedelta(hours=1):
            await send_billing_email(user_id, user, "sub_expired_24h", "expired_sent")


async def send_billing_email(user_id, user, template_key, new_status, extra_context=None):
    """Helper to format, send, and update status in one go"""
    try:
        context = {
            "user_name": (user.get("name") or "Creator").split()[0],
            "name": user.get("username") or "creator",
            "billing_url": "https://payla.ng/subscription",
        }

        if extra_context:
            context.update(extra_context)

        html = generate_billing_content(template_key, context)
        subject = BILLING_TEMPLATES[template_key]["subject"].format(name=context["name"])

        # send_single_channel needs to be configured to accept sender/from_email
        success = await send_single_channel(
            method="email",
            invoice={"client_email": user.get("email")},
            msg="",
            subject=subject,
            html=html,
            email_type="billing",
            sender=BILLING_SENDER # Explicitly using the vip address
        )

        if success:
            db.collection("users").document(user_id).update({
                "billing_nudge_status": new_status,
                "last_nudge_date": datetime.now(timezone.utc)
            })
            logger.info(f"✅ {new_status} nudge sent to {user.get('email')} via {BILLING_SENDER}")

    except Exception as e:
        logger.error(f"Failed to process billing nudge for {user_id}: {e}")

async def billing_service_loop():
    logger.info("🚀 Starting Payla Billing Service Loop")
    while True:
        try:
            await check_billing_status()
        except Exception as e:
            logger.exception(f"Critical error in billing loop: {e}")
        
        await asyncio.sleep(CHECK_INTERVAL)