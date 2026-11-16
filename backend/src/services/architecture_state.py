"""An architecture's saved content as one value (025, research R2, data-model §1).

`ArchitectureState` holds the architecture's name and provider and its live collections, services
and connectors, with their row ids. Three things are built on it:

- `fingerprint(state)`: a hash of the content, so any saved change (by the user, in any tab, or by
  an accepted proposal) is noticed without hooks in the edit routes (R3);
- `apply_state(...)`: makes the saved rows equal a state, keeping ids, so accept, undo and redo
  are one mechanism and undo restores the architecture exactly, browser layout included (R2);
- `to_transient(state)`: an unsaved ORM graph, so a proposed state is priced through
  `calculate_architecture_price` like any saved architecture (Principle I) without writing it.

`is_public`, the owner and browser layout aren't content (clarification Q3). Connector branches
(019, not drawn yet) are left as they are by `apply_state` and aren't part of the state.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.orm import Architecture, Collection, DataConnector, SKUSelection

QUANTUM = Decimal("0.0001")  # sku_selections.usage_quantity is Numeric(18, 4)


def quantity(value) -> Decimal:
    return Decimal(str(value)).quantize(QUANTUM)


class CollectionState(BaseModel):
    id: uuid.UUID
    type: str
    name: str
    region: str
    parent_id: uuid.UUID | None = None
    created_at: datetime


class ServiceState(BaseModel):
    id: uuid.UUID
    collection_id: uuid.UUID | None = None
    connector_id: uuid.UUID | None = None
    service_code: str
    sku: str
    pricing_term: str
    purchase_option: str
    usage_quantity: Decimal
    provider_options: dict | None = None
    created_at: datetime

    @field_serializer("usage_quantity")
    def _quantity(self, value: Decimal) -> str:
        return str(quantity(value))


class ConnectorState(BaseModel):
    id: uuid.UUID
    from_id: uuid.UUID
    to_id: uuid.UUID
    arrow_style: str = "none"
    arrow_reversed: bool = False
    created_at: datetime


class ArchitectureState(BaseModel):
    name: str
    provider: str
    collections: list[CollectionState] = Field(default_factory=list)
    services: list[ServiceState] = Field(default_factory=list)
    connectors: list[ConnectorState] = Field(default_factory=list)

    def canonical(self) -> dict:
        data = self.model_dump(mode="json")
        for key in ("collections", "services", "connectors"):
            data[key] = sorted(data[key], key=lambda row: row["id"])
        return data

    def collection(self, collection_id: uuid.UUID) -> CollectionState | None:
        return next((c for c in self.collections if c.id == collection_id), None)

    def connector(self, connector_id: uuid.UUID) -> ConnectorState | None:
        return next((c for c in self.connectors if c.id == connector_id), None)

    def service(self, service_id: uuid.UUID) -> ServiceState | None:
        return next((s for s in self.services if s.id == service_id), None)

    def service_region(self, service: ServiceState) -> str | None:
        """A service is priced in its collection's region, or its connector's "from" one."""
        if service.collection_id is not None:
            owner = self.collection(service.collection_id)
            return owner.region if owner else None
        connector = self.connector(service.connector_id) if service.connector_id else None
        owner = self.collection(connector.from_id) if connector else None
        return owner.region if owner else None


def fingerprint(state: ArchitectureState) -> str:
    text = json.dumps(state.canonical(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def _service_state(selection: SKUSelection) -> ServiceState:
    return ServiceState(
        id=selection.id, collection_id=selection.collection_id,
        connector_id=selection.connector_id, service_code=selection.service_code,
        sku=selection.sku, pricing_term=selection.pricing_term,
        purchase_option=selection.purchase_option,
        usage_quantity=quantity(selection.usage_quantity),
        provider_options=selection.provider_options, created_at=selection.created_at,
    )


def state_of(architecture: Architecture) -> ArchitectureState:
    """The state of an architecture whose collections (with services) and connectors (with their
    service) are loaded. Deleted collections and connectors, and their services, are skipped."""
    collections = [c for c in architecture.collections if c.deleted_at is None]
    connectors = [c for c in architecture.connectors if c.deleted_at is None]
    live = {c.id for c in collections}
    return ArchitectureState(
        name=architecture.name,
        provider=architecture.provider,
        collections=[
            CollectionState(id=c.id, type=c.type, name=c.name, region=c.region,
                            parent_id=c.parent_collection_id, created_at=c.created_at)
            for c in collections
        ],
        services=[_service_state(s) for c in collections for s in c.sku_selections]
        + [_service_state(c.sku_selection) for c in connectors if c.sku_selection is not None],
        connectors=[
            ConnectorState(id=c.id, from_id=c.from_collection_id, to_id=c.to_collection_id,
                           arrow_style=c.arrow_style, arrow_reversed=c.arrow_reversed,
                           created_at=c.created_at)
            for c in connectors if c.from_collection_id in live and c.to_collection_id in live
        ],
    )


async def load_architecture(session: AsyncSession, architecture_id: uuid.UUID,
                            *, include_deleted: bool = False) -> Architecture | None:
    """The architecture with its live collections, services and connectors, read afresh."""
    stmt = (
        select(Architecture)
        .where(Architecture.id == architecture_id)
        .options(
            selectinload(Architecture.collections.and_(Collection.deleted_at.is_(None)))
            .selectinload(Collection.sku_selections),
            selectinload(Architecture.connectors.and_(DataConnector.deleted_at.is_(None)))
            .selectinload(DataConnector.sku_selection),
        )
        .execution_options(populate_existing=True)
    )
    if not include_deleted:
        stmt = stmt.where(Architecture.deleted_at.is_(None))
    return (await session.execute(stmt)).scalar_one_or_none()


async def read_state(session: AsyncSession, architecture_id: uuid.UUID) -> ArchitectureState | None:
    architecture = await load_architecture(session, architecture_id)
    return None if architecture is None else state_of(architecture)


async def apply_state(session: AsyncSession, architecture_id: uuid.UUID,
                      target: ArchitectureState) -> None:
    """Make the saved architecture equal `target`, keeping row ids and `created_at`.

    Rows in `target` are updated, revived (a soft-deleted collection or connector) or inserted
    with their ids; live collections and connectors not in `target` are soft deleted, as the edit
    routes do; services not in `target` are deleted. Nothing is committed: the caller commits, so
    a failure leaves nothing applied."""
    architecture = await session.get(Architecture, architecture_id)
    architecture.name = target.name
    now = datetime.now(UTC).replace(tzinfo=None)

    # Collections: insert or update without parents first (a parent may be new too), then parents.
    wanted = {c.id: c for c in target.collections}
    rows = {
        c.id: c for c in (await session.execute(
            select(Collection).where(Collection.architecture_id == architecture_id)
        )).scalars()
    }
    for row in rows.values():
        if row.id not in wanted and row.deleted_at is None:
            row.deleted_at = now
            row.parent_collection_id = None
    for spec in target.collections:
        row = rows.get(spec.id)
        if row is None:
            row = Collection(id=spec.id, architecture_id=architecture_id, type=spec.type,
                             name=spec.name, region=spec.region, created_at=spec.created_at)
            session.add(row)
            rows[spec.id] = row
        row.type, row.name, row.region = spec.type, spec.name, spec.region
        row.deleted_at = None
        row.parent_collection_id = None
    await session.flush()
    for spec in target.collections:
        rows[spec.id].parent_collection_id = spec.parent_id
    await session.flush()

    # Connectors.
    wanted_connectors = {c.id: c for c in target.connectors}
    connector_rows = {
        c.id: c for c in (await session.execute(
            select(DataConnector).where(DataConnector.architecture_id == architecture_id)
        )).scalars()
    }
    for row in connector_rows.values():
        if row.id not in wanted_connectors and row.deleted_at is None:
            row.deleted_at = now
    for spec in target.connectors:
        row = connector_rows.get(spec.id)
        if row is None:
            row = DataConnector(id=spec.id, architecture_id=architecture_id,
                                from_collection_id=spec.from_id, to_collection_id=spec.to_id,
                                created_at=spec.created_at)
            session.add(row)
        row.from_collection_id, row.to_collection_id = spec.from_id, spec.to_id
        row.arrow_style, row.arrow_reversed = spec.arrow_style, spec.arrow_reversed
        row.deleted_at = None
    await session.flush()

    # Services: delete the ones the target drops first (a connector holds at most one), then
    # update or insert the target's.
    wanted_services = {s.id: s for s in target.services}
    owners = or_(
        SKUSelection.collection_id.in_(list(rows)),
        SKUSelection.connector_id.in_(list(connector_rows) + list(wanted_connectors)),
        SKUSelection.id.in_(list(wanted_services)),
    )
    service_rows = {s.id: s for s in (await session.execute(select(SKUSelection).where(owners))
                                      ).scalars()}
    live_owners = set(wanted) | set(wanted_connectors)
    dropped = [
        sid for sid, row in service_rows.items()
        if sid not in wanted_services and (row.collection_id in live_owners
                                           or row.connector_id in live_owners)
    ]
    if dropped:
        await session.execute(delete(SKUSelection).where(SKUSelection.id.in_(dropped)))
        for sid in dropped:
            service_rows.pop(sid)
    for spec in target.services:
        row = service_rows.get(spec.id)
        if row is None:
            row = SKUSelection(id=spec.id, created_at=spec.created_at)
            session.add(row)
        row.collection_id, row.connector_id = spec.collection_id, spec.connector_id
        row.service_code, row.sku = spec.service_code, spec.sku
        row.pricing_term, row.purchase_option = spec.pricing_term, spec.purchase_option
        row.usage_quantity = quantity(spec.usage_quantity)
        row.provider_options = spec.provider_options
    await session.flush()


def to_transient(state: ArchitectureState) -> Architecture:
    """An unsaved ORM graph of `state` (never added to a session), for pricing."""
    architecture = Architecture(id=uuid.uuid4(), name=state.name, provider=state.provider)
    collections: dict[uuid.UUID, Collection] = {}
    for spec in state.collections:
        collection = Collection(id=spec.id, type=spec.type, name=spec.name, region=spec.region,
                                parent_collection_id=spec.parent_id)
        collection.sku_selections = []
        collections[spec.id] = collection
    connectors: dict[uuid.UUID, DataConnector] = {}
    for spec in state.connectors:
        connector = DataConnector(id=spec.id, from_collection_id=spec.from_id,
                                  to_collection_id=spec.to_id, arrow_style=spec.arrow_style,
                                  arrow_reversed=spec.arrow_reversed)
        connector.sku_selection = None
        connectors[spec.id] = connector
    for spec in state.services:
        selection = SKUSelection(
            id=spec.id, collection_id=spec.collection_id, connector_id=spec.connector_id,
            service_code=spec.service_code, sku=spec.sku, pricing_term=spec.pricing_term,
            purchase_option=spec.purchase_option, usage_quantity=quantity(spec.usage_quantity),
            provider_options=spec.provider_options,
        )
        if spec.collection_id in collections:
            collections[spec.collection_id].sku_selections.append(selection)
        elif spec.connector_id in connectors:
            connectors[spec.connector_id].sku_selection = selection
    architecture.collections = list(collections.values())
    architecture.connectors = list(connectors.values())
    return architecture
