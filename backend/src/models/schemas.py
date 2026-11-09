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

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    field_validator,
    model_validator,
)

from src.pricing_data.providers.base import OPTION_PROVIDERS


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Providers -----------------------------------------------------------------------------


class ProviderOut(BaseModel):
    code: str
    name: str
    # 019 (contracts §1, FR-001): true exactly when the provider has a usable active snapshot
    # and the app can price it.
    active: bool
    status: Literal["current", "partial", "failed", "stale", "none"] = "none"
    # A short public phrase when not `current`; never a location or an error text.
    reason: str | None = None
    snapshot_date: str | None = None
    snapshot_revision: int | None = None


# --- Regions (010-multi-region-support) ---------------------------------------------------


class RegionOut(BaseModel):
    code: str
    # 019 (contracts §2): the provider's own name for the region (Azure `US East`); the code
    # when the provider publishes none (AWS, GCP).
    display_name: str | None = None


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
    # 019 (research R6): Azure savings plans and GCP committed-use discounts. Which ones a
    # selection may use depends on its architecture's provider (`PROVIDER_PRICE_TYPES`).
    savings_plan_1yr = "savings_plan_1yr"
    savings_plan_3yr = "savings_plan_3yr"
    commitment_1yr = "commitment_1yr"
    commitment_3yr = "commitment_3yr"


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


ProviderCode = Literal["aws", "gcp", "azure"]


class CatalogKind(str, Enum):
    """019 (contracts §3, research R6): search presets matching the pipeline's reference
    lookups. Azure and GCP only."""

    vm = "vm"
    block_storage = "block_storage"
    object_storage = "object_storage"
    data_transfer = "data_transfer"
    managed_db = "managed_db"


class GcpMachineOptions(BaseModel):
    """019 (research R6): a GCP machine priced as vCPUs × core rate + GiB × RAM rate. The
    selection's `sku` is the core SKU; `ram_sku` is the matching RAM SKU."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["gcp_machine"]
    version: Literal[1] = 1
    vcpus: int = Field(gt=0)
    memory_gib: Decimal = Field(gt=0)
    ram_sku: str = Field(min_length=1)


class AzureVmOptions(BaseModel):
    """019 (research R6): which Azure VM meter to price, by operating system."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["azure_vm"]
    version: Literal[1] = 1
    os: Literal["linux", "windows"]


# A selection's provider-specific options; null means the common pricing path (data-model §3).
ProviderOptions = Annotated[GcpMachineOptions | AzureVmOptions, Field(discriminator="kind")]


class SKUSelectionCreate(BaseModel):
    service_code: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    pricing_term: PricingTerm
    purchase_option: PurchaseOption
    usage_quantity: Decimal = Field(gt=0)
    # 019 (contracts §4): must match the architecture's provider.
    provider_options: ProviderOptions | None = None


class SKUSelectionUpdate(BaseModel):
    pricing_term: PricingTerm | None = None
    purchase_option: PurchaseOption | None = None
    usage_quantity: Decimal | None = Field(default=None, gt=0)
    # 019: sent → replaced (null clears it); not sent → unchanged.
    provider_options: ProviderOptions | None = None
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
    provider_options: ProviderOptions | None = None
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
    # 019 (FR-005): the item's published price types and search kind, from the provider
    # adapter at response time, so the Service Editor offers only what the item publishes.
    # Empty / null when the provider doesn't report them (AWS) or the item isn't found.
    price_types: list[PricingTerm] = []
    kind: CatalogKind | None = None
    # 020 (contracts/api.md §2, research R7): the provider's display name of the selection's
    # service (e.g. "Compute Engine"), resolved read-only at response time like
    # `product_family` and never stored — the GCP / Azure fallback tile shows it. `None` when
    # the item isn't in the active snapshot, and always for AWS, whose icons never need it.
    service_name: str | None = None
    # 021 (US7, FR-044): the item's own description, as the catalog search shows it (e.g.
    # "Multi-Region HNS Nearline Class A Operations"), resolved at response time like
    # `service_name` and never stored. `None` when the item isn't in the active snapshot, and
    # for AWS, whose readable details come from `attributes`.
    summary: str | None = None


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


