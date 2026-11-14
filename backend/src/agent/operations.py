"""The agent's operations (023-agent-foundation, research R9, contracts/agent-internals.md).

Each operation is a typed function over the app's existing services. It takes the current user
and the open architecture from the request (`OperationContext`), never from the model, so a
manipulated model can't reach beyond what the user could do (constitution Principle VII). In
this feature every operation is read-only (FR-003). The registry turns the decorated functions
into provider-neutral tool specs, one source of truth for what the model may call.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from src.agent.figures import FigureBook
from src.agent.model import ToolSpec


class ToolError(Exception):
    """An operation couldn't run; the message goes back to the model as the tool's result."""


def _no_progress(done: int, total: int, label: str) -> None:
    return None


@dataclass
class OperationContext:
    session: Any  # AsyncSession
    user: Any  # src.models.orm.User
    open_architecture_id: uuid.UUID | None
    figures: FigureBook
    # 024 (research R7, R8, R13): the message's match references, the session and user message
    # a result belongs to, the results made so far, and a progress callback for long operations.
    matches: Any = field(default_factory=lambda: _match_book())
    agent_session: Any = None  # src.models.orm.AgentSession
    message: Any = None  # the user message being answered (src.models.orm.AgentMessage)
    results: list = field(default_factory=list)
    progress: Callable[[int, int, str], None] = _no_progress


def _match_book():
    from src.agent.matching.book import MatchBook

    return MatchBook()


@dataclass
class OperationResult:
    data: dict  # sent to the model as JSON (data, never instructions: FR-008)
    summary: dict  # kept in the activity log
    snapshot: dict | None = None  # {provider: {date, revision}} behind any figure


OperationFn = Callable[[OperationContext, Any], Awaitable[OperationResult]]


@dataclass(frozen=True)
class Operation:
    name: str
    description: str
    input_model: type[BaseModel]
    fn: OperationFn

    def spec(self) -> ToolSpec:
        schema = self.input_model.model_json_schema()
        schema.pop("title", None)
        for prop in schema.get("properties", {}).values():
            prop.pop("title", None)
        schema.setdefault("properties", {})
        return ToolSpec(self.name, self.description, schema)


class Registry:
    def __init__(self) -> None:
        self._operations: dict[str, Operation] = {}

    def operation(self, name: str, description: str, input_model: type[BaseModel]):
        def register(fn: OperationFn) -> OperationFn:
            self._operations[name] = Operation(name, description, input_model, fn)
            return fn

        return register

    def tool_specs(self) -> list[ToolSpec]:
        return [op.spec() for op in self._operations.values()]

    def names(self) -> list[str]:
        return list(self._operations)

    async def run(self, ctx: OperationContext, name: str, arguments: dict) -> OperationResult:
        operation = self._operations.get(name)
        if operation is None:
            raise ToolError(f"unknown operation {name!r}")
        try:
            args = operation.input_model.model_validate(arguments or {})
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(map(str, e['loc'])) or 'input'}: {e['msg']}" for e in exc.errors()
            )
            raise ToolError(f"invalid arguments: {problems}") from exc
        return await operation.fn(ctx, args)


registry = Registry()


# --- The read-only operations (023: US1, US2) --------------------------------------------------

import asyncio  # noqa: E402
from collections import defaultdict  # noqa: E402
from decimal import Decimal  # noqa: E402
from typing import Literal  # noqa: E402

from fastapi import HTTPException  # noqa: E402
from pydantic import Field  # noqa: E402

Duration = Literal["1_day", "1_month", "1_year"]


class NoInput(BaseModel):
    pass


class PriceInput(BaseModel):
    duration: Duration = Field(
        default="1_month",
        description="1_day, 1_month (31 days) or 1_year (365 days). 'Per month' is 1_month.",
    )


class DriversInput(PriceInput):
    top: int = Field(default=5, ge=1, le=20, description="How many services to list.")


async def _open_architecture(ctx: OperationContext):
    from src.models.schemas import ArchitectureDetailOut
    from src.services.architecture_service import (
        attach_units_to_architecture,
        get_owned_architecture,
    )

    if ctx.open_architecture_id is None:
        raise ToolError("No architecture is open. Ask the user to open one from the Cloud "
                        "Pricing menu.")
    try:
        architecture = await get_owned_architecture(ctx.open_architecture_id, ctx.session,
                                                    ctx.user)
    except HTTPException as exc:
        raise ToolError("The open architecture isn't available to this user.") from exc
    detail = ArchitectureDetailOut.model_validate(architecture)
    attach_units_to_architecture(detail, architecture)
    return architecture, detail


def _service_label(selection) -> str:
    """A readable name: the provider's service name (or code), then the product family."""
    name = selection.service_name or selection.service_code
    if selection.product_family and selection.product_family not in name:
        return f"{name} ({selection.product_family})"
    return name


