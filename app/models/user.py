import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class KYCTier(str, enum.Enum):
    TIER_0 = "tier_0"   # phone-verified only, low limits
    TIER_1 = "tier_1"   # + email/BVN, medium limits
    TIER_2 = "tier_2"   # + govt ID, high limits (needed for agents)


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone = Column(String(20), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True)
    hashed_password = Column(String(255), nullable=False)
    kyc_tier = Column(Enum(KYCTier), default=KYCTier.TIER_0, nullable=False)
    is_agent = Column(String(10), default="false")
    created_at = Column(DateTime, default=datetime.utcnow)

    wallet = relationship("Wallet", back_populates="user", uselist=False)