# 019 (FR-026, data-model §5): how a connector's line is drawn. Visual only: pricing always
# uses `from` → `to`.
ArrowStyle = Literal["none", "one_way", "two_way", "one_to_many", "many_to_one"]


class DataConnectorCreate(BaseModel):
    from_collection_id: uuid.UUID
    to_collection_id: uuid.UUID
    arrow_style: ArrowStyle = "none"
    arrow_reversed: StrictBool = False


class DataConnectorUpdate(BaseModel):
    """019 (contracts §6): `PATCH /connectors/{id}`; only the fields sent change."""

    model_config = ConfigDict(extra="forbid")

    arrow_style: ArrowStyle | None = None
    arrow_reversed: StrictBool | None = None


class DataConnectorOut(ORMBase):
    id: uuid.UUID
    from_collection_id: uuid.UUID
    to_collection_id: uuid.UUID
    arrow_style: ArrowStyle = "none"
    arrow_reversed: bool = False
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
    """Owner-only update: the public/private toggle (012-user-accounts-sharing, spec FR-020)
    and, from 021 (US6, FR-043), the name. Only the fields sent change; at least one is
    required."""

    is_public: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @model_validator(mode="after")
    def _something_to_change(self) -> ArchitectureUpdate:
        if self.is_public is None and self.name is None:
            raise ValueError("send is_public, name, or both")
        return self


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
    # 019 (contracts §3): optional, so AWS results are unchanged.
    provider: str = "aws"
    location_scope: Literal["regional", "multi_regional", "global"] = "regional"
    kind: CatalogKind | None = None
    # The price types this item publishes (FR-005); empty when the provider doesn't report
    # them per item (AWS).
    price_types: list[PricingTerm] = []


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


class PriceComponentOut(BaseModel):
    """019 (contracts §5): one part of a composite price, e.g. a GCP machine's cores or RAM."""

    label: str
    sku: str
    quantity: Decimal
    rate: Decimal
    cost: Decimal


class TierPartOut(BaseModel):
    """019 (contracts §5, research R8): the part of a line's quantity priced at one tier.
    `from_quantity`/`to_quantity` are the published monthly bounds (`to_quantity` null for an
    open top tier); `quantity` and `cost` are what the part contributes to the requested
    duration, so the parts add up to the line's price."""

    from_quantity: Decimal
    to_quantity: Decimal | None
    rate: Decimal
    quantity: Decimal
    cost: Decimal


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
    # 019 (contracts §5): the tier breakdown of a tiered price; null when not tiered.
    tiers: list[TierPartOut] | None = None
    # 019 (contracts §5): how the provider names the price type (e.g. "Savings plan, 1 year").
    price_type_label: str | None = None
    # 019 (contracts §5): the parts of a composite price (`gcp_machine`); null otherwise.
    components: list[PriceComponentOut] | None = None


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
    # 020 (data-model §2): the region the selection was priced in (its box's, or a connector's
    # "from" box's). Missing or null → `AWS_PRICING_REGION`, the v0.0.2 behaviour.
    region: str | None = None
    # 020: the selection's provider-specific options, validated against the request's provider.
    provider_options: ProviderOptions | None = None


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
    # 020 (contracts/api.md §1): the architecture's provider. Missing → `aws`, as elsewhere.
    provider: ProviderCode | None = None

    @model_validator(mode="after")
    def _options_match_provider(self) -> CalculateSnapshotRequest:
        """Each selection's options must belong to the request's provider (422 otherwise), the
        same rule selection create and update apply."""
        provider = self.provider or "aws"
        for selection in self.selections:
            options = selection.provider_options
            if options is not None and OPTION_PROVIDERS.get(options.kind) != provider:
                raise ValueError(
                    f"{options.kind!r} options don't apply to a {provider} architecture"
                )
        return self


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
    # 019 (research R15): optional, so older files import unchanged.
    provider_options: ProviderOptions | None = None


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
    # 019 (research R15): optional. A file from before 019 has none, and every connector was
    # drawn with an arrowhead then, so it imports as `one_way` (as migration 0008 does).
    arrow_style: ArrowStyle = "one_way"
    arrow_reversed: bool = False
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


