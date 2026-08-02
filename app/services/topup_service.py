"""
The heart of the system: process_topup() implements the failover logic
described in the plan —

  1. Debit the wallet FIRST (atomically, with row locking) and create a
     PENDING transaction. This reserves the funds so the user can't spend
     the same balance twice while we're mid-purchase.
  2. Try each active provider for this product, in priority order.
  3. On a clean failure (ProviderError — e.g. "invalid meter number"),
     move to the next provider immediately.
  4. On a timeout (ProviderTimeoutError), the upstream state is UNKNOWN —
     do NOT immediately retry with a different provider (that risks
     double-delivery if the first one actually succeeded). Instead, leave
     the transaction PROCESSING and let the reconciliation job resolve it.
  5. If every provider cleanly fails, REVERSE the debit (credit the wallet
     back) and mark the transaction FAILED.
  6. All money movements use the transaction's `idempotency_key` as the
     ledger reference, so retrying this whole function for the same
     transaction is always safe.
"""
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.transaction import Transaction, TransactionStatus
from app.models.provider import Provider, Product
from app.services.wallet_service import debit_wallet, credit_wallet, InsufficientFundsError, DuplicateLedgerReferenceError
from app.integrations.base import ProviderError, ProviderTimeoutError
from app.integrations.registry import get_provider_client

import structlog

log = structlog.get_logger()


class TopupProcessingResult:
    def __init__(self, status: TransactionStatus, message: str):
        self.status = status
        self.message = message


def _get_active_providers_for_product(db: Session, product: Product) -> list[Provider]:
    """Returns providers capable of fulfilling this product, ordered by failover priority.
    In a real system, Product would map to provider-specific upstream codes per provider
    (e.g. via a product_provider_mapping table) since the same "MTN Airtime" product has
    a different upstream service code on VTpass vs Reloadly. Simplified here for clarity."""
    return db.execute(
        select(Provider).where(Provider.is_active == True).order_by(Provider.priority.asc())  # noqa: E712
    ).scalars().all()


def process_topup(db: Session, transaction_id) -> TopupProcessingResult:
    txn = db.get(Transaction, transaction_id)
    if txn is None:
        raise ValueError(f"transaction {transaction_id} not found")

    if txn.status in (TransactionStatus.SUCCESS, TransactionStatus.FAILED, TransactionStatus.REVERSED):
        # Already resolved — safe to no-op on retry (idempotent by design).
        return TopupProcessingResult(txn.status, "already resolved, no-op")

    product = db.get(Product, txn.product_id)
    providers = _get_active_providers_for_product(db, product)

    txn.status = TransactionStatus.PROCESSING
    db.flush()

    for provider_row in providers:
        client = get_provider_client(provider_row.code)
        try:
            result = client.purchase(
                upstream_product_code=product.upstream_code,
                recipient=txn.recipient,
                amount=float(txn.amount),
                idempotency_key=f"{txn.idempotency_key}:{provider_row.code}",
            )
        except ProviderTimeoutError as e:
            log.warning("provider_timeout", provider=provider_row.code, txn_id=str(txn.id), error=str(e))
            # Unknown outcome — leave as PROCESSING, do NOT try another provider or
            # reverse funds. The reconciliation job will call check_status() later.
            db.commit()
            return TopupProcessingResult(TransactionStatus.PROCESSING, f"{provider_row.code} timed out; awaiting reconciliation")
        except ProviderError as e:
            log.info("provider_declined", provider=provider_row.code, txn_id=str(txn.id), error=str(e))
            continue  # clean failure — safe to try the next provider

        if result.success:
            txn.status = TransactionStatus.SUCCESS
            txn.provider_code = provider_row.code
            txn.provider_ref = result.provider_ref
            from datetime import datetime
            txn.completed_at = datetime.utcnow()
            db.commit()
            log.info("topup_success", provider=provider_row.code, txn_id=str(txn.id))
            return TopupProcessingResult(TransactionStatus.SUCCESS, "delivered")

    # Every provider cleanly failed -> reverse the reserved funds.
    try:
        credit_wallet(
            db,
            wallet_id=_get_wallet_id_for_user(db, txn.user_id),
            amount=Decimal(txn.amount),
            reference=f"reversal:{txn.idempotency_key}",
            description=f"Reversal for failed transaction {txn.id}",
        )
    except DuplicateLedgerReferenceError:
        pass  # already reversed on a previous retry — fine

    txn.status = TransactionStatus.FAILED
    txn.failure_reason = "all providers declined"
    db.commit()
    log.warning("topup_failed_all_providers", txn_id=str(txn.id))
    return TopupProcessingResult(TransactionStatus.FAILED, "all providers declined")


def _get_wallet_id_for_user(db: Session, user_id):
    from app.models.wallet import Wallet
    return db.execute(select(Wallet.id).where(Wallet.user_id == user_id)).scalar_one()


def initiate_topup(db: Session, user_id, product_id, recipient: str, amount: Decimal, idempotency_key: str) -> Transaction:
    """Step 1 of the flow: reserve funds and create the PENDING transaction.
    Called synchronously from the API route; the actual provider call is
    dispatched to Celery (see tasks/topup_tasks.py) so the HTTP request
    returns fast and upstream slowness never blocks the user's browser/app."""
    wallet_id = _get_wallet_id_for_user(db, user_id)

    debit_wallet(db, wallet_id=wallet_id, amount=amount, reference=idempotency_key,
                 description=f"Top-up reservation for product {product_id}")

    txn = Transaction(
        user_id=user_id,
        product_id=product_id,
        recipient=recipient,
        amount=amount,
        idempotency_key=idempotency_key,
        status=TransactionStatus.PENDING,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn
