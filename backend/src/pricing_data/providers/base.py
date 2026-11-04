"""The provider adapter protocol and the shapes every adapter returns (019, research R3).

The request shapes (catalog search, SKU selections, calculation) are the same for every
provider. Each provider implements `PricingProvider` over its own tables; the services call it
through `registry.get_provider(code)` and never branch on the provider themselves
(Constitution Principle III). Prices are `Decimal`, exactly as published; a missing price is
`None` and is never estimated (Principle I).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, Protocol

from src.pricing_data.duration import UnitClassification
from src.pricing_data.snapshot import ActiveSnapshot

LocationScope = Literal["regional", "multi_regional", "global"]

# The price types each provider publishes (research R6). An item may publish fewer; the adapter
# reports those per item (FR-005).
PROVIDER_PRICE_TYPES: dict[str, frozenset[str]] = {
    "aws": frozenset({"on_demand", "reserved_1yr", "reserved_3yr"}),
    "azure": frozenset({"on_demand", "reserved_1yr", "reserved_3yr", "savings_plan_1yr",
                        "savings_plan_3yr"}),
    "gcp": frozenset({"on_demand", "commitment_1yr", "commitment_3yr"}),
}


# Purchase options per provider (research R6): Azure and GCP prices have none.
PROVIDER_PURCHASE_OPTIONS: dict[str, frozenset[str]] = {
    "aws": frozenset({"not_applicable", "no_upfront", "partial_upfront", "all_upfront"}),
    "azure": frozenset({"not_applicable"}),
    "gcp": frozenset({"not_applicable"}),
}

# Which provider each `provider_options` kind belongs to (data-model §3).
OPTION_PROVIDERS: dict[str, str] = {"gcp_machine": "gcp", "azure_vm": "azure"}

_TERM_LABELS: dict[str, str] = {
    "on_demand": "On demand",
    "reserved_1yr": "Reserved, 1 year",
    "reserved_3yr": "Reserved, 3 years",
    "savings_plan_1yr": "Savings plan, 1 year",
    "savings_plan_3yr": "Savings plan, 3 years",
    "commitment_1yr": "Committed use, 1 year",
    "commitment_3yr": "Committed use, 3 years",
}
_OPTION_LABELS: dict[str, str] = {
    "no_upfront": "no upfront",
    "partial_upfront": "partial upfront",
    "all_upfront": "all upfront",
}


def price_type_label(pricing_term: str, purchase_option: str = "not_applicable") -> str:
    """The line item's `price_type_label` (contracts §5), e.g. "Reserved, 1 year, all upfront"."""
    label = _TERM_LABELS.get(pricing_term, pricing_term)
    option = _OPTION_LABELS.get(purchase_option)
    return f"{label}, {option}" if option else label


@dataclass(frozen=True)
class Tier:
    """One published price tier: the rate applies from `start_quantity` (per month, in the
    item's unit) up to the next tier's start, or up to `end_quantity` when the provider publishes
    one (AWS `end_range`). `rate` is `None` when the source publishes no price for the tier."""

    start_quantity: Decimal
    rate: Decimal | None
    end_quantity: Decimal | None = None


@dataclass(frozen=True)
class TierPart:
    """The part of a line's quantity priced at one tier (the line item's `tiers` breakdown).
    `to_quantity` is `None` for an open top tier."""

    from_quantity: Decimal
    to_quantity: Decimal | None
    rate: Decimal
    quantity: Decimal
    cost: Decimal


@dataclass(frozen=True)
class CatalogItem:
    """One catalog search result, the same shape for every provider (contracts §3)."""

    provider: str
    service_code: str
    service_name: str | None
    product_family: str | None
    sku: str
    summary: str
    attributes: dict[str, str]
    unit: str | None
    location_scope: LocationScope = "regional"
    kind: str | None = None
    price_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class PriceComponent:
    """One part of a composite price (a GCP machine's core or RAM, research R6): `multiplier`
    units of `sku` per unit of the line's quantity, at `rate` each."""

    label: str
    sku: str
    multiplier: Decimal
    rate: Decimal


@dataclass(frozen=True)
class PriceQuote:
    """What an adapter returns for one selection's price.

    - Usage-priced (on demand, savings plan, committed use): `tiers`, with the rates already per
      base unit, so cost is rate × quantity.
    - Term-priced (reservations): `recurring_rate` per hour and `upfront_fee` for the term.

    `unit` is the unit as published. `unit_class` is set when the adapter classifies its own
    unit (Azure, GCP); otherwise the AWS table in `duration.py` classifies `unit`.
    """

    unit: str | None
    tiers: list[Tier] = field(default_factory=list)
    recurring_rate: Decimal | None = None
    upfront_fee: Decimal | None = None
    label: str | None = None
    unit_class: UnitClassification | None = None
    components: tuple[PriceComponent, ...] = ()


@dataclass(frozen=True)
class ComparablePrice:
    """One row of a snapshot's comparable price list for Trends (research R10)."""

    location: str
    item_key: str
    service_key: str
    description: str
    unit: str | None
    price: Decimal | None  # on-demand, first non-zero tier; None or 0 are counted as excluded


class PricingProvider(Protocol):
    """Everything the app needs from one provider's pricing tables."""

    code: str
    # Whether `CatalogItem.price_types` is reported per item (Azure, GCP). When it is, a
    # selection's price type must be one its item publishes (FR-005).
    reports_price_types: bool

    def locations(self, snapshot: ActiveSnapshot) -> list[str]:
        """The selectable regions (never `global` or an Azure geography, research R5)."""
        ...

    def search(
        self, snapshot: ActiveSnapshot, *, region: str, limit: int, offset: int, **filters: object
    ) -> tuple[list[CatalogItem], int]:
        """Catalog items for `region` (plus `global` items), and the true total."""
        ...

    def describe(
        self, snapshot: ActiveSnapshot, items: Sequence[tuple[str, str]], *, region: str
    ) -> dict[tuple[str, str], CatalogItem]:
        """Catalog details for `(service_code, item)` pairs; missing pairs are left out."""
        ...

    def exists(
        self, snapshot: ActiveSnapshot, items: Iterable[tuple[str, str]], *, region: str
    ) -> set[tuple[str, str]]:
        """The `(service_code, item)` pairs that exist in `region` (import validation)."""
        ...

    def price(
        self,
        snapshot: ActiveSnapshot,
        *,
        item: str,
        pricing_term: str,
        purchase_option: str,
        region: str,
        options: dict | None = None,
    ) -> PriceQuote | None:
        """The published price for one selection, or `None` when it isn't published."""
        ...

    def units(
        self, snapshot: ActiveSnapshot, keys: Sequence[tuple[str, str, str]], *, region: str
    ) -> dict[tuple[str, str, str], str | None]:
        """The published unit for `(item, pricing_term, purchase_option)` keys; missing keys
        are left out."""
        ...

    def service_key(self, item: CatalogItem) -> str:
        ...

    def comparable_prices(self, snapshot: ActiveSnapshot) -> list[ComparablePrice]:
        ...
