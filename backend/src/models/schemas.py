"""Pydantic request/response schemas — the single source of truth for the OpenAPI contract
that `openapi-typescript` generates the frontend's types from (Constitution Principle IV).
Shapes here follow contracts/api.md.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Providers -----------------------------------------------------------------------------


class ProviderOut(BaseModel):
    code: str
    name: str
    active: bool


# --- Regions (010-multi-region-support) ---------------------------------------------------


class RegionOut(BaseModel):
    code: str


class RegionsOut(BaseModel):
    regions: list[RegionOut]


# --- Users and Auth (012-user-accounts-sharing) -------------------------------------------


class CurrentUserOut(BaseModel):
    id: uuid.UUID
    username: str | None
    is_admin: bool
    is_active: bool


class CheckUsernameRequest(BaseModel):
    username: str = Field(min_length=1)


class CheckUsernameOut(BaseModel):
    exists: bool
    has_password: bool


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class AdminUserCreate(BaseModel):
    username: str = Field(min_length=1)


class AdminPasswordUpdate(BaseModel):
    password: str = Field(min_length=1)


class AdminUserActiveUpdate(BaseModel):
    is_active: bool


class AdminUserOut(BaseModel):
    id: uuid.UUID
    username: str
    is_active: bool
    has_password: bool
    # Last 4 characters of the stored password hash string (FR-009) — never the full hash or
    # anything else password-derived.
    password_hash_suffix: str | None
    is_admin: bool
    is_default_admin: bool
    # Non-deleted architectures owned (014-architecture-templates-import-export, FR-012) —
    # the Admin tab disables Export at 0.
    architecture_count: int


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
    # 016-canvas-icon-layout, FR-004a/FR-004b (contracts/api.md §2): moves the service to another
    # box — one in the same Architecture and the same region. Connector-owned services can't move.
    collection_id: uuid.UUID | None = None


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
    # The SKU's catalog product family (e.g. "NAT Gateway"), resolved read-only from Parquet at
    # response time alongside `attributes` and never stored — lets the canvas pick a
    # product-family-specific icon (015-canvas-service-icons, contracts/api.md). `None` when the
    # SKU has no catalog row or its product family is empty.
    product_family: str | None = None


# --- Collection --------------------------------------------------------------------------


class CollectionCreate(BaseModel):
    type: CollectionType
    name: str = Field(min_length=1, max_length=255)
    # 010-multi-region-support, spec FR-001/FR-002: required unless `parent_collection_id` is
    # given, in which case it's ignored server-side in favor of the parent VPC's own region
    # (FR-001a) — never trusted from the client when a parent is supplied.
    region: str | None = None
    parent_collection_id: uuid.UUID | None = None


class CollectionOut(ORMBase):
    id: uuid.UUID
    type: CollectionType
    name: str
    region: str
    parent_collection_id: uuid.UUID | None = None
    sku_selections: list[SKUSelectionOut] = []


class CollectionUpdate(BaseModel):
    """Nest/move/un-nest an Application Component (002-vpc-component-nesting, FR-001-003)
    and/or change a collection's region while it's still unlocked (010-multi-region-support,
    spec FR-003). Both fields are optional so either can be updated independently — the
    endpoint distinguishes "omitted" from "explicitly null" via `model_fields_set`, since
    `parent_collection_id: null` is itself a meaningful request (un-nest)."""

    parent_collection_id: uuid.UUID | None = None
    region: str | None = None


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
    is_public: bool


class ArchitectureDetailOut(ORMBase):
    id: uuid.UUID
    name: str
    provider: str
    created_at: datetime
    is_public: bool
    collections: list[CollectionOut] = []
    connectors: list[DataConnectorOut] = []


class ArchitectureUpdate(BaseModel):
    """Owner-only public/private toggle (012-user-accounts-sharing, spec FR-020)."""

    is_public: bool


class ImportableArchitectureOut(BaseModel):
    id: uuid.UUID
    name: str


class ImportableArchitectureGroupOut(BaseModel):
    owner_username: str
    architectures: list[ImportableArchitectureOut]


class ImportableArchitecturesOut(BaseModel):
    groups: list[ImportableArchitectureGroupOut]


class ArchitectureImportRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


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
    # 018-app-cloud-deployment, FR-059: the revision of `snapshot_date` the rows came from.
    snapshot_revision: int
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
    # 010-multi-region-support, data-model.md: the region this line item is attributed to —
    # its owning Collection's region, or (for a Connector-owned selection) the Connector's
    # "from" Collection's region. `None` is a defensive fallback only, grouped under a
    # "Global" section by the frontend (spec FR-015) — not expected in normal operation, since
    # every Collection has a NOT NULL region and every Connector a NOT NULL from_collection_id.
    region: str | None = None


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
    # 018-app-cloud-deployment, FR-059: a corrected revision is never shown under the same label.
    snapshot_revision: int
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


# --- Architecture export/import file (014-architecture-templates-import-export) --------------
#
# One versioned format serves the Admin tab's Export, its Import, and the checked-in standard-
# architecture seed (contracts/export-format.md). Every definition model ignores unknown fields
# so later non-breaking additions don't break older importers; a breaking change bumps
# `format_version`. Never carries database ids, owners, visibility, or vendor prices (FR-016).

EXPORT_FORMAT = "cloud-pricing-architectures"
SUPPORTED_FORMAT_VERSIONS = frozenset({1})

DefinitionName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]


class SKUSelectionDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    service_code: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    pricing_term: PricingTerm
    purchase_option: PurchaseOption
    # Serialized as a decimal string (preserves `Numeric(18, 4)` exactly); a JSON number is
    # also accepted on import.
    usage_quantity: Decimal = Field(ge=0, decimal_places=4)


class CollectionDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # File-local key, unique within its architecture — never a database id.
    ref: str = Field(min_length=1)
    type: CollectionType
    name: DefinitionName
    region: str = Field(min_length=1)
    parent_ref: str | None = None
    sku_selections: list[SKUSelectionDefinition] = []


class ConnectorDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    from_ref: str = Field(min_length=1)
    to_ref: str = Field(min_length=1)
    sku_selection: SKUSelectionDefinition | None = None


class ArchitectureDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: DefinitionName
    provider: Literal["aws", "gcp", "azure"]
    collections: list[CollectionDefinition] = []
    connectors: list[ConnectorDefinition] = []


class ArchitectureExportFile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    format: Literal["cloud-pricing-architectures"]
    format_version: Literal[1]
    exported_at: datetime
    source_username: str
    architectures: list[ArchitectureDefinition]


class ArchitectureFileImportRequest(BaseModel):
    """The Admin import's request envelope — deliberately loose (research.md §8). Every
    whole-file problem (wrong `format`, unsupported `format_version`, missing or non-list
    `architectures`) must produce this codebase's own `{"error": "invalid_import_file", ...}`
    400 (contracts/api.md), not FastAPI's generic 422 — the same convention
    `CalculateSnapshotRequest.selections` follows — so these are checked explicitly by
    `services/architecture_transfer.validate_envelope`. Each `architectures[]` entry is then
    validated individually against `ArchitectureDefinition`, so one bad entry never fails the
    whole file (FR-020)."""

    model_config = ConfigDict(extra="allow")

    format: Any = None
    format_version: Any = None
    exported_at: Any = None
    source_username: Any = None
    architectures: Any = None


class ImportResult(BaseModel):
    # `None` when the entry has no readable name — the UI shows "(unnamed #n)".
    name: str | None
    status: Literal["success", "failed"]
    error: str | None


class ArchitectureFileImportResponse(BaseModel):
    imported_count: int
    failed_count: int
    results: list[ImportResult]


# --- System information (016-canvas-icon-layout, US5, contracts/api.md §1) --------------------


class WaitingSnapshotOut(BaseModel):
    snapshot_date: str
    reason: str


class IssueOut(BaseModel):
    kind: Literal["missing_icon", "missing_regions", "pinned_incomplete"]
    snapshot_date: str
    message: str
    service_code: str | None = None
    service_name: str | None = None
    is_new: bool | None = None
    regions: list[str] | None = None


class SystemInfoOut(BaseModel):
    active_snapshot_date: str | None
    pinned: bool
    last_check_at: datetime | None
    last_check_error: str | None
    check_interval_seconds: int
    waiting_snapshots: list[WaitingSnapshotOut]
    issues: list[IssueOut]