# --- Health (018-app-cloud-deployment, FR-028, contracts/admin-api.md) ----------------------


class HealthOut(BaseModel):
    status: Literal["ok"]
    pricing: Literal["ok", "unavailable"]
    # A fixed phrase ("no snapshot available", "data source unreachable", …), never a location,
    # a credential or an exception text: /health is public.
    pricing_reason: str | None = None


# --- System information (016-canvas-icon-layout, US5, contracts/api.md §1) --------------------


class IssueOut(BaseModel):
    kind: Literal["missing_icon", "missing_regions"]
    snapshot_date: str
    message: str
    service_code: str | None = None
    service_name: str | None = None
    is_new: bool | None = None
    regions: list[str] | None = None


# 018-app-cloud-deployment, FR-014 (contracts/admin-api.md).


class DeploymentOut(BaseModel):
    environment: str
    release: str


class SourceOut(BaseModel):
    kind: Literal["local", "s3"]
    # The local root or s3://bucket[/prefix] — never credentials.
    location: str
    provider: str


class FailedRegionOut(BaseModel):
    region: str
    reason: str
    attempts: int


class ActiveSnapshotOut(BaseModel):
    snapshot_date: str
    revision: int
    run_id: str
    pipeline_version: str
    created_at: str
    pinned: bool
    regions: list[str]
    failed_regions: list[FailedRegionOut]


class LatestRunOut(BaseModel):
    snapshot_date: str
    revision: int
    status: Literal["succeeded", "partial", "failed", "purged"]
    failed_regions: list[FailedRegionOut]


class RejectedOut(BaseModel):
    snapshot_date: str | None
    revision: int | None
    reason: str


class CacheEntryOut(BaseModel):
    snapshot_date: str
    revision: int
    state: Literal["active", "cached"]
    bytes: int


class CacheOut(BaseModel):
    total_bytes: int
    max_bytes: int
    entries: list[CacheEntryOut]


class ProviderSystemOut(BaseModel):
    """019 (contracts §9, FR-009): one provider's snapshot state in the Admin tab."""

    name: str
    status: Literal["current", "partial", "failed", "stale", "none"]
    reason: str | None
    checked: bool
    active_snapshot: ActiveSnapshotOut | None
    latest_run: LatestRunOut | None
    rejected: RejectedOut | None
    last_check_error: str | None
    issues: list[IssueOut]
    history: HistoryOut | None = None


class SystemInfoOut(BaseModel):
    deployment: DeploymentOut
    source: SourceOut
    # The top-level snapshot fields are AWS's, unchanged (018); every provider is in
    # `providers` (019).
    active: ActiveSnapshotOut | None
    latest_run: LatestRunOut | None
    rejected: RejectedOut | None
    cache: CacheOut | None
    last_check_at: datetime | None
    last_check_error: str | None
    check_interval_seconds: int
    issues: list[IssueOut]
    providers: dict[str, ProviderSystemOut] = {}


class SnapshotCheckStartedOut(BaseModel):
    started: bool


# --- User preferences (019, data-model §1, contracts §7, research R12) -----------------------

ColumnKey = Literal["col1", "col2", "col3", "col4"]
TrendsCategory = Literal["all", "compute", "storage", "database", "networking"]


class _Strict(BaseModel):
    """Unknown keys are rejected (data-model §1): new preferences extend these models."""

    model_config = ConfigDict(extra="forbid")


InspectorTab = Literal["pricing", "service"]


class InspectorArrangement(_Strict):
    """The workspace inspector's tab layout (021, data-model §1). All fields are required when
    the arrangement is sent; `upper` and `front` are both kept in either mode so a split ->
    merge -> split round trip restores the previous split."""

    mode: Literal["merged", "split"]
    upper: InspectorTab
    front: InspectorTab
    split: float = Field(ge=0.2, le=0.8)