def _selection_labels(detail) -> dict[str, tuple[str, str]]:
    """sku_selection_id → (readable service name, where it is)."""
    labels: dict[str, tuple[str, str]] = {}
    names = {c.id: c.name for c in detail.collections}
    for collection in detail.collections:
        for selection in collection.sku_selections:
            labels[str(selection.id)] = (_service_label(selection), collection.name)
    for connector in detail.connectors:
        if connector.sku_selection is not None:
            where = (f"connector {names.get(connector.from_collection_id, '?')} → "
                     f"{names.get(connector.to_collection_id, '?')}")
            labels[str(connector.sku_selection.id)] = (
                _service_label(connector.sku_selection), where)
    return labels


async def _calculate(architecture, duration: str):
    from src.models.schemas import CalculationDuration
    from src.services.price_calculation import calculate_architecture_price

    return await asyncio.to_thread(
        calculate_architecture_price, architecture, duration=CalculationDuration(duration)
    )


def _is_empty(detail) -> bool:
    return not any(c.sku_selections for c in detail.collections) and not any(
        c.sku_selection for c in detail.connectors)


_EMPTY = {"empty": True, "message": "The open architecture has no services."}


@registry.operation(
    "describe_open_architecture",
    "What the open architecture contains: its collections (with type, region and nesting) and "
    "the services in each, as saved. Gives no prices.",
    NoInput,
)
async def describe_open_architecture(ctx: OperationContext, args: NoInput) -> OperationResult:
    _architecture, detail = await _open_architecture(ctx)
    names = {c.id: c.name for c in detail.collections}

    def service(s) -> dict:
        return {"service": _service_label(s), "service_code": s.service_code, "sku": s.sku,
                "quantity": str(s.usage_quantity), "unit": s.unit,
                "price_type": s.pricing_term.value}

    collections = [
        {"name": c.name, "type": c.type.value, "region": c.region,
         "inside": names.get(c.parent_collection_id),
         "services": [service(s) for s in c.sku_selections]}
        for c in detail.collections
    ]
    connectors = [
        {"from": names.get(c.from_collection_id), "to": names.get(c.to_collection_id),
         "service": service(c.sku_selection) if c.sku_selection else None}
        for c in detail.connectors
    ]
    count = sum(len(c["services"]) for c in collections) + sum(
        1 for c in connectors if c["service"])
    return OperationResult(
        data={"name": detail.name, "provider": detail.provider, "collections": collections,
              "connectors": connectors},
        summary={"architecture": detail.name, "collections": len(collections),
                 "services": count},
    )


def _snapshot(provider: str, result) -> dict:
    return {provider: {"date": str(result.snapshot_date),
                       "revision": int(result.snapshot_revision)}}


def _unpriceable(result, labels) -> list[dict]:
    return [
        {"service": labels.get(str(u.sku_selection_id), (u.service_code, ""))[0],
         "service_code": u.service_code, "sku": u.sku, "reason": u.reason,
         "where": list(u.components)}
        for u in result.unpriceable
    ]


