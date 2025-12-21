# tasks/payout_celery.py
import asyncio
import logging
from datetime import datetime
from celery import shared_task
from app.tasks.payout import initiate_payout

logger = logging.getLogger("payla")

# Rate-limit: 50 requests/sec per worker (adjust per Paystack plan)
@shared_task(bind=True, max_retries=5, default_retry_delay=60, rate_limit="50/s")
def payout_task(self, user_id: str, amount: float, reference: str):
    """
    Celery task to process a payout safely with retries.
    """
    try:
        asyncio.run(initiate_payout(user_id, amount, reference))
        logger.info(f"Payout succeeded: {reference} → ₦{amount:,.0f} to {user_id}")
    except Exception as exc:
        logger.error(f"Payout failed: {reference}, retrying...", exc_info=True)
        raise self.retry(exc=exc)
