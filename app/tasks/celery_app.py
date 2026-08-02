from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery("vtu", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    task_acks_late=True,          # don't ack until the task actually finishes — survives worker crashes
    worker_prefetch_multiplier=1,  # avoid one slow worker hoarding many jobs
)

celery_app.conf.beat_schedule = {
    "reconcile-pending-transactions": {
        "task": "app.tasks.reconciliation_tasks.reconcile_pending_transactions",
        "schedule": crontab(minute="*/5"),   # every 5 minutes
    },
}
