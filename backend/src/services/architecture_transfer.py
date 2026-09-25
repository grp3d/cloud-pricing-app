"""Architecture transfer: export serialization, import validation, and the shared row builder
(014-architecture-templates-import-export, research.md §8-§10, data-model.md).

One module owns every way an Architecture's rows get *created from a description* rather than
edited in place:

- `build_architecture` — the single place that turns a set of collection/connector specs into
  new ORM rows, remapping every file-local (or source-row) reference to the new rows' ids. Used
  by the 012 public-architecture copy (`architecture_import.py`) and by the Admin file import.
- `validate_envelope` / `validate_definition` — the Admin import's whole-file and
  per-architecture checks, in data-model.md's documented order, with the exact user-facing
  error messages the import status popup shows (FR-019, FR-021).

Nothing here ever reads or writes a vendor price (Constitution Principle I/II): SKUs are
carried and checked only as `(service_code, sku)` references.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm import Architecture, Collection, DataConnector, SKUSelection, User
from src.models.schemas import (
    EXPORT_FORMAT,
    SUPPORTED_FORMAT_VERSIONS,
    ArchitectureDefinition,
    ArchitectureExportFile,
    ArchitectureFileImportResponse,
    CollectionDefinition,
    ConnectorDefinition,
    ImportResult,
    SKUSelectionDefinition,
)
from src.pricing_data.catalog import find_existing_skus
from src.pricing_data.regions import list_available_regions

# Only AWS has pricing data today (Constitution III: provider is modeled, not assumed — this is
# a data-availability check, not a structural one).
_SUPPORTED_PROVIDERS = frozenset({"aws"})

ExistingSkusLookup = Callable[[str, set[tuple[str, str]]], set[tuple[str, str]]]


class InvalidImportFileError(ValueError):
    """The import file as a whole isn't in the export format (FR-019) — nothing is imported."""


# --- Shared row builder ------------------------------------------------------------------


@dataclass(frozen=True)
class SKUSelectionSpec:
    service_code: str
    sku: str
    pricing_term: str
    purchase_option: str
    usage_quantity: Decimal


@dataclass(frozen=True)
class CollectionSpec:
    ref: str
    type: str
    name: str
    region: str
    parent_ref: str | None = None
    sku_selections: Sequence[SKUSelectionSpec] = field(default_factory=tuple)


@dataclass(frozen=True)
class ConnectorSpec:
    from_ref: str
    to_ref: str
    sku_selection: SKUSelectionSpec | None = None


def build_architecture(
    session: AsyncSession,
    *,
    owner: User,
    name: str,
    provider: str,
    collections: Sequence[CollectionSpec],
    connectors: Sequence[ConnectorSpec],
) -> Architecture:
    """Add a brand-new, private Architecture and all its rows to `session` (not committed).

    Every row gets an explicit `uuid.uuid4()` id up front (not the ORM's flush-time default),
    so `parent_ref`/`from_ref`/`to_ref` can be remapped to the *new* rows before anything is
    flushed. Collections and SKU selections get `created_at = clock_timestamp()` (distinct and
    increasing within one transaction, unlike the `now()` server default) because both are
    displayed in `created_at` order (orm.py) — so a copy keeps its source's service order
    (spec SC-004). `collections` must list every parent before its children — true of both callers'
    sources (`created_at` order, and the export format's documented order) — so a single
    left-to-right pass always finds a parent already mapped.
    """
    architecture = Architecture(
        id=uuid.uuid4(), user_id=owner.id, name=name, provider=provider, is_public=False
    )
    session.add(architecture)

    ref_to_id: dict[str, uuid.UUID] = {}
    for spec in collections:
        collection_id = uuid.uuid4()
        session.add(
            Collection(
                id=collection_id,
                architecture=architecture,
                type=spec.type,
                name=spec.name,
                region=spec.region,
                parent_collection_id=(
                    ref_to_id.get(spec.parent_ref) if spec.parent_ref is not None else None
                ),
                created_at=func.clock_timestamp(),
            )
        )
        ref_to_id[spec.ref] = collection_id
        for selection in spec.sku_selections:
            session.add(_sku_selection(selection, collection_id=collection_id))

    for spec in connectors:
        connector_id = uuid.uuid4()
        session.add(
            DataConnector(
                id=connector_id,
                architecture=architecture,
                from_collection_id=ref_to_id[spec.from_ref],
                to_collection_id=ref_to_id[spec.to_ref],
            )
        )
        if spec.sku_selection is not None:
            session.add(_sku_selection(spec.sku_selection, connector_id=connector_id))

    return architecture


