"""Pydantic request/response schemas — the single source of truth for the OpenAPI contract
that `openapi-typescript` generates the frontend's types from (Constitution Principle IV).
Shapes here follow contracts/api.md.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Providers -----------------------------------------------------------------------------


class ProviderOut(BaseModel):
    code: str
    name: str
    active: bool


# --- Enums (mirror the DB check constraints in models/orm.py) ------------------------------


class CollectionType(str, Enum):
    application_component = "application_component"
    vpc = "vpc"


class PricingTerm(str, Enum):
    on_demand = "on_demand"
    reserved_1yr = "reserved_1yr"
    reserved_3yr = "reserved_3yr"


class PurchaseOption(str, Enum):
    no_upfront = "no_upfront"
    partial_upfront = "partial_upfront"
    all_upfront = "all_upfront"
    not_applicable = "not_applicable"


class CalculationDuration(str, Enum):
    """The period a calculated total is scoped to (004, FR-001). Day-counts used for proration
    are fixed per FR-006: 1 day, 31 days, 365 days."""

    one_day = "1_day"
    one_month = "1_month"
    one_year = "1_year"


# --- SKU Selection ---------------------------------------------------------------------------


class SKUSelectionCreate(BaseModel):
    service_code: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    pricing_term: PricingTerm
    purchase_option: PurchaseOption
    usage_quantity: Decimal = Field(gt=0)


class SKUSelectionUpdate(BaseModel):
    pricing_term: PricingTerm | None = None
    purchase_option: PurchaseOption | None = None
    usage_quantity: Decimal | None = Field(default=None, gt=0)


class SKUSelectionOut(ORMBase):
    id: uuid.UUID
    service_code: str
    sku: str
    pricing_term: PricingTerm
    purchase_option: PurchaseOption
    usage_quantity: Decimal
    # Resolved read-only from the AWS Pricing Catalog at response time (never a stored
    # column) — attached by the endpoint after construction, since Pydantic's ORM-attribute
    # serialization has no DuckDB access. `None` when unpriceable (003, FR-004/FR-005).
    unit: str | None = None
    # Full descriptive attributes, mirroring CatalogSKUOut.attributes (003) — {} (never null)
    # when unavailable. Lets the canvas diagram show an identifying detail per service without
    # a second catalog lookup (004, FR-014).
    attributes: dict[str, str] = {}


# --- Collection --------------------------------------------------------------------------


class CollectionCreate(BaseModel):
    type: CollectionType
    name: str = Field(min_length=1, max_length=255)


class CollectionOut(ORMBase):
    id: uuid.UUID
    type: CollectionType
    name: str
    parent_collection_id: uuid.UUID | None = None
    sku_selections: list[SKUSelectionOut] = []


class CollectionNestingUpdate(BaseModel):
    """Nest, move, or un-nest an Application Component (002-vpc-component-nesting, FR-001-003)."""

    parent_collection_id: uuid.UUID | None


# --- Data Connector ------------------------------------------------------------------------


class DataConnectorCreate(BaseModel):
    from_collection_id: uuid.UUID
    to_collection_id: uuid.UUID


class DataConnectorOut(ORMBase):
    id: uuid.UUID
    from_collection_id: uuid.UUID
    to_collection_id: uuid.UUID
    sku_selection: SKUSelectionOut | None = None


# --- Architecture ------------------------------------------------------------------------


class ArchitectureCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    provider: str = Field(default="aws")


class ArchitectureSummaryOut(ORMBase):
    id: uuid.UUID
    name: str
    provider: str
    created_at: datetime


class ArchitectureDetailOut(ORMBase):
    id: uuid.UUID
    name: str
    provider: str
    created_at: datetime
    collections: list[CollectionOut] = []
    connectors: list[DataConnectorOut] = []


# --- Catalog search ------------------------------------------------------------------------


class CatalogSKUOut(BaseModel):
    service_code: str
    service_name: str
    product_family: str
    sku: str
    summary: str
    # Full descriptive attributes as a flat key/value map — {} (never null) when none are
    # available (003, FR-001/FR-002/FR-003).
    attributes: dict[str, str] = {}
    # Billing unit, e.g. "Hrs", "GB-Mo" — null if this SKU has no price data at all
    # (003, FR-004/FR-005).
    unit: str | None = None


class CatalogSearchResult(BaseModel):
    results: list[CatalogSKUOut]
    next_cursor: str | None = None
    snapshot_date: str
    # 008-ui-updates-corrections, FR-024, data-model.md — the true count of every catalog
    # row matching the current filters, independent of how many are returned in `results`
    # (capped at 200, FR-023). Drives the "(n of m results displayed)" indicator.
    total: int


# --- Price calculation ---------------------------------------------------------------------


class PriceLineItem(BaseModel):
    sku_selection_id: uuid.UUID
    service_code: str
    sku: str
    price: Decimal | None
    priceable: bool


class UnpriceableItem(BaseModel):
    sku_selection_id: uuid.UUID
    service_code: str
    sku: str
    reason: str
    # The Architecture component(s) containing this service — a Collection's name, or a Data
    # Connector description (e.g. "Data Connector between X and Y") — so a user can find and
    # fix it directly (004, FR-012/FR-013). Covers both this class's original "no price" case
    # and 004's new duration-unrecognized-unit case, in one combined list (spec Clarifications).
    components: list[str] = []


class CalculationWarning(BaseModel):
    code: str
    message: str


class CalculationResult(BaseModel):
    snapshot_date: str
    # Echoes the CalculationDuration the total was computed for (004, FR-001) — every price
    # below reflects proration to this duration per FR-002/003/004.
    duration: CalculationDuration
    total_price: Decimal
    currency: str = "USD"
    line_items: list[PriceLineItem]
    unpriceable: list[UnpriceableItem]
    warnings: list[CalculationWarning]


# --- Snapshot calculation (008-ui-updates-corrections, FR-016a, contracts/api.md,
# data-model.md) — prices an arbitrary, caller-supplied set of SKU selections, independent
# of any persisted Architecture. Exists to compute a duration-adjusted comparison total for
# Price Change (research.md §5) when both an architecture's contents and its Duration
# selection have changed since the last accepted calculation. ---------------------------------


class SnapshotSelection(BaseModel):
    """One prior SKU selection's pricing inputs — a plain value, not a reference to a live
    row (data-model.md): the row it originally came from may since have been edited or
    deleted, so this intentionally carries no `sku_selection_id`/foreign key."""

    service_code: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    pricing_term: PricingTerm
    purchase_option: PurchaseOption
    usage_quantity: Decimal = Field(gt=0)


class CalculateSnapshotRequest(BaseModel):
    # The *new* Duration to price the snapshot at (FR-016a) — not necessarily the Duration
    # the selections were originally priced at.
    duration: CalculationDuration
    # Deliberately unconstrained here (no `min_length=1`): an empty list must produce this
    # codebase's own `{"error": "empty_snapshot", ...}` 400 shape (contracts/api.md), not
    # FastAPI/Pydantic's generic 422 validation-error shape — so emptiness is checked and
    # raised explicitly in the endpoint (src/api/calculate.py), matching the
    # `EmptyCatalogFilterError` convention already used for catalog search.
    selections: list[SnapshotSelection]
