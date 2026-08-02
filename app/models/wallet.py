import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Numeric, ForeignKey, Enum, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class LedgerEntryType(str, enum.Enum):
    CREDIT = "credit"
    DEBIT = "debit"


class Wallet(Base):
    """
    A wallet's `balance` column is a cached, derived value for fast reads.
    The SOURCE OF TRUTH is always WalletLedger — balance must equal the sum
    of all ledger entries for that wallet. Reconciliation jobs check this.
    """
    __tablename__ = "wallets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    balance = Column(Numeric(18, 2), nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="NGN")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="wallet")


class WalletLedger(Base):
    """
    Append-only. NEVER update or delete a row here. Corrections are made by
    inserting a new reversing entry, not by editing history.
    """
    __tablename__ = "wallet_ledger"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wallet_id = Column(UUID(as_uuid=True), ForeignKey("wallets.id"), nullable=False, index=True)
    entry_type = Column(Enum(LedgerEntryType), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)          # always positive
    balance_after = Column(Numeric(18, 2), nullable=False)   # snapshot for audit
    reference = Column(String(100), nullable=False, index=True)  # idempotency key
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_wallet_ledger_wallet_created", "wallet_id", "created_at"),
    )
