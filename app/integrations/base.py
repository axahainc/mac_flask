"""
Every upstream top-up provider must implement this interface. This is what
makes failover possible: topup_service doesn't know or care whether it's
talking to VTpass or Reloadly — it just calls .purchase() on whichever
provider object it's given.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


class ProviderError(Exception):
    """Upstream returned an error we can identify (declined, invalid recipient, etc.)."""
    pass


class ProviderTimeoutError(Exception):
    """Upstream didn't respond in time — status is UNKNOWN, not failed. Handle carefully."""
    pass


@dataclass
class TopupResult:
    success: bool
    provider_ref: Optional[str]      # upstream's transaction/reference ID
    message: str
    raw_response: dict


class TopupProvider(ABC):
    code: str  # e.g. "vtpass", "reloadly" — must match Provider.code in the DB

    @abstractmethod
    def purchase(self, upstream_product_code: str, recipient: str, amount: float, idempotency_key: str) -> TopupResult:
        """Attempt to fulfill a top-up. Must raise ProviderTimeoutError on network timeout
        rather than treating it as a definite failure — a timeout means status is unknown,
        not that the top-up didn't happen. This distinction matters for reconciliation."""
        raise NotImplementedError

    @abstractmethod
    def check_status(self, provider_ref: str) -> TopupResult:
        """Used by the reconciliation job to resolve PENDING/unknown transactions."""
        raise NotImplementedError
