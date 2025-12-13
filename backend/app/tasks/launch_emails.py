# tasks/launch_emails.py → FULLY AUTOMATIC LAUNCH DAY EMAILS
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from app.utils.presell_email import send_layla_email
from app.core.firebase import db

logger = logging.getLogger("payla")

# SET YOUR LAUNCH DATE HERE (UTC)
LAUNCH_DATE_UTC = datetime(2026, 1, 1, 7, 0, 0, tzinfo=timezone.utc)  # June 1, 2025 @ 8:00 AM WAT

# Email templates
EMAILS = {
    "paid": {
        "template": "launch_day_1",
        "context": lambda u: {
            "name": u["full_name"].split()[0],
            "username": u["username"]
        }
    },
    "waitlist": {
        "template": "launch_waitlist",
        "context": lambda u: {
            "name": u["name"].split()[0]
        }
    }
}

async def send_emails_to_group(collection: str, email_config: dict):
    """Send emails to a Firestore collection"""
    count = 0
    docs = db.collection(collection).stream()
    
    for doc in docs:
        user = doc.to_dict()
        try:
            send_layla_email(
                email_config["template"],
                user["email"],
                email_config["context"](user)
            )
            count += 1
            await asyncio.sleep(1.3)  # Stay under Gmail limits
        except Exception as e:
            logger.error(f"Failed to email {user['email']}: {e}")
    
    logger.info(f"Sent {count} emails to {collection}")

async def launch_day_email_blast():
    """The magic function — runs only ONCE on launch day"""
    now = datetime.now(timezone.utc)
    
    if now < LAUNCH_DATE_UTC:
        logger.info(f"Launch day not yet — waiting... (Launch: {LAUNCH_DATE_UTC})")
        return False
    
    if now > LAUNCH_DATE_UTC + timedelta(hours=24):
        logger.info("Launch day already passed — emails already sent")
        return False
    
    logger.info("PAYLA IS LAUNCHING TODAY — SENDING EMAILS TO EVERYONE")
    
    # Send to paid users
    await send_emails_to_group("presell_users", EMAILS["paid"])
    
    # Send to waitlist
    await send_emails_to_group("presell_waitlist", EMAILS["waitlist"])
    
    logger.info("LAUNCH DAY EMAIL BLAST COMPLETE — PAYLA IS LIVE")
    return True

# AUTO-START WHEN SERVER BOOTS
async def start_launch_email_scheduler():
    while True:
        try:
            now = datetime.now(timezone.utc)
            if now >= LAUNCH_DATE_UTC:
                await launch_day_email_blast()
                break
            else:
                # Sleep until launch time or 5 seconds, whichever is smaller
                seconds_until_launch = (LAUNCH_DATE_UTC - now).total_seconds()
                await asyncio.sleep(min(seconds_until_launch, 5))
        except Exception as e:
            logger.error(f"Launch email error: {e}")

# Start it when server starts
import threading
def auto_start_launch_emails():
    """Call this from main.py"""
    threading.Thread(target=lambda: asyncio.run(start_launch_email_scheduler()), daemon=True).start()
    logger.info("Launch day email scheduler started — will auto-run on June 1, 2025")