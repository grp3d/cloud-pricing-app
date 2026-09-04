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


# --- Collection --------------------------------------------------------------------------


class CollectionCreate(BaseModel):
    type: CollectionType
    name: str = Field(min_length=1, max_length=255)


class CollectionOut(ORMBase):
    id: uuid.UUID
    type: CollectionType
    name: str
    sku_selections: list[SKUSelectionOut] = []


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


class CatalogSearchResult(BaseModel):
    results: list[CatalogSKUOut]
    next_cursor: str | None = None
    snapshot_date: str


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


class CalculationWarning(BaseModel):
    code: str
    message: str


class CalculationResult(BaseModel):
    snapshot_date: str
    total_price: Decimal
    currency: str = "USD"
    line_items: list[PriceLineItem]
    unpriceable: list[UnpriceableItem]
    warnings: list[CalculationWarning]
