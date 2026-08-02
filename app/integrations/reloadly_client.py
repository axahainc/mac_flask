"""
Reloadly client. Reloadly uses OAuth2 client-credentials for auth (unlike
VTpass's basic auth), so this client caches an access token and refreshes
it when it expires. Verify field names against
https://developers.reloadly.com before going live.
"""
import time
import httpx

from app.core.config import settings
from app.integrations.base import TopupProvider, TopupResult, ProviderError, ProviderTimeoutError


class ReloadlyProvider(TopupProvider):
    code = "reloadly"
    _token = None
    _token_expiry = 0

    def __init__(self):
        self.base_url = settings.RELOADLY_BASE_URL

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expiry:
            return self._token
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                "https://auth.reloadly.com/oauth/token",
                json={
                    "client_id": settings.RELOADLY_CLIENT_ID,
                    "client_secret": settings.RELOADLY_CLIENT_SECRET,
                    "grant_type": "client_credentials",
                    "audience": self.base_url,
                },
            )
        data = resp.json()
        self._token = data["access_token"]
        self._token_expiry = time.time() + data.get("expires_in", 3600) - 60  # refresh 60s early
        return self._token

    def purchase(self, upstream_product_code: str, recipient: str, amount: float, idempotency_key: str) -> TopupResult:
        headers = {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/com.reloadly.topups-v1+json",
        }
        payload = {
            "operatorId": upstream_product_code,
            "amount": amount,
            "useLocalAmount": True,
            "customIdentifier": idempotency_key,  # Reloadly's idempotency/dedup field
            "recipientPhone": {"countryCode": "NG", "number": recipient},
        }
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(f"{self.base_url}/topups", json=payload, headers=headers)
        except httpx.TimeoutException as e:
            raise ProviderTimeoutError(str(e))

        data = resp.json()
        if resp.status_code == 200 and data.get("status") == "SUCCESSFUL":
            return TopupResult(success=True, provider_ref=str(data.get("transactionId")), message="successful", raw_response=data)
        if resp.status_code >= 500:
            raise ProviderTimeoutError(f"reloadly 5xx: {data}")

        raise ProviderError(data.get("message", "reloadly purchase failed"))

    def check_status(self, provider_ref: str) -> TopupResult:
        headers = {"Authorization": f"Bearer {self._get_token()}"}
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(f"{self.base_url}/topups/{provider_ref}/status", headers=headers)
        data = resp.json()
        success = data.get("status") == "SUCCESSFUL"
        return TopupResult(success=success, provider_ref=provider_ref, message=data.get("status", "unknown"), raw_response=data)
