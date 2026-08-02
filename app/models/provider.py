import uuid
from sqlalchemy import Column, String, Boolean, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Provider(Base):
    """
    One row per upstream aggregator (VTpass, Reloadly, ClubKonnect, ...).
    `priority` controls failover order — lower number = tried first.
    """
    __tablename__ = "providers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(50), unique=True, nullable=False)   # e.g. "vtpass", "reloadly"
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=100)
    config = Column(JSON, default=dict)   # non-secret config only; secrets stay in env vars


class Product(Base):
    """
    A sellable item: e.g. 'MTN Airtime', 'DSTV Compact', 'Ikeja Electric Prepaid'.
    Maps a category to a specific provider + upstream product code.
    """
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id = Column(UUID(as_uuid=True), nullable=False)
    category = Column(String(50), nullable=False)   # airtime | data | electricity | cable_tv
    network = Column(String(50), nullable=True)      # MTN, Airtel, Glo, 9mobile...
    upstream_code = Column(String(100), nullable=False)  # provider's own product/service ID
    display_name = Column(String(150), nullable=False)
    is_active = Column(Boolean, default=True)
