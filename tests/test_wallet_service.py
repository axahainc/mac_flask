"""
Core correctness tests for the wallet ledger. Run with: pytest tests/ -v
Requires a real Postgres test DB (row-locking behavior can't be faithfully
tested against SQLite) — point DATABASE_URL at a disposable test database.
"""
import uuid
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.user import User
from app.models.wallet import Wallet
from app.services.wallet_service import (
    debit_wallet, credit_wallet, InsufficientFundsError, DuplicateLedgerReferenceError,
)


@pytest.fixture
def db_session():
    engine = create_engine("postgresql://vtu_user:vtu_pass@localhost:5432/vtu_test_db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    Base.metadata.drop_all(engine)
    session.close()


def _make_user_with_wallet(db, balance=Decimal("1000.00")):
    user = User(id=uuid.uuid4(), phone=f"080{uuid.uuid4().int % 10**8}", hashed_password="x")
    db.add(user)
    db.flush()
    wallet = Wallet(id=uuid.uuid4(), user_id=user.id, balance=balance)
    db.add(wallet)
    db.commit()
    return wallet


def test_debit_reduces_balance(db_session):
    wallet = _make_user_with_wallet(db_session)
    debit_wallet(db_session, wallet.id, Decimal("200.00"), reference=str(uuid.uuid4()))
    db_session.commit()
    db_session.refresh(wallet)
    assert wallet.balance == Decimal("800.00")


def test_debit_beyond_balance_raises(db_session):
    wallet = _make_user_with_wallet(db_session, balance=Decimal("100.00"))
    with pytest.raises(InsufficientFundsError):
        debit_wallet(db_session, wallet.id, Decimal("200.00"), reference=str(uuid.uuid4()))


def test_duplicate_reference_is_rejected(db_session):
    wallet = _make_user_with_wallet(db_session)
    ref = str(uuid.uuid4())
    debit_wallet(db_session, wallet.id, Decimal("50.00"), reference=ref)
    db_session.commit()
    with pytest.raises(DuplicateLedgerReferenceError):
        debit_wallet(db_session, wallet.id, Decimal("50.00"), reference=ref)


def test_credit_after_reversal_restores_balance(db_session):
    wallet = _make_user_with_wallet(db_session, balance=Decimal("500.00"))
    ref = str(uuid.uuid4())
    debit_wallet(db_session, wallet.id, Decimal("300.00"), reference=ref)
    db_session.commit()
    credit_wallet(db_session, wallet.id, Decimal("300.00"), reference=f"reversal:{ref}")
    db_session.commit()
    db_session.refresh(wallet)
    assert wallet.balance == Decimal("500.00")
