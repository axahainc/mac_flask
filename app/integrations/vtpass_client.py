"""
VTpass client. Endpoint shapes below follow VTpass's documented pattern
(POST /api/pay with request_id, serviceID, phone, amount) — verify field
names against the current docs at https://www.vtpass.com/developers
before going live; aggregators do change field names between API versions.
"""
import httpx

from app.core.config import settings
from app.integrations.base import TopupProvider, TopupResult, ProviderError, ProviderTimeoutError


class VTpassProvider(TopupProvider):
    code = "vtpass"

    def __init__(self):
        self.base_url = settings.VTPASS_BASE_URL
        self.auth = (settings.VTPASS_API_KEY, settings.VTPASS_SECRET_KEY)

    def purchase(self, upstream_product_code: str, recipient: str, amount: float, idempotency_key: str) -> TopupResult:
        payload = {
            "request_id": idempotency_key,   # VTpass requires a unique request_id per attempt
            "serviceID": upstream_product_code,
            "phone": recipient,
            "amount": amount,
        }
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(f"{self.base_url}/pay", json=payload, auth=self.auth)
        except httpx.TimeoutException as e:
            raise ProviderTimeoutError(str(e))

        data = resp.json()
        code = data.get("code")
        content = data.get("content", {})
        transaction = content.get("transactions", {})

        if code == "000" and transaction.get("status") == "delivered":
            return TopupResult(
                success=True,
                provider_ref=transaction.get("transactionId"),
                message="delivered",
                raw_response=data,
            )
        if transaction.get("status") == "pending":
            # VTpass sometimes returns pending immediately — treat as unknown, not failed
            raise ProviderTimeoutError("vtpass returned pending status")

        raise ProviderError(data.get("response_description", "vtpass purchase failed"))

    def check_status(self, provider_ref: str) -> TopupResult:
        payload = {"request_id": provider_ref}
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(f"{self.base_url}/requery", json=payload, auth=self.auth)
        data = resp.json()
        content = data.get("content", {}).get("transactions", {})
        success = content.get("status") == "delivered"
        return TopupResult(success=success, provider_ref=provider_ref, message=content.get("status", "unknown"), raw_response=data)