def _sku_selection(
    spec: SKUSelectionSpec,
    *,
    collection_id: uuid.UUID | None = None,
    connector_id: uuid.UUID | None = None,
) -> SKUSelection:
    return SKUSelection(
        id=uuid.uuid4(),
        collection_id=collection_id,
        connector_id=connector_id,
        service_code=spec.service_code,
        sku=spec.sku,
        pricing_term=spec.pricing_term,
        purchase_option=spec.purchase_option,
        usage_quantity=spec.usage_quantity,
        created_at=func.clock_timestamp(),
    )


def specs_from_definition(
    definition: ArchitectureDefinition,
) -> tuple[list[CollectionSpec], list[ConnectorSpec]]:
    """Convert a validated export-format definition into builder specs."""

    def _selection(s) -> SKUSelectionSpec:
        return SKUSelectionSpec(
            service_code=s.service_code,
            sku=s.sku,
            pricing_term=s.pricing_term.value,
            purchase_option=s.purchase_option.value,
            usage_quantity=s.usage_quantity,
        )

    collections = [
        CollectionSpec(
            ref=c.ref,
            type=c.type.value,
            name=c.name,
            region=c.region,
            parent_ref=c.parent_ref,
            sku_selections=tuple(_selection(s) for s in c.sku_selections),
        )
        for c in definition.collections
    ]
    connectors = [
        ConnectorSpec(
            from_ref=c.from_ref,
            to_ref=c.to_ref,
            sku_selection=_selection(c.sku_selection) if c.sku_selection is not None else None,
        )
        for c in definition.connectors
    ]
    return collections, connectors


# --- Export ------------------------------------------------------------------------------

_QUANTITY = Decimal("0.0001")


def _selection_definition(selection: SKUSelection) -> SKUSelectionDefinition:
    return SKUSelectionDefinition(
        service_code=selection.service_code,
        sku=selection.sku,
        pricing_term=selection.pricing_term,
        purchase_option=selection.purchase_option,
        usage_quantity=Decimal(selection.usage_quantity).quantize(_QUANTITY),
    )


def _created_order(row) -> tuple:
    # `created_at` then id: a stable, deterministic order even for rows sharing a timestamp.
    return (row.created_at or datetime.min, str(row.id))


def serialize_architecture(architecture: Architecture) -> ArchitectureDefinition:
    """One live architecture in the export format (contracts/export-format.md).

    Soft-deleted collections and connectors are left out, as is any connector touching a
    removed collection. Collections are emitted parents-first (every VPC, then the application
    components nested in them), each group in creation order, with file-local refs `c1..cn`.
    Carries no ids, owner, visibility, or prices (FR-016).
    """
    live = [c for c in architecture.collections if c.deleted_at is None]
    roots = sorted((c for c in live if c.parent_collection_id is None), key=_created_order)
    children = sorted((c for c in live if c.parent_collection_id is not None), key=_created_order)
    ordered = roots + children
    refs = {c.id: f"c{index}" for index, c in enumerate(ordered, start=1)}

    collections = [
        CollectionDefinition(
            ref=refs[c.id],
            type=c.type,
            name=c.name,
            region=c.region,
            # A parent removed without its child (not expected, but possible in old data)
            # simply leaves the child top-level rather than emitting a dangling ref.
            parent_ref=refs.get(c.parent_collection_id),
            sku_selections=[
                _selection_definition(s) for s in sorted(c.sku_selections, key=_created_order)
            ],
        )
        for c in ordered
    ]
    connectors = [
        ConnectorDefinition(
            from_ref=refs[c.from_collection_id],
            to_ref=refs[c.to_collection_id],
            sku_selection=(
                _selection_definition(c.sku_selection) if c.sku_selection is not None else None
            ),
        )
        for c in sorted(architecture.connectors, key=_created_order)
        if c.deleted_at is None and c.from_collection_id in refs and c.to_collection_id in refs
    ]
    return ArchitectureDefinition(
        name=architecture.name,
        provider=architecture.provider,
        collections=collections,
        connectors=connectors,
    )


