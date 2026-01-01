import asyncio
import logging
from celery import shared_task
from app.tasks.payout import initiate_payout

logger = logging.getLogger("payla")

@shared_task(
    bind=True, 
    max_retries=25,  # Increased to handle up to 4 days of retries if needed
    rate_limit="50/s"
)
def payout_task(self, user_id: str, amount: float, reference: str):
    """
    Wrapper to run the async initiate_payout in a sync Celery worker.
    Passes 'self' to allow the async function to trigger Celery retries.
    """
    try:
        # We pass 'self' as the task_instance
        asyncio.run(initiate_payout(user_id, amount, reference, task_instance=self))
    except Exception as exc:
        # If the error is a Celery Retry signal, re-raise it so Celery handles the countdown
        if "Retry" in str(type(exc)):
            raise exc
            
        logger.error(f"Permanent failure for payout {reference}: {exc}", exc_info=True)
        # For non-retry exceptions, we don't want to infinite loop, so we let it fail
        raise exc