@registry.operation(
    "price_open_architecture",
    "The open architecture's total cost for a duration, from the pricing engine, with any "
    "services that can't be priced and the pricing snapshot date. Amounts come back as "
    "references (e.g. F1) to write as [[F1]].",
    PriceInput,
)
async def price_open_architecture(ctx: OperationContext, args: PriceInput) -> OperationResult:
    architecture, detail = await _open_architecture(ctx)
    if _is_empty(detail):
        return OperationResult(data=dict(_EMPTY), summary={"empty": True})
    result = await _calculate(architecture, args.duration)
    snapshot = _snapshot(detail.provider, result)
    ref = ctx.figures.add(result.total_price, "total", duration=args.duration, snapshot=snapshot)
    unpriceable = _unpriceable(result, _selection_labels(detail))
    return OperationResult(
        data={"architecture": detail.name, "duration": args.duration, "total": ref,
              "currency": "USD", "unpriceable": unpriceable,
              "total_excludes_unpriceable": bool(unpriceable),
              "snapshot_date": snapshot[detail.provider]["date"],
              "snapshot_revision": snapshot[detail.provider]["revision"]},
        summary={"architecture": detail.name, "duration": args.duration,
                 "total": str(result.total_price), "unpriceable": len(unpriceable)},
        snapshot=snapshot,
    )


@registry.operation(
    "cost_drivers",
    "The services that cost the most in the open architecture for a duration, largest first, "
    "with the total and the rest combined. Amounts come back as references to write as [[Fn]].",
    DriversInput,
)
async def cost_drivers(ctx: OperationContext, args: DriversInput) -> OperationResult:
    architecture, detail = await _open_architecture(ctx)
    if _is_empty(detail):
        return OperationResult(data=dict(_EMPTY), summary={"empty": True})
    result = await _calculate(architecture, args.duration)
    snapshot = _snapshot(detail.provider, result)
    labels = _selection_labels(detail)
    by_selection: dict[str, Decimal] = defaultdict(Decimal)
    for item in result.line_items:
        if item.priceable and item.price is not None:
            by_selection[str(item.sku_selection_id)] += item.price
    ranked = sorted(by_selection.items(), key=lambda kv: kv[1], reverse=True)
    top, rest = ranked[: args.top], ranked[args.top:]

    def add(amount: Decimal, label: str) -> str:
        return ctx.figures.add(amount, label, duration=args.duration, snapshot=snapshot)

    drivers = [
        {"service": labels.get(sid, ("unknown service", ""))[0],
         "where": labels.get(sid, ("", ""))[1], "price": add(amount, "service")}
        for sid, amount in top
    ]
    unpriceable = _unpriceable(result, labels)
    return OperationResult(
        data={"duration": args.duration, "drivers": drivers,
              "all_other_services": add(sum((a for _, a in rest), Decimal(0)), "rest"),
              "other_service_count": len(rest),
              "total": add(result.total_price, "total"), "currency": "USD",
              "unpriceable": unpriceable, "total_excludes_unpriceable": bool(unpriceable),
              "snapshot_date": snapshot[detail.provider]["date"]},
        summary={"duration": args.duration, "listed": len(drivers),
                 "total": str(result.total_price)},
        snapshot=snapshot,
    )


class ImportableInput(BaseModel):
    provider: Literal["aws", "gcp", "azure"] | None = Field(
        default=None, description="Only this provider's architectures; omit for all.")


@registry.operation(
    "list_importable_architectures",
    "The public architectures this user can import, grouped by owner (Admin first), as the "
    "Import list in the Cloud Pricing menu shows them. Importing makes the user's own private "
    "copy; you can't import for them yet.",
    ImportableInput,
)
async def list_importable_architectures(ctx: OperationContext,
                                        args: ImportableInput) -> OperationResult:
    from src.models.orm import Architecture
    from src.services.importable import importable_architectures

    listing = await importable_architectures(ctx.session, ctx.user, args.provider)
    ids = [a.id for g in listing.groups for a in g.architectures]
    providers = {}
    if ids:
        from sqlalchemy import select

        rows = await ctx.session.execute(
            select(Architecture.id, Architecture.provider).where(Architecture.id.in_(ids)))
        providers = dict(rows.all())
    groups = [
        {"owner": g.owner_username,
         "architectures": [{"name": a.name, "provider": providers.get(a.id)}
                           for a in g.architectures]}
        for g in listing.groups
    ]
    return OperationResult(
        data={"provider": args.provider, "groups": groups,
              "how_to_import": "Import in the Cloud Pricing menu, under the provider."},
        summary={"provider": args.provider, "groups": len(groups),
                 "architectures": len(ids)},
    )


# 024: the comparison operations register themselves in the same registry.
from src.agent import operations_compare  # noqa: E402,F401
