from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "payla",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        "visibility_timeout": 3600,
        "ssl": {"ssl_cert_reqs": 0},
    },
    redis_backend_health_check_interval=30,
    broker_pool_limit=5,
)

celery_app.autodiscover_tasks(packages=["app.tasks"])
