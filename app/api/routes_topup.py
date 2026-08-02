"""
POST /topups — the only endpoint the frontend calls to buy airtime/data/bills.
It does the wallet debit synchronously (so we can return "insufficient funds"
immediately) but hands the actual provider call to Celery so the request
returns in milliseconds regardless of upstream latency.
"""
import uuid
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.topup_service import initiate_topup
from app.services.wallet_service import InsufficientFundsError, DuplicateLedgerReferenceError
from app.tasks.topup_tasks import process_topup_task

router = APIRouter(prefix="/topups", tags=["topups"])


class TopupRequest(BaseModel):
    user_id: uuid.UUID
    product_id: uuid.UUID
    recipient: str
    amount: Decimal
    client_reference: str   # client-generated idempotency key, e.g. a UUID from the app


@router.post("")
def create_topup(payload: TopupRequest, db: Session = Depends(get_db)):
    # Using the client's own reference as the idempotency key means a network
    # retry from the app (e.g. user backgrounds the app mid-request) can't
    # result in a double-charge — the DB unique constraint on
    # transactions.idempotency_key plus wallet_ledger.reference protects this.
    try:
        txn = initiate_topup(
            db,
            user_id=payload.user_id,
            product_id=payload.product_id,
            recipient=payload.recipient,
            amount=payload.amount,
            idempotency_key=payload.client_reference,
        )
    except InsufficientFundsError:
        raise HTTPException(status_code=402, detail="Insufficient wallet balance")
    except DuplicateLedgerReferenceError:
        raise HTTPException(status_code=409, detail="Duplicate request — already processed")

    process_topup_task.delay(str(txn.id))

    return {"transaction_id": str(txn.id), "status": txn.status.value}


@router.get("/{transaction_id}")
def get_topup_status(transaction_id: uuid.UUID, db: Session = Depends(get_db)):
    from app.models.transaction import Transaction
    txn = db.get(Transaction, transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {
        "transaction_id": str(txn.id),
        "status": txn.status.value,
        "provider": txn.provider_code,
        "failure_reason": txn.failure_reason,
    }
