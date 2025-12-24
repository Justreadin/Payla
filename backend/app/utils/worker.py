# backend/app/worker.py
import asyncio
import logging
from app.services.layla_service import LaylaOnboardingService
from app.core.firebase import db # Assuming firebase is initialized here

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LaylaWorker")

async def run_layla_sequence():
    logger.info("Layla is reviewing the user list...")
    try:
        service = LaylaOnboardingService()
        # Ensure run_daily_automation is async if it calls Firestore/Resend
        service.run_daily_automation() 
        logger.info("Layla has completed her daily sequence.")
    except Exception as e:
        logger.error(f"Layla Worker Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_layla_sequence())