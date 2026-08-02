import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Numeric, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    REVERSED = "reversed"   # wallet was refunded after a failed/ambiguous upstream call


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    provider_code = Column(String(50), nullable=True)        # which provider actually fulfilled it
    provider_ref = Column(String(150), nullable=True, index=True)  # upstream's transaction ID
    recipient = Column(String(50), nullable=False)           # phone number / meter number
    amount = Column(Numeric(18, 2), nullable=False)
    status = Column(Enum(TransactionStatus), default=TransactionStatus.PENDING, nullable=False)
    idempotency_key = Column(String(100), unique=True, nullable=False, index=True)
    failure_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
