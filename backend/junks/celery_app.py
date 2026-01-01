from celery import Celery
from app.core.config import settings
import ssl

celery_app = Celery(
    "payla",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

# Auto-discover tasks
celery_app.autodiscover_tasks(packages=["app.tasks"])

# Recommended: JSON serialization
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    broker_use_ssl={
        "ssl_cert_reqs": ssl.CERT_NONE  # or CERT_OPTIONAL / CERT_REQUIRED
    },
    redis_backend_use_ssl={
        "ssl_cert_reqs": ssl.CERT_NONE  # same here for the result backend
    }
)