def serialize_user_architectures(
    architectures: Iterable[Architecture], *, username: str, now: datetime
) -> ArchitectureExportFile:
    """Every live architecture of one user as a single export document (FR-015, FR-017)."""
    return ArchitectureExportFile(
        format=EXPORT_FORMAT,
        format_version=1,
        exported_at=now,
        source_username=username,
        architectures=[
            serialize_architecture(a)
            for a in sorted(architectures, key=_created_order)
            if a.deleted_at is None
        ],
    )


# --- Import validation -------------------------------------------------------------------


def validate_envelope(doc: Any) -> None:
    """Whole-file check (FR-019). Raises `InvalidImportFileError` with a short, user-facing
    reason; otherwise the file's entries go on to per-architecture validation."""
    if not isinstance(doc, dict):
        raise InvalidImportFileError("the file is not in the expected format")
    if doc.get("format") != EXPORT_FORMAT:
        raise InvalidImportFileError("the file is not an architecture export")
    version = doc.get("format_version")
    # `bool` is an `int` subclass — `true` must not pass as version 1.
    if not isinstance(version, int) or isinstance(version, bool) or (
        version not in SUPPORTED_FORMAT_VERSIONS
    ):
        raise InvalidImportFileError(f"unsupported file version: {version!r}")
    if not isinstance(doc.get("architectures"), list):
        raise InvalidImportFileError("the file has no architectures list")


def entry_name(raw: Any) -> str | None:
    """Best-effort readable name for a (possibly invalid) entry, for the status popup."""
    if isinstance(raw, dict) and isinstance(raw.get("name"), str) and raw["name"].strip():
        return raw["name"].strip()
    return None


def definition_sku_pairs(
    definition: ArchitectureDefinition,
) -> dict[str, set[tuple[str, str]]]:
    """Every `(service_code, sku)` the definition references, grouped by the region it will be
    priced in: its collection's region, or — for a connector's selection — its `from`
    collection's region (the existing pricing rule, 010-multi-region-support FR-006)."""
    regions = {c.ref: c.region for c in definition.collections}
    pairs: dict[str, set[tuple[str, str]]] = {}
    for collection in definition.collections:
        for s in collection.sku_selections:
            pairs.setdefault(collection.region, set()).add((s.service_code, s.sku))
    for connector in definition.connectors:
        if connector.sku_selection is not None and connector.from_ref in regions:
            s = connector.sku_selection
            pairs.setdefault(regions[connector.from_ref], set()).add((s.service_code, s.sku))
    return pairs


def validate_definition(
    raw: Any,
    *,
    taken_names: set[str],
    available_regions: set[str],
    existing_skus: ExistingSkusLookup,
) -> tuple[ArchitectureDefinition | None, str | None]:
    """Validate one `architectures[]` entry against data-model.md's rules, in order, returning
    `(definition, None)` or `(None, <first failure message>)` (FR-021).

    `existing_skus(region, pairs)` returns the subset of `pairs` present in that region's
    pricing data — injected so callers can batch the DuckDB lookup across a whole file.
    """
    # Rule 1 — shape.
    try:
        definition = ArchitectureDefinition.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first["loc"]) or "entry"
        return None, f"Invalid architecture definition: {location} {first['msg']}"

    # Rule 2 — name uniqueness for the target user (including earlier entries of this file).
    if definition.name in taken_names:
        return None, "Architecture name already exists"

    # Rule 3 — references resolve within this architecture.
    by_ref: dict[str, Any] = {}
    for collection in definition.collections:
        if collection.ref in by_ref:
            return None, f'Invalid reference: duplicate collection ref "{collection.ref}"'
        by_ref[collection.ref] = collection
    for collection in definition.collections:
        if collection.parent_ref is not None and collection.parent_ref not in by_ref:
            return None, (
                f'Invalid reference: "{collection.name}" has unknown parent '
                f'"{collection.parent_ref}"'
            )
    for connector in definition.connectors:
        for ref in (connector.from_ref, connector.to_ref):
            if ref not in by_ref:
                return None, f'Invalid reference: connector points to unknown collection "{ref}"'
        if connector.from_ref == connector.to_ref:
            return None, (
                f'Invalid reference: connector links collection "{connector.from_ref}" to itself'
            )

    # Rule 4 — nesting: only an application component may have a parent, and it must be a VPC
    # (mirrors the DB constraint + service-layer rule from 002-vpc-component-nesting). A parent
    # must also appear before its child, which the builder's single pass relies on.
    seen: set[str] = set()
    for collection in definition.collections:
        if collection.parent_ref is not None:
            if collection.type.value == "vpc":
                return None, f'Invalid nesting: VPC "{collection.name}" cannot be nested'
            parent = by_ref[collection.parent_ref]
            if parent.type.value != "vpc" or collection.parent_ref not in seen:
                return None, f'Invalid nesting: "{collection.name}" must be inside a VPC'
        seen.add(collection.ref)

    # Rule 4a — provider has pricing data.
    if definition.provider not in _SUPPORTED_PROVIDERS:
        return None, f"Provider not supported: {definition.provider}"

    # Rule 5 — regions exist in the pricing data.
    for collection in definition.collections:
        if collection.region not in available_regions:
            return None, f"Region not available in pricing data: {collection.region}"

    # Rule 6 — every referenced SKU exists in the region it will be priced in.
    for region, pairs in sorted(definition_sku_pairs(definition).items()):
        missing = sorted(pairs - existing_skus(region, pairs))
        if missing:
            service_code, sku = missing[0]
            return None, f"Service not found in pricing data: {service_code} / {sku} ({region})"

    return definition, None


