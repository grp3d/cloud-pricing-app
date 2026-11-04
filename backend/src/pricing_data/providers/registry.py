"""Provider code → adapter (019, research R3). Adding a provider means adding an adapter here."""

from __future__ import annotations

from src.pricing_data.providers.aws import AwsProvider
from src.pricing_data.providers.azure import AzureProvider
from src.pricing_data.providers.base import PricingProvider
from src.pricing_data.providers.gcp import GcpProvider

_PROVIDERS: dict[str, PricingProvider] = {
    "aws": AwsProvider(),
    "azure": AzureProvider(),
    "gcp": GcpProvider(),
}


def get_provider(code: str | None) -> PricingProvider:
    """The adapter for `code`; a missing code means `aws` (contracts, compatibility rule).
    Raises `ValueError` for a provider with no adapter."""
    code = code or "aws"
    try:
        return _PROVIDERS[code]
    except KeyError:
        raise ValueError(f"no pricing adapter for provider {code!r}") from None


def has_adapter(code: str) -> bool:
    """Whether the app can search and price `code` (an inactive provider has no adapter yet)."""
    return code in _PROVIDERS
