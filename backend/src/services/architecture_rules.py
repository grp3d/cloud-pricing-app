"""The edit rules for architectures, shared by the edit routes and agent proposals (025, research R1).

Each rule raises `RuleError` with the status and detail the edit routes have always returned, so
manual edits behave exactly as before and a proposal is refused for exactly the reasons a manual
edit would be (FR-002). The functions take plain facts, not ORM rows or HTTP bodies, so a whole
proposed architecture can be checked before anything is saved.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from src.pricing_data.active_snapshot import get_active_snapshot
from src.pricing_data.providers.base import (
    OPTION_PROVIDERS,
    PROVIDER_PRICE_TYPES,
    PROVIDER_PURCHASE_OPTIONS,
)
from src.pricing_data.providers.registry import get_provider, has_adapter
from src.pricing_data.regions import list_available_regions

MAX_CHANGE_ITEMS = 100


class RuleError(HTTPException):
    """A broken edit rule: the HTTP status and detail the routes return, plus the field for a
    field error (422) and the proposal item it concerns, when there is one. It is an
    `HTTPException`, so a route that lets it through answers exactly as it always has."""

    def __init__(self, status: int, detail: Any, *, field: str | None = None,
                 message: str | None = None, ref: str | None = None):
        super().__init__(status_code=status, detail=detail)
        self.status = status
        self.detail = detail
        self.field = field
        self.message = message or (detail if isinstance(detail, str) else str(detail))
        self.ref = ref

    def to_http(self) -> HTTPException:
        return HTTPException(status_code=self.status, detail=self.detail)


def _field_error(field: str, message: str) -> RuleError:
    return RuleError(422, [{"loc": ["body", field], "msg": message, "type": "value_error"}],
                     field=field, message=message)


@dataclass(frozen=True)
class CollectionFacts:
    """What the nesting rule needs to know about a would-be parent."""

    type: str
    region: str


def check_provider(provider: str) -> None:
    if not has_adapter(provider):
        raise RuleError(400, f"Provider not supported: {provider}")


def check_region_given(region: str | None, *, creating: bool = True) -> None:
    if not region:
        raise RuleError(400, "region is required when parent_collection_id is not given"
                        if creating else "region is required")


def check_region_available(provider: str, region: str) -> None:
    if region not in list_available_regions(provider):
        raise RuleError(400, f"region '{region}' is not currently available")


def check_nesting(child_type: str, child_region: str, parent: CollectionFacts | None, *,
                  creating: bool = False) -> None:
    """An Application Component may sit inside a live VPC of the same architecture, in the same
    region (002 FR-001–FR-004, 010 FR-004). `parent` is None when the id didn't resolve to a
    live collection of the architecture. On create the child takes the parent's region, so the
    region check only matters for moves and proposals."""
    if child_type != "application_component":
        raise RuleError(400, "Only an Application Component can be created with a "
                        "parent_collection_id" if creating
                        else "Only an Application Component can be nested inside a VPC")
    if parent is None or parent.type != "vpc":
        raise RuleError(400, "parent_collection_id must reference an existing, non-deleted VPC "
                        "Collection in the same Architecture")
    if not creating and child_region != parent.region:
        raise RuleError(409, {"error": "region_mismatch", "application_region": child_region,
                              "vpc_region": parent.region})


def check_region_change(*, locked: bool) -> None:
    """010 FR-003: a collection's region locks once it has content."""
    if locked:
        raise RuleError(409, "This collection's region is locked because it already has content")


def check_connector_not_self(from_id: Any, to_id: Any) -> None:
    if from_id == to_id:
        raise RuleError(400, "A connector cannot link a Collection to itself")


def check_connector_ends(from_id: Any, to_id: Any, collection_ids: Iterable[Any]) -> None:
    check_connector_not_self(from_id, to_id)
    ids = set(collection_ids)
    if from_id not in ids or to_id not in ids:
        raise RuleError(400, "Both collections must belong to this Architecture")


def check_selection(provider: str, *, service_code: str, sku: str, pricing_term: str,
                    purchase_option: str, provider_options: dict | None, region: str) -> None:
    """019 (contracts §4, data-model §3): a selection the provider can't price is refused (422,
    with the field), so it's never stored.

    - The price type must be one the provider supports and, when the adapter reports them per
      item (Azure, GCP), one the item publishes (FR-005).
    - The purchase option must be one the provider has (`not_applicable` for Azure and GCP).
    - `provider_options.kind` must belong to the provider.
    - An item the adapter reports price types for must exist in the region.
    """
    if pricing_term not in PROVIDER_PRICE_TYPES.get(provider, frozenset()):
        raise _field_error("pricing_term",
                           f"{provider} does not publish the price type {pricing_term!r}")
    if purchase_option not in PROVIDER_PURCHASE_OPTIONS.get(provider, frozenset()):
        raise _field_error("purchase_option",
                           f"{provider} prices have no purchase option {purchase_option!r}")
    if provider_options is not None:
        kind = provider_options.get("kind")
        if OPTION_PROVIDERS.get(kind) != provider:
            raise _field_error("provider_options",
                               f"{kind!r} options don't apply to a {provider} architecture")
    adapter = get_provider(provider)
    if adapter.reports_price_types:
        snapshot = get_active_snapshot(adapter.code)
        item = adapter.describe(snapshot, [(service_code, sku)], region=region).get(
            (service_code, sku))
        if item is None:
            raise _field_error("sku", f"{service_code} / {sku} is not in the {region} pricing data")
        if pricing_term not in item.price_types:
            raise _field_error(
                "pricing_term",
                f"this item doesn't publish the price type {pricing_term!r} in {region}")


def check_item_count(count: int) -> None:
    if count > MAX_CHANGE_ITEMS:
        raise RuleError(422, f"A proposal can hold at most {MAX_CHANGE_ITEMS} changes; build it "
                        "in parts.")
