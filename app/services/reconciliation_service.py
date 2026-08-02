"""
Resolves transactions stuck in PROCESSING (i.e. the provider timed out and
we genuinely don't know if it succeeded). This job is what prevents "money
debited but nothing delivered" complaints from becoming permanent — it's
the single most important background job in a VTU system.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.transaction import Transaction, TransactionStatus
from app.services.wallet_service import credit_wallet, DuplicateLedgerReferenceError
from app.integrations.registry import get_provider_client
import structlog

log = structlog.get_logger()

STUCK_THRESHOLD_MINUTES = 3


def reconcile_stuck_transactions(db: Session):
    cutoff = datetime.utcnow() - timedelta(minutes=STUCK_THRESHOLD_MINUTES)
    stuck = db.execute(
        select(Transaction).where(
            Transaction.status == TransactionStatus.PROCESSING,
            Transaction.created_at < cutoff,
        )
    ).scalars().all()

    for txn in stuck:
        if not txn.provider_code or not txn.provider_ref:
            # We never even got a provider_ref back — provider never accepted the
            # request in the first place. Safe to treat as failed and reverse.
            _reverse_and_fail(db, txn, reason="no provider_ref recorded; assumed not accepted")
            continue

        client = get_provider_client(txn.provider_code)
        try:
            status = client.check_status(txn.provider_ref)
        except Exception as e:
            log.warning("reconciliation_check_failed", txn_id=str(txn.id), error=str(e))
            continue  # try again on the next run

        if status.success:
            txn.status = TransactionStatus.SUCCESS
            txn.completed_at = datetime.utcnow()
            db.commit()
            log.info("reconciled_success", txn_id=str(txn.id))
        elif status.message in ("FAILED", "failed", "declined"):
            _reverse_and_fail(db, txn, reason=f"upstream confirmed failure: {status.message}")
        else:
            log.info("still_pending", txn_id=str(txn.id), upstream_status=status.message)
            # leave PROCESSING, check again next run


def _reverse_and_fail(db: Session, txn: Transaction, reason: str):
    from app.services.topup_service import _get_wallet_id_for_user
    try:
        credit_wallet(
            db,
            wallet_id=_get_wallet_id_for_user(db, txn.user_id),
            amount=Decimal(txn.amount),
            reference=f"reversal:{txn.idempotency_key}",
            description=reason,
        )
    except DuplicateLedgerReferenceError:
        pass
    txn.status = TransactionStatus.FAILED
    txn.failure_reason = reason
    db.commit()
    log.warning("reconciled_failed_and_reversed", txn_id=str(txn.id), reason=reason)
