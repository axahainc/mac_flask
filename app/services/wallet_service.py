"""
Wallet service — every balance mutation in the whole system MUST go through
these two functions. Never write to wallet.balance directly anywhere else.

Why this design:
1. `SELECT ... FOR UPDATE` locks the wallet row so two concurrent requests
   (e.g. a double-tap on "Buy" or two webhook retries) can't both read the
   same starting balance and both succeed — this is THE classic bug in
   home-grown wallet systems.
2. Every mutation writes an immutable WalletLedger row. wallet.balance is a
   cache; wallet_ledger is the source of truth used for audits/reconciliation.
3. `reference` is an idempotency key — if the same reference is submitted
   twice (e.g. a retried webhook), we detect it and skip re-applying it,
   rather than double-crediting or double-debiting.
"""
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.wallet import Wallet, WalletLedger, LedgerEntryType


class InsufficientFundsError(Exception):
    pass


class DuplicateLedgerReferenceError(Exception):
    """Raised when a reference has already been applied — caller should treat as a no-op success."""
    pass


def _reference_already_applied(db: Session, reference: str) -> bool:
    existing = db.execute(
        select(WalletLedger).where(WalletLedger.reference == reference)
    ).scalar_one_or_none()
    return existing is not None


def debit_wallet(db: Session, wallet_id, amount: Decimal, reference: str, description: str = "") -> Wallet:
    if _reference_already_applied(db, reference):
        raise DuplicateLedgerReferenceError(reference)

    # Row-level lock: blocks other transactions from reading/writing this
    # wallet until we commit or rollback. This is what prevents overdrafts
    # under concurrent requests.
    wallet = db.execute(
        select(Wallet).where(Wallet.id == wallet_id).with_for_update()
    ).scalar_one()

    if wallet.balance < amount:
        raise InsufficientFundsError(f"wallet {wallet_id} balance {wallet.balance} < {amount}")

    wallet.balance = wallet.balance - amount
    db.add(WalletLedger(
        wallet_id=wallet.id,
        entry_type=LedgerEntryType.DEBIT,
        amount=amount,
        balance_after=wallet.balance,
        reference=reference,
        description=description,
    ))
    db.flush()  # push to DB within the open transaction, don't commit yet — caller controls the commit boundary
    return wallet


def credit_wallet(db: Session, wallet_id, amount: Decimal, reference: str, description: str = "") -> Wallet:
    if _reference_already_applied(db, reference):
        raise DuplicateLedgerReferenceError(reference)

    wallet = db.execute(
        select(Wallet).where(Wallet.id == wallet_id).with_for_update()
    ).scalar_one()

    wallet.balance = wallet.balance + amount
    db.add(WalletLedger(
        wallet_id=wallet.id,
        entry_type=LedgerEntryType.CREDIT,
        amount=amount,
        balance_after=wallet.balance,
        reference=reference,
        description=description,
    ))
    db.flush()
    return wallet
