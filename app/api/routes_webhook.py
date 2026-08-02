"""
Receives async status callbacks from providers that support webhooks
(not all VTU aggregators do — some are request/response only, which is
why the reconciliation poller exists as a fallback for those).

Security: verify the signature BEFORE touching the DB. Never trust an
unauthenticated POST to move money.
"""
import hmac
import hashlib
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _verify_signature(raw_body: bytes, signature_header: str) -> bool:
    expected = hmac.new(
        settings.WEBHOOK_SIGNING_SECRET.encode(), raw_body, hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header or "")


@router.post("/provider-status")
async def provider_status_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    signature = request.headers.get("x-webhook-signature", "")

    if not _verify_signature(raw_body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    provider_ref = payload.get("transactionId")
    upstream_status = payload.get("status")

    from app.models.transaction import Transaction, TransactionStatus
    from sqlalchemy import select
    txn = db.execute(select(Transaction).where(Transaction.provider_ref == provider_ref)).scalar_one_or_none()
    if not txn:
        # Unknown reference — log and return 200 so the provider doesn't keep retrying forever,
        # but alert on this in monitoring since it usually means a data mismatch.
        return {"received": True, "matched": False}

    # Idempotent: if we already resolved this transaction, do nothing.
    if txn.status in (TransactionStatus.SUCCESS, TransactionStatus.FAILED, TransactionStatus.REVERSED):
        return {"received": True, "matched": True, "already_resolved": True}

    if upstream_status in ("delivered", "SUCCESSFUL"):
        from datetime import datetime
        txn.status = TransactionStatus.SUCCESS
        txn.completed_at = datetime.utcnow()
        db.commit()
    elif upstream_status in ("failed", "FAILED"):
        from app.services.reconciliation_service import _reverse_and_fail
        _reverse_and_fail(db, txn, reason=f"webhook reported failure: {upstream_status}")

    return {"received": True, "matched": True}
