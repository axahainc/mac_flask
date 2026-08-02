from app.tasks.celery_app import celery_app
from app.core.database import SessionLocal
from app.services.reconciliation_service import reconcile_stuck_transactions


@celery_app.task
def reconcile_pending_transactions():
    db = SessionLocal()
    try:
        reconcile_stuck_transactions(db)
    finally:
        db.close()
