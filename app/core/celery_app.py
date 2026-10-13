from celery import Celery
from celery.signals import setup_logging as celery_setup_logging
from app.core.config import settings
from app.core.logging import setup_logging


celery_app = Celery(
    "bulk_certificate_generator",
    broker=settings.broker_url,
    backend=settings.result_backend,
    include=["app.workers.processor"],
)

celery_app.conf.update(
    # Task persistence across worker restarts / crashes
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Fair dispatching of tasks
    worker_prefetch_multiplier=1,
)

@celery_setup_logging.connect
def on_celery_setup_logging(**kwargs):
    setup_logging(log_level=settings.log_level)

