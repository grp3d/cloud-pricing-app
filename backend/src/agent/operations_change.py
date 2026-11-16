"""The change operations (025, contracts/agent-operations.md): the agent proposes, the user
decides.

None of these saves an architecture: `propose_*` builds a proposal (change items over a state,
validated with the edit routes' rules and priced by the engine) that only the user's Accept saves
(FR-003, Principle VII). The model works with references only: `C…` products from this message's
searches, `A…`/`V…`/`K…` rows of the open architecture, `P…` items of the pending proposal, `M…`
and `I…` architectures. It never sends an id or a SKU (FR-002).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.agent import compare, proposals
from src.agent.matching.book import Candidate
from src.agent.matching.candidates import _Searcher
from src.agent.matching.profiles import FUNCTION_CATEGORY
from src.agent.operations import OperationContext, OperationResult, ToolError, registry
from src.agent.operations_compare import (
    Category,
    Duration,
    Provider,
    PurchaseOption,
    Size,
    Term,
    Usage,
    _available,
    _candidate_out,
    _usage_for,
    search_region,
)
from src.agent.proposals import Draft, ServiceSpec
from src.services import architecture_rules as rules
from src.services.architecture_state import ArchitectureState

Function = Literal[tuple(FUNCTION_CATEGORY)]  # type: ignore[valid-type]
CollectionType = Literal["vpc", "application"]
Arrow = Literal["none", "one_way", "two_way"]
_TYPES = {"vpc": "vpc", "application": "application_component"}
TOP_DRIVERS = 5


# --- find_products ---------------------------------------------------------------------------------


class ProductPart(BaseModel):
    part: str = Field(max_length=40, description="Your name for this part, e.g. 'web', 'db'.")
    category: Category
    function: Function | None = Field(  # type: ignore[valid-type]
        default=None, description="Narrow to one kind of product, e.g. vm, managed_db.")
    text: str | None = Field(default=None, max_length=100,
                             description="Search words, e.g. 'e2-standard' or 'postgres'.")


class FindProductsInput(BaseModel):
    provider: Provider
    region: str = Field(max_length=40)
    parts: list[ProductPart] = Field(min_length=1, max_length=8)


@registry.operation(
    "find_products",
    "Find catalog products for several parts of an architecture in one provider and region "
    "(up to 8 parts, up to 5 products each), in one call. Returns C… references to use in "
    "propose_new_architecture or propose_changes. A part with no product says so: leave it out "
    "and tell the user; never invent one.",
    FindProductsInput,
)
async def find_products(ctx: OperationContext, args: FindProductsInput) -> OperationResult:
    if args.region not in _available(args.provider):
        raise ToolError(f"{args.provider} has no pricing data for {args.region}; use "
                        "list_regions")
    searcher = _Searcher()
    data: dict = {"provider": args.provider, "region": args.region, "parts": {}}
    found = 0
    for part in args.parts:
        if part.function and FUNCTION_CATEGORY[part.function] != part.category:
            raise ToolError(f"{part.part}: {part.function} is in "
                            f"{FUNCTION_CATEGORY[part.function]}, not {part.category}")
        functions = ([part.function] if part.function else
                     [f for f, c in FUNCTION_CATEGORY.items() if c == part.category])
        kept = await search_region(searcher, args.provider, args.region, functions, part.text)
        for candidate in kept:
            ctx.matches.add_candidate(candidate)
        found += len(kept)
        if kept:
            data["parts"][part.part] = {
                "products": [_candidate_out(c, with_quality=False) for c in kept]}
        elif part.text and await search_region(searcher, args.provider, args.region,
                                               functions, None):
            data["parts"][part.part] = {
                "none": f"no product of that kind matches {part.text!r} here; search again "
                        "with a word from the product names, or no words"}
        else:
            data["parts"][part.part] = {
                "none": "the catalog has no product of that kind in this region"}
    return OperationResult(data=data, summary={"provider": args.provider,
                                               "region": args.region, "parts": len(args.parts),
                                               "candidates": found})


# --- Building blocks ------------------------------------------------------------------------------


class ServiceInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    in_: str = Field(alias="in", description="The collection: an A… reference or a new… ref "
                     "from this call.")
    product: str = Field(description="A C… reference from this message.")
    usage: Usage | Literal["default"] | None = Field(
        default=None, description="How much: a quantity and unit, or 'default' for the app's "
        "default (say which). Leave out for a find_region_equivalents product to keep the "
        "original's usage.")
    size: Size | None = Field(default=None, description="vCPU and memory, for GCP machines.")
    term: Term | None = Field(default=None, description="On demand unless set; a "
                              "find_region_equivalents product keeps the original's term.")
    purchase_option: PurchaseOption | None = None
    group: str | None = Field(default=None, max_length=60, description="Which part of the "
                              "request this belongs to, e.g. 'web tier', 'standby'.")


class CollectionInput(BaseModel):
    ref: str = Field(pattern=r"^new\d+$", description="new1, new2, … for use in this call.")
    type: CollectionType
    name: str = Field(min_length=1, max_length=255)
    region: str = Field(max_length=40)
    parent: str | None = Field(default=None, description="A VPC's new… ref or A… reference, for "
                               "an application inside it (same region).")
    group: str | None = Field(default=None, max_length=60)


class ConnectorInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    arrow: Arrow = "none"
    product: str | None = Field(default=None, description="A C… data-transfer product.")
    usage: Usage | Literal["default"] | None = None
    term: Term = "on_demand"
    group: str | None = Field(default=None, max_length=60)


class AssumptionInput(BaseModel):
    kind: Literal["region", "term", "size", "usage", "default"]
    text: str = Field(max_length=300)
    guessed: bool = False


def service_spec(candidate: Candidate, *, usage, size, term: str | None,
                 purchase_option: str | None, ref: str) -> ServiceSpec:
    """A service from a catalog reference, with its engine quantity (024's conversions)."""
    if usage is None and candidate.quantity is not None:
        quantity, options, why = candidate.quantity, candidate.options, None
    else:
        converted, why, _label = _usage_for(candidate, usage or "default", candidate, size)
        quantity = converted.quantity if converted else None
        options = converted.options if converted else None
    if why or quantity is None:
        raise ToolError(f"{ref}: {why or 'say how much to price (usage)'}")
    if term is None and candidate.keep_term is not None:
        pricing_term, option = candidate.keep_term
    else:
        pricing_term, option = compare.term_option(candidate.provider, term or "on_demand",
                                                   purchase_option)
    return ServiceSpec(candidate.service_code, candidate.sku, pricing_term, option,
                       Decimal(quantity), options, candidate.label)


def resolve_owner(ref: str, draft: Draft, ctx: OperationContext):
    """A collection reference (`new…` from this call, or an `A…`) → its id."""
    if ref in draft.new_refs:
        return draft.new_refs[ref]
    row = ctx.rows.get(ref)
    if row is None or row[0] != "collection":
        raise ToolError(f"unknown collection {ref!r}: use an A… reference or a new… ref made "
                        "earlier in this call")
    return row[1]


def _where(draft: Draft, collection_id) -> str:
    collection = draft.state.collection(collection_id)
    return collection.name if collection else "?"


def add_service(draft: Draft, ctx: OperationContext, service: ServiceInput, index: int) -> None:
    owner = resolve_owner(service.in_, draft, ctx)
    candidate = ctx.matches.candidate(service.product)
    collection = draft.state.collection(owner)
    if collection is not None and candidate.region != collection.region:
        raise ToolError(f"service {index}: {service.product} is in {candidate.region}, but "
                        f"{collection.name} is in {collection.region}; search that region")
    spec = service_spec(candidate, usage=service.usage, size=service.size, term=service.term,
                        purchase_option=service.purchase_option, ref=f"service {index}")
    draft.add_service(spec, collection_id=owner, group=service.group,
                      where=_where(draft, owner))


def add_connector(draft: Draft, ctx: OperationContext, connector: ConnectorInput,
                  index: int) -> None:
    from_id = resolve_owner(connector.from_, draft, ctx)
    to_id = resolve_owner(connector.to, draft, ctx)
    label = f"Connector {_where(draft, from_id)} → {_where(draft, to_id)}"
    connector_id = draft.add_connector(from_id, to_id, arrow_style=connector.arrow,
                                       group=connector.group, label=label)
    if connector.product:
        candidate = ctx.matches.candidate(connector.product)
        source = draft.state.collection(from_id)
        if source is not None and candidate.region != source.region:
            raise ToolError(f"connector {index}: a connector's service is priced in its 'from' "
                            f"collection's region ({source.region}), but {connector.product} is "
                            f"in {candidate.region}")
        spec = service_spec(candidate, usage=connector.usage, size=None, term=connector.term,
                            purchase_option=None, ref=f"connector {index}")
        draft.add_service(spec, connector_id=connector_id, group=connector.group,
                          where=label.removeprefix("Connector "))


def cost_for_model(ctx: OperationContext, cost: dict) -> dict:
    """The proposal's figures as references (FR-004): totals, the difference, the biggest
    drivers, the contributions and what couldn't be priced."""
    duration = cost["duration"]
    snapshot = {cost["snapshot"]["provider"]: {k: v for k, v in cost["snapshot"].items()
                                               if k != "provider"}}

    def ref(amount, label, kind="money"):
        return ctx.figures.add(Decimal(amount), label, duration=duration, snapshot=snapshot,
                               kind=kind)

    out: dict = {"after": ref(cost["after"]["total"], "total after"),
                 "partial": cost["after"]["partial"], "duration": duration,
                 "snapshot_date": cost["snapshot"]["date"]}
    if cost.get("before"):
        out["before"] = ref(cost["before"]["total"], "total before")
        out["difference"] = ref(cost["difference"], "difference")
        if cost.get("percent") is not None:
            out["percent"] = ref(cost["percent"], "difference %", "percent")
        rows = [r for r in cost["by_service"] if r["difference"] not in (None, "0")
                and Decimal(r["difference"]) != 0]
        rows.sort(key=lambda r: abs(Decimal(r["difference"])), reverse=True)
        out["drivers"] = [{"service": r["label"], "difference": ref(r["difference"], r["label"])}
                          for r in rows[:TOP_DRIVERS]]
    else:
        rows = [r for r in cost["by_service"] if r["after"] is not None]
        rows.sort(key=lambda r: Decimal(r["after"]), reverse=True)
        out["drivers"] = [{"service": r["label"], "cost": ref(r["after"], r["label"])}
                          for r in rows[:TOP_DRIVERS]]
    if cost.get("contributions"):
        out["contributions"] = [{"group": c["group"], "difference": ref(c["difference"],
                                                                        c["group"])}
                                for c in cost["contributions"]]
    if cost.get("unpriceable"):
        out["not_priced"] = [f"{u['label']} ({u['reason']})" for u in cost["unpriceable"]]
    return out


async def finish(ctx: OperationContext, draft: Draft, *, kind: str, title: str,
                 base: ArchitectureState | None, duration: str, assumptions: list,
                 architecture_id=None, source_architecture_id=None) -> OperationResult:
    """Validate, price and save the proposal (pending), and tell the model what it holds."""
    target = draft.state
    try:
        proposals.validate(base, target, draft.items)
    except rules.RuleError as error:
        where = f"{error.ref}: " if error.ref else ""
        raise ToolError(f"{where}{error.message}") from error
    cost = proposals.cost_summary(base, draft.items, target, duration)
    proposal = await proposals.create_proposal(
        ctx.session, ctx.agent_session, ctx.message, kind=kind, title=title, base=base,
        target=target, items=draft.items, cost=cost,
        assumptions=[a.model_dump() for a in assumptions], architecture_id=architecture_id,
        source_architecture_id=source_architecture_id)
    ctx.proposals.append(proposal)
    data = {
        "proposal": f"Q{proposal.seq}",
        "status": "pending: shown to the user beside you; nothing is saved until they accept",
        "items": [{"ref": i.ref, "op": i.op, "label": i.label, **({"group": i.group}
                                                                  if i.group else {})}
                  for i in draft.items],
        "cost": cost_for_model(ctx, cost),
    }
    summary = {"proposal": str(proposal.id), "kind": kind, "items": len(draft.items),
               "skus": sorted({f"{s['after']['service_code']}:{s['after']['sku']}"
                               for s in (i.to_json() for i in draft.items)
                               if s["target"] == "service" and s["op"] == "add"})}
    return OperationResult(data=data, summary=summary,
                           snapshot={cost["snapshot"]["provider"]: {
                               k: v for k, v in cost["snapshot"].items() if k != "provider"}})


# --- propose_new_architecture -----------------------------------------------------------------------


class NewArchitectureInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    provider: Provider
    duration: Duration = "1_month"
    collections: list[CollectionInput] = Field(min_length=1, max_length=50)
    services: list[ServiceInput] = Field(default_factory=list, max_length=100)
    connectors: list[ConnectorInput] = Field(default_factory=list, max_length=50)
    assumptions: list[AssumptionInput] = Field(default_factory=list, max_length=20)


@registry.operation(
    "propose_new_architecture",
    "Propose a new architecture: collections (VPCs and applications), services from C… "
    "products, and connectors. The app validates it like a manual edit and prices it; the user "
    "sees it beside you and decides. Nothing is saved until they accept. State your "
    "assumptions in `assumptions`.",
    NewArchitectureInput,
)
async def propose_new_architecture(ctx: OperationContext,
                                   args: NewArchitectureInput) -> OperationResult:
    empty = ArchitectureState(name=args.name, provider=args.provider)
    draft = Draft(empty, await proposals.db_clock(ctx.session))
    for collection in args.collections:
        parent = resolve_owner(collection.parent, draft, ctx) if collection.parent else None
        draft.add_collection(collection.ref, type=_TYPES[collection.type], name=collection.name,
                             region=collection.region, parent_id=parent,
                             group=collection.group)
    for index, service in enumerate(args.services, start=1):
        add_service(draft, ctx, service, index)
    for index, connector in enumerate(args.connectors, start=1):
        add_connector(draft, ctx, connector, index)
    return await finish(ctx, draft, kind="create", title=args.name, base=None,
                        duration=args.duration, assumptions=args.assumptions)


# --- list_my_architectures / open_architecture (FR-017, research R7) -------------------------------


class NoArgs(BaseModel):
    pass


@registry.operation(
    "list_my_architectures",
    "The user's own architectures (name, provider, regions, how many services), each with an "
    "M… reference for open_architecture. Use it to find one the user names.",
    NoArgs,
)
async def list_my_architectures(ctx: OperationContext, args: NoArgs) -> OperationResult:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from src.models.orm import Architecture, Collection

    rows = (await ctx.session.execute(
        select(Architecture).where(Architecture.user_id == ctx.user.id,
                                   Architecture.deleted_at.is_(None))
        .options(selectinload(Architecture.collections.and_(Collection.deleted_at.is_(None)))
                 .selectinload(Collection.sku_selections))
        .order_by(Architecture.name, Architecture.created_at)
    )).scalars().all()
    out = []
    for index, architecture in enumerate(rows, start=1):
        ref = f"M{index}"
        ctx.rows[ref] = ("architecture", architecture.id)
        out.append({"ref": ref, "name": architecture.name, "provider": architecture.provider,
                    "regions": sorted({c.region for c in architecture.collections}),
                    "services": sum(len(c.sku_selections) for c in architecture.collections),
                    "is_open": architecture.id == ctx.open_architecture_id})
    return OperationResult(data={"architectures": out}, summary={"architectures": len(out)})


class OpenInput(BaseModel):
    architecture: str = Field(description="An M… reference from list_my_architectures.")


@registry.operation(
    "open_architecture",
    "Open one of the user's architectures in the app (say you're opening it). Returns what it "
    "contains, with A…/V…/K… references for propose_changes.",
    OpenInput,
)
async def open_architecture(ctx: OperationContext, args: OpenInput) -> OperationResult:
    from src.agent.operations import _open_architecture, describe_detail

    row = ctx.rows.get(args.architecture)
    if row is None or row[0] != "architecture":
        raise ToolError(f"unknown architecture {args.architecture!r}: use an M… reference from "
                        "list_my_architectures")
    previous = ctx.open_architecture_id
    ctx.open_architecture_id = row[1]
    try:
        _architecture, detail = await _open_architecture(ctx)
    except ToolError:
        ctx.open_architecture_id = previous
        raise
    for ref in [r for r, (kind, _id) in ctx.rows.items() if kind != "architecture"]:
        ctx.rows.pop(ref)
    ctx.opened.append((detail.id, detail.name))
    described = describe_detail(ctx, detail)
    return OperationResult(data={"opened": detail.name, **described.data},
                           summary={"opened": detail.name, **described.summary})


# --- find_region_equivalents (US2: replication) ----------------------------------------------------


class RegionEquivalentsInput(BaseModel):
    services: list[str] = Field(min_length=1, max_length=50, description="V… references.")
    region: str = Field(max_length=40, description="The region to replicate to.")


async def _sources_by_id(detail) -> dict:
    """The open architecture's services as 024 sources (with product profiles), by row id."""
    ids = [s.id for c in detail.collections for s in c.sku_selections] + [
        c.sku_selection.id for c in detail.connectors if c.sku_selection is not None]
    return dict(zip(ids, await compare.architecture_sources(detail), strict=True))


@registry.operation(
    "find_region_equivalents",
    "For services of the open architecture (V… references), the same product in another region "
    "of the same provider, with its match quality, as C… references that keep the original's "
    "usage. 'none' means the catalog has no equivalent there: say so and leave it out.",
    RegionEquivalentsInput,
)
async def find_region_equivalents(ctx: OperationContext,
                                  args: RegionEquivalentsInput) -> OperationResult:
    from src.agent.matching.quality import quality
    from src.agent.operations import _open_architecture

    _architecture, detail = await _open_architecture(ctx)
    if args.region not in _available(detail.provider):
        raise ToolError(f"{detail.provider} has no pricing data for {args.region}; use "
                        "list_regions")
    sources = await _sources_by_id(detail)
    searcher = _Searcher()
    data: dict = {"region": args.region, "services": {}}
    found = 0
    for ref in args.services:
        row = ctx.rows.get(ref)
        if row is None or row[0] != "service":
            raise ToolError(f"unknown service {ref!r}: use a V… reference from "
                            "describe_open_architecture")
        source = sources[row[1]]
        if source.region == args.region:
            raise ToolError(f"{ref} is already in {args.region}; choose another region")
        reference = Candidate(source_ref=None, provider=source.provider, region=source.region,
                              service_code=source.service_code, sku=source.sku,
                              label=source.label, profile=source.profile)
        kept = await search_region(searcher, source.provider, args.region,
                                   [source.profile.function], None, reference)
        best = next((c for c in kept if c.quality in ("exact", "close")), None)
        if best is None:
            data["services"][ref] = {"service": source.label,
                                     "none": f"no equivalent product in {args.region}"}
            continue
        best.quality, best.differences = quality(source.profile, best.profile)
        best.quantity = source.usage_quantity
        options = source.provider_options
        if options and options.get("kind") == "gcp_machine" and best.ram_sku:
            options = {**options, "ram_sku": best.ram_sku}
        best.options = options
        best.keep_term = (source.pricing_term, source.purchase_option)
        ctx.matches.add_candidate(best)
        found += 1
        data["services"][ref] = {"service": source.label, "term": source.pricing_term,
                                 **_candidate_out(best)}
    return OperationResult(data=data, summary={"region": args.region,
                                               "services": len(args.services),
                                               "found": found})


# --- propose_changes (US2, US6–US8) -----------------------------------------------------------------


class ServiceChangeInput(BaseModel):
    ref: str = Field(description="A V… service reference.")
    usage: Usage | None = Field(default=None, description="The new amount.")
    scale: Decimal | None = Field(default=None, gt=0, description="Multiply the current amount, "
                                  "e.g. 0.5 for half, 2 for double.")
    product: str | None = Field(default=None, description="A C… product to resize to (same "
                                "region).")
    size: Size | None = None
    term: Term | None = None
    purchase_option: PurchaseOption | None = None
    group: str | None = Field(default=None, max_length=60)


class RenameInput(BaseModel):
    ref: str = Field(description="An A… collection reference.")
    name: str = Field(min_length=1, max_length=255)
    group: str | None = Field(default=None, max_length=60)


class RemoveInput(BaseModel):
    ref: str = Field(description="An A…, V… or K… reference.")
    group: str | None = Field(default=None, max_length=60)


class ChangesInput(BaseModel):
    title: str = Field(min_length=1, max_length=200, description="A short title, e.g. "
                       "'Replicate Prod Web to us-west-2'.")
    duration: Duration = "1_month"
    add_collections: list[CollectionInput] = Field(default_factory=list, max_length=50)
    add_services: list[ServiceInput] = Field(default_factory=list, max_length=100)
    add_connectors: list[ConnectorInput] = Field(default_factory=list, max_length=50)
    change_services: list[ServiceChangeInput] = Field(default_factory=list, max_length=100)
    rename_collections: list[RenameInput] = Field(default_factory=list, max_length=50)
    remove: list[RemoveInput] = Field(default_factory=list, max_length=100)
    rename_architecture: str | None = Field(default=None, min_length=1, max_length=255)
    revise_pending: bool = Field(default=False, description="Start from the pending proposal's "
                                 "items (a refinement); change or remove them by P… reference.")
    assumptions: list[AssumptionInput] = Field(default_factory=list, max_length=20)


def _row(ctx: OperationContext, ref: str, kinds: tuple[str, ...]):
    row = ctx.rows.get(ref)
    if row is None or row[0] not in kinds:
        raise ToolError(f"unknown reference {ref!r}: use one from describe_open_architecture "
                        "in this message")
    return row


@registry.operation(
    "propose_changes",
    "Propose changes to the open architecture: add collections, services and connectors; "
    "change a service's amount, size, product or term; rename; remove. Uses A…/V…/K… "
    "references from describe_open_architecture (or open_architecture) and C… products. The "
    "app validates it like a manual edit and prices before and after; the user sees it beside "
    "you and decides. It replaces any pending proposal. Nothing is saved until they accept.",
    ChangesInput,
)
async def propose_changes(ctx: OperationContext, args: ChangesInput) -> OperationResult:
    from src.agent.matching.usage import stated_quantity
    from src.agent.operations import _open_architecture
    from src.services.architecture_state import read_state

    architecture, detail = await _open_architecture(ctx)
    base = await read_state(ctx.session, architecture.id)
    draft = Draft(base, await proposals.db_clock(ctx.session))
    if args.revise_pending:
        await _replay_pending(ctx, draft, architecture.id)
    for collection in args.add_collections:
        parent = resolve_owner(collection.parent, draft, ctx) if collection.parent else None
        draft.add_collection(collection.ref, type=_TYPES[collection.type], name=collection.name,
                             region=collection.region, parent_id=parent, group=collection.group)
    for index, service in enumerate(args.add_services, start=1):
        add_service(draft, ctx, service, index)
    for index, connector in enumerate(args.add_connectors, start=1):
        add_connector(draft, ctx, connector, index)
    sources = await _sources_by_id(detail) if args.change_services else {}
    for change in args.change_services:
        _kind, service_id = _row(ctx, change.ref, ("service",))
        current = draft.state.service(service_id)
        if current is None:
            raise ToolError(f"{change.ref} isn't in the architecture or the pending proposal")
        source = sources.get(service_id)  # None for a service the pending proposal adds
        region = draft.state.service_region(current)
        label = (f"{source.label} in {source.where}" if source else
                 next((i.label for i in draft.items if i.id == str(service_id)), change.ref))
        fields: dict = {}
        if change.product:
            candidate = ctx.matches.candidate(change.product)
            if candidate.region != region:
                raise ToolError(f"{change.ref}: {change.product} is in {candidate.region}, not "
                                f"{region}")
            fields.update(service_code=candidate.service_code, sku=candidate.sku)
            if change.size or candidate.options:
                spec = service_spec(candidate, usage=change.usage or "default",
                                    size=change.size, term=current.pricing_term,
                                    purchase_option=None, ref=change.ref)
                fields["provider_options"] = spec.provider_options
        if change.usage is not None:
            if source is None:
                raise ToolError(f"{change.ref} is added by the pending proposal: use scale "
                                "(for example 0.5 for half) to change its amount")
            stated = stated_quantity(source.profile.unit_kind, change.usage.quantity,
                                     change.usage.unit)
            if not hasattr(stated, "quantity"):
                raise ToolError(f"{change.ref}: {stated.reason}")
            fields["usage_quantity"] = str(Decimal(stated.quantity))
        elif change.scale is not None:
            fields["usage_quantity"] = str(Decimal(current.usage_quantity) * change.scale)
        if change.term is not None or change.purchase_option is not None:
            term, option = compare.term_option(
                architecture.provider, change.term or current.pricing_term,
                change.purchase_option)
            fields.update(pricing_term=term, purchase_option=option)
        if not fields:
            raise ToolError(f"{change.ref}: say what to change (usage, scale, product, size or "
                            "term)")
        from src.services.architecture_state import quantity as q

        if "usage_quantity" in fields:
            fields["usage_quantity"] = str(q(fields["usage_quantity"]))
        draft.change("service", service_id, fields, label=label, group=change.group)
    for rename in args.rename_collections:
        _kind, collection_id = _row(ctx, rename.ref, ("collection",))
        draft.change("collection", collection_id, {"name": rename.name},
                     label=f"Rename to {rename.name}", group=rename.group)
    for removal in args.remove:
        kind, row_id = _row(ctx, removal.ref, ("collection", "service", "connector"))
        if _drop_added(draft, row_id):
            continue  # an addition of the pending proposal, taken back
        label = removal.ref
        if kind == "service":
            label = f"{sources.get(row_id).label}" if row_id in sources else removal.ref
            label = _service_name(draft, row_id, label)
        elif kind == "collection":
            found = draft.state.collection(row_id)
            label = found.name if found else removal.ref
        else:
            found = draft.state.connector(row_id)
            label = (f"Connector {_where(draft, found.from_id)} → {_where(draft, found.to_id)}"
                     if found else removal.ref)
        draft.remove(kind, row_id, label=label, group=removal.group)
    if args.rename_architecture:
        draft.rename(args.rename_architecture, group=None)
    if not draft.items:
        raise ToolError("the proposal has no changes")
    return await finish(ctx, draft, kind="change", title=args.title, base=base,
                        duration=args.duration, assumptions=args.assumptions,
                        architecture_id=architecture.id)


def _service_name(draft: Draft, service_id, fallback: str) -> str:
    service = draft.state.service(service_id)
    if service is None:
        return fallback
    where = _where(draft, service.collection_id) if service.collection_id else "a connector"
    return f"{service.service_code} in {where}" if fallback.startswith("V") else (
        f"{fallback} in {where}")


# --- propose_import (US5, FR-009, FR-012) ------------------------------------------------------------


class ImportInput(BaseModel):
    architecture: str = Field(description="An I… reference from list_importable_architectures.")
    name: str | None = Field(default=None, min_length=1, max_length=255,
                             description="The copy's name; 'My <name>' when left out.")


async def _importable(ctx: OperationContext, architecture_id):
    """The public architecture, as the menu's Import reads it (someone else's, public, live)."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from src.models.orm import Architecture, Collection, DataConnector

    return (await ctx.session.execute(
        select(Architecture).where(Architecture.id == architecture_id,
                                   Architecture.is_public.is_(True),
                                   Architecture.deleted_at.is_(None),
                                   Architecture.user_id != ctx.user.id)
        .options(selectinload(Architecture.collections.and_(Collection.deleted_at.is_(None)))
                 .selectinload(Collection.sku_selections),
                 selectinload(Architecture.connectors.and_(DataConnector.deleted_at.is_(None)))
                 .selectinload(DataConnector.sku_selection))
    )).scalar_one_or_none()


@registry.operation(
    "propose_import",
    "Propose importing a public architecture as the user's own private copy, named 'My <name>' "
    "unless they chose a name. The user sees it beside you with its cost and decides; nothing "
    "is saved until they accept.",
    ImportInput,
)
async def propose_import(ctx: OperationContext, args: ImportInput) -> OperationResult:
    row = ctx.rows.get(args.architecture)
    if row is None or row[0] != "importable":
        raise ToolError(f"unknown architecture {args.architecture!r}: use an I… reference from "
                        "list_importable_architectures in this message")
    source = await _importable(ctx, row[1])
    if source is None:
        raise ToolError("That architecture can't be imported now.")
    name = args.name or f"My {source.name}"
    draft = Draft(ArchitectureState(name=name, provider=source.provider),
                  await proposals.db_clock(ctx.session))
    ids = {}
    # Collections in their created order, parents first (as the menu's Import copies them).
    for collection in source.collections:
        ids[collection.id] = draft.add_collection(
            f"new{len(ids) + 1}", type=collection.type, name=collection.name,
            region=collection.region,
            parent_id=ids.get(collection.parent_collection_id), group=None)
        for s in collection.sku_selections:
            draft.add_service(_copy_spec(s), collection_id=ids[collection.id], group=None,
                              where=collection.name)
    for connector in source.connectors:
        if connector.from_collection_id not in ids or connector.to_collection_id not in ids:
            continue
        new = draft.add_connector(ids[connector.from_collection_id],
                                  ids[connector.to_collection_id],
                                  arrow_style=connector.arrow_style, group=None,
                                  label="Connector")
        if connector.arrow_reversed:
            draft.items[-1].after["arrow_reversed"] = True
        if connector.sku_selection is not None:
            draft.add_service(_copy_spec(connector.sku_selection), connector_id=new, group=None,
                              where="a connector")
    return await finish(ctx, draft, kind="import", title=name, base=None,
                        duration="1_month", assumptions=[], source_architecture_id=source.id)


def _copy_spec(selection) -> ServiceSpec:
    return ServiceSpec(selection.service_code, selection.sku, selection.pricing_term,
                       selection.purchase_option, Decimal(selection.usage_quantity),
                       selection.provider_options, selection.service_code)


async def _replay_pending(ctx: OperationContext, draft: Draft, architecture_id) -> None:
    """US6: the pending proposal's items, on the current base, as the start of a refinement."""
    from sqlalchemy import select

    from src.agent.operations import describe_pending
    from src.agent.proposals import ChangeItem, check_applies
    from src.models.orm import AgentProposal

    pending = (await ctx.session.execute(select(AgentProposal).where(
        AgentProposal.session_id == ctx.agent_session.id, AgentProposal.status == "pending",
        AgentProposal.architecture_id == architecture_id))).scalar_one_or_none()
    if pending is None:
        raise ToolError("there's no pending proposal for this architecture to revise")
    await describe_pending(ctx, architecture_id)  # its P… references, in case they're new
    items = [ChangeItem.from_json(i) for i in pending.items]
    try:
        check_applies(draft.base, items)
    except rules.RuleError as error:
        raise ToolError(error.message) from error
    for item in items:
        draft.items.append(item)
    draft._tick = len(items)


def _drop_added(draft: Draft, row_id) -> bool:
    """Take back an addition made earlier in this draft (and, for a collection, what was added
    inside it). True when something was dropped."""
    added = [i for i in draft.items if i.op == "add" and i.id == str(row_id)]
    if not added:
        return False
    gone = {str(row_id)}
    if added[0].target == "collection":
        gone |= {i.id for i in draft.items if i.op == "add" and i.target in ("service", "connector")
                 and str(row_id) in (str(i.after.get("collection_id")), str(i.after.get("from_id")),
                                     str(i.after.get("to_id")))}
    draft.items = [i for i in draft.items if i.id not in gone]
    for index, item in enumerate(draft.items, start=1):
        item.ref = f"P{index}"
    return True