class WorkspacePreferences(_Strict):
    column_widths: dict[ColumnKey, int] | None = None
    collapsed: dict[ColumnKey, bool] | None = None
    last_provider: ProviderCode | None = None
    inspector: InspectorArrangement | None = None

    @field_validator("column_widths")
    @classmethod
    def _positive_widths(cls, widths: dict[str, int] | None) -> dict[str, int] | None:
        if widths and any(w <= 0 for w in widths.values()):
            raise ValueError("column widths must be positive")
        return widths


class ChartProviderSelection(_Strict):
    provider: ProviderCode
    # Empty means all of the provider's regions.
    regions: list[Annotated[str, StringConstraints(min_length=1, max_length=64)]] = []


class TrendsChartsPreferences(_Strict):
    providers: list[ChartProviderSelection] = []
    category: TrendsCategory = "all"


class TrendsMoversPreferences(_Strict):
    provider: ProviderCode
    category: TrendsCategory = "all"
    regions: list[Annotated[str, StringConstraints(min_length=1, max_length=64)]] = []
    period_weeks: Literal[1, 4, 13, 52] = 52


class TrendsPreferences(_Strict):
    charts: TrendsChartsPreferences | None = None
    movers: TrendsMoversPreferences | None = None


class Preferences(_Strict):
    migrated_from_browser: bool = False
    workspace: WorkspacePreferences | None = None
    trends: TrendsPreferences | None = None


class PreferencesOut(BaseModel):
    schema_version: int
    data: Preferences


class PreferencesPatch(_Strict):
    """Each section sent replaces that section; sections not sent are kept (research R12).
    `trends.charts` and `trends.movers` are separate sections, so the two Resets never
    overwrite each other. Sending a section as null clears it back to the defaults."""

    migrated_from_browser: bool | None = None
    workspace: WorkspacePreferences | None = None
    trends: TrendsPreferences | None = None


# --- Trends (019, contracts §8) ----------------------------------------------------------------


class SkusChangedPointOut(BaseModel):
    week: str
    from_snapshot: str
    to_snapshot: str
    # Null when nothing was compared that week ("no data"), never 0.
    increased: int | None
    decreased: int | None
    increased_pct: float | None
    decreased_pct: float | None
    compared: int | None
    excluded: int | None
    gap: bool


TrendStatus = Literal["ok", "building", "not_enough_history", "provider_unavailable"]


class TrendSeriesOut(BaseModel):
    provider: ProviderCode
    regions: list[str]
    status: TrendStatus
    reason: str | None = None
    weeks_built: int
    weeks_total: int
    points: list[SkusChangedPointOut]


class TrendSeriesResult(BaseModel):
    metric: Literal["skus_changed"] = "skus_changed"
    category: TrendsCategory
    series: list[TrendSeriesOut]


class MoverOut(BaseModel):
    service_name: str
    description: str
    region: str
    unit: str
    # Decimal strings exactly as published (FR-019).
    start_price: str
    end_price: str
    change_pct: float  # rounded to 2 decimal places
    tier_note: str | None = None


class MoversOut(BaseModel):
    """019 (contracts §8): the biggest movers for one provider, category, regions and period.
    `status` and `reason` (added to the contract) say why the lists are empty when there is no
    usable history: the same values as a chart series."""

    provider: ProviderCode
    category: TrendsCategory
    regions: list[str]
    period_weeks: Literal[1, 4, 13, 52]
    status: TrendStatus
    reason: str | None = None
    from_snapshot: str | None
    to_snapshot: str | None
    weeks_available: int
    increases: list[MoverOut]
    decreases: list[MoverOut]
    message: str | None = None


class HistoryOut(BaseModel):
    """019 (contracts §9): one provider's price history in the Admin tab."""

    weeks_built: int
    weeks_total: int
    gaps: list[str]
    backfill: Literal["pending", "running", "done", "failed"]
    last_error: str | None
    last_built_at: str | None
