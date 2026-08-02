"""
Maps provider.code (from the DB) to a concrete client instance.
Add a new provider to the system by: (1) writing a new TopupProvider
subclass, (2) registering it here, (3) inserting a `providers` row with
the matching `code` and a `priority`. No other code changes needed.
"""
from app.integrations.vtpass_client import VTpassProvider
from app.integrations.reloadly_client import ReloadlyProvider

PROVIDER_REGISTRY = {
    "vtpass": VTpassProvider,
    "reloadly": ReloadlyProvider,
}


def get_provider_client(code: str):
    provider_cls = PROVIDER_REGISTRY.get(code)
    if not provider_cls:
        raise ValueError(f"No client registered for provider code '{code}'")
    return provider_cls()
