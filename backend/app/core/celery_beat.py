# app/core/celery_beat.py
from celery.schedules import crontab
from app.core.celery_app import celery_app

celery_app.conf.beat_schedule = {
    "retry-pending-payouts": {
        "task": "app.tasks.pending_payouts.process_pending_payouts",
        "schedule": crontab(minute="*/0.5"),  # every 15 minutes
    },
}
