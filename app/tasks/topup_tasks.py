"""
Async wrapper around topup_service.process_topup(). Kept deliberately thin —
all real logic lives in the service layer so it stays testable without Celery.
"""
from celery import Task

from app.tasks.celery_app import celery_app
from app.core.database import SessionLocal
from app.services.topup_service import process_topup
from app.integrations.base import ProviderTimeoutError


class DBTask(Task):
    """Ensures every task gets its own DB session and always closes it,
    even on failure — prevents connection leaks under Celery's process pool."""
    _db = None

    def after_return(self, *args, **kwargs):
        if self._db is not None:
            self._db.close()
            self._db = None


@celery_app.task(
    bind=True,
    base=DBTask,
    autoretry_for=(ProviderTimeoutError,),
    retry_backoff=True,       # exponential backoff: 1s, 2s, 4s...
    retry_backoff_max=60,
    retry_jitter=True,        # avoid thundering-herd retries across many tasks
    max_retries=3,
)
def process_topup_task(self, transaction_id: str):
    db = SessionLocal()
    try:
        result = process_topup(db, transaction_id)
        return {"status": result.status.value, "message": result.message}
    finally:
        db.close()