# --- Admin file import -------------------------------------------------------------------


async def import_architectures(
    session: AsyncSession, *, owner: User, doc: Any
) -> ArchitectureFileImportResponse:
    """Import every valid architecture in an export-format document into `owner`'s account
    (spec FR-018-FR-023, research.md §8-§9).

    - A bad envelope raises `InvalidImportFileError` before anything is read or written.
    - Every SKU the file references is checked against the pricing data up front — one batched
      query per region for the whole file, never one per SKU — so a pricing-data outage
      (`PricingDataUnavailableError`, 503) aborts with nothing written.
    - Each entry is then validated on its own and, if valid, inserted inside its own SAVEPOINT:
      an invalid or unsaveable entry leaves nothing behind and never blocks the others.
    - Results come back in file order; imported architectures are private and owned by `owner`.
    """
    validate_envelope(doc)
    entries: list[Any] = doc["architectures"]

    taken_names = set(
        (
            await session.execute(
                select(Architecture.name).where(
                    Architecture.user_id == owner.id, Architecture.deleted_at.is_(None)
                )
            )
        ).scalars()
    )
    available_regions = set(list_available_regions())

    # Batch every referenced SKU per region before writing anything.
    wanted: dict[str, set[tuple[str, str]]] = {}
    for raw in entries:
        try:
            parsed = ArchitectureDefinition.model_validate(raw)
        except ValidationError:
            continue  # reported by `validate_definition` below
        for region, pairs in definition_sku_pairs(parsed).items():
            if region in available_regions:
                wanted.setdefault(region, set()).update(pairs)
    existing = {
        region: find_existing_skus(pairs, region=region) for region, pairs in sorted(wanted.items())
    }

    def existing_skus(region: str, pairs: set[tuple[str, str]]) -> set[tuple[str, str]]:
        return pairs & existing.get(region, set())

    results: list[ImportResult] = []
    for raw in entries:
        definition, error = validate_definition(
            raw,
            taken_names=taken_names,
            available_regions=available_regions,
            existing_skus=existing_skus,
        )
        if definition is None:
            results.append(ImportResult(name=entry_name(raw), status="failed", error=error))
            continue
        collections, connectors = specs_from_definition(definition)
        try:
            async with session.begin_nested():
                build_architecture(
                    session,
                    owner=owner,
                    name=definition.name,
                    provider=definition.provider,
                    collections=collections,
                    connectors=connectors,
                )
                await session.flush()
        except SQLAlchemyError:
            results.append(
                ImportResult(
                    name=definition.name, status="failed", error="Could not save architecture"
                )
            )
            continue
        taken_names.add(definition.name)
        results.append(ImportResult(name=definition.name, status="success", error=None))

    await session.commit()
    imported = sum(1 for r in results if r.status == "success")
    return ArchitectureFileImportResponse(
        imported_count=imported, failed_count=len(results) - imported, results=results
    )
