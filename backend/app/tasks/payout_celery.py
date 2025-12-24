import asyncio
import logging
from celery import shared_task
from app.tasks.payout import initiate_payout

logger = logging.getLogger("payla")

@shared_task(
    bind=True, 
    max_retries=5, 
    # Exponential backoff: 60s, 120s, 240s...
    autoretry_for=(Exception,),
    retry_backoff=True, 
    retry_jitter=True,
    rate_limit="50/s"
)
def payout_task(self, user_id: str, amount: float, reference: str):
    """
    Wrapper to run the async initiate_payout in a sync Celery worker.
    """
    try:
        # Use a single run call to handle the coroutine
        asyncio.run(initiate_payout(user_id, amount, reference))
    except Exception as exc:
        logger.error(f"Permanent failure for {reference}: {exc}")
        raise exc