"""The comparison operations (024, contracts/agent-operations.md): `list_regions`,
`search_products`, `price_products`, `find_matches` and `price_matches`.

All are read-only (FR-014) and take the user and the open architecture from the request. The
model picks products by reference (`S…`, `C…`) from this message's searches; every candidate,
quality label, usage quantity and price is the app's (Principle I, VII). Amounts and
differences go back to the model as figure references only.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from src.agent import compare
from src.agent.matching.book import Candidate
from src.agent.matching.candidates import (
    SEARCHES,
    TOP_N,
    _Searcher,
    excluded,
    find_candidates,
)
from src.agent.matching.profiles import (
    FUNCTION_CATEGORY,
    FUNCTION_LABELS,
    product_label,
    profile,
)
from src.agent.matching.quality import lower, quality
from src.agent.matching.regions import RegionChoice, resolve_region
from src.agent.matching.usage import (
    STATED_UNITS,
    Converted,
    convert,
    default_usage,
    stated_quantity,
)
from src.agent.operations import OperationContext, OperationResult, ToolError, registry
from src.agent.results import PROVIDER_NAMES, create_result

Provider = Literal["aws", "azure", "gcp"]
Category = Literal["compute", "storage", "database", "networking"]
Function = Literal[tuple(FUNCTION_CATEGORY)]  # type: ignore[valid-type]
Term = Literal["on_demand", "reserved_1yr", "reserved_3yr", "savings_plan_1yr",
               "savings_plan_3yr", "commitment_1yr", "commitment_3yr"]
PurchaseOption = Literal["no_upfront", "partial_upfront", "all_upfront"]
Duration = Literal["1_day", "1_month", "1_year"]
Quality = Literal["exact", "close", "partial", "no_equivalent"]

# How many candidates per target go back to the model (the app keeps up to TOP_N).
SHOWN_TO_MODEL = 3


def _available(provider: str) -> set[str]:
    from src.pricing_data.active_snapshot import get_active_snapshot
    from src.pricing_data.errors import PricingDataUnavailableError
    from src.pricing_data.providers.registry import get_provider

    adapter = get_provider(provider)
    try:
        return set(adapter.locations(get_active_snapshot(adapter.code)))
    except PricingDataUnavailableError:
        return set()


def _region_out(choice: RegionChoice) -> dict:
    out = {"region": choice.region, "guessed": choice.guessed}
    if not choice.available:
        out["unavailable"] = choice.reason
    return out


def _candidate_out(c: Candidate, *, with_quality: bool = True) -> dict:
    out: dict = {"ref": c.ref, "product": c.label,
                 "type": FUNCTION_LABELS.get(c.profile.function, c.profile.function)}
    if with_quality and c.quality:
        out["quality"] = c.quality
        if c.differences:
            out["differences"] = c.differences[:3]
    if c.usage_note:
        out["usage"] = c.usage_note
    if c.unconvertible:
        out["usage"] = f"can't be converted: {c.unconvertible}"
    if c.price_types:
        out["terms"] = list(c.price_types)
    return out


def _term_or_unavailable(candidate: Candidate, term: str) -> str | None:
    """Why the candidate can't be priced on `term`, or None. AWS items don't list their terms;
    the engine reports those as unpriceable."""
    if candidate.provider != "aws" and candidate.price_types and term not in candidate.price_types:
        return f"term not offered (offers: {', '.join(candidate.price_types)})"
    return None


# --- list_regions --------------------------------------------------------------------------------


class ListRegionsInput(BaseModel):
    provider: Provider
    near: str | None = Field(default=None, description="A region on any provider, e.g. "
                             "us-east-1; returns the guessed nearest region too.")
    near_provider: Provider | None = Field(default=None, description="The provider of `near`.")


@registry.operation(
    "list_regions",
    "The regions a provider has pricing data for. With `near`, also the guessed nearest region "
    "(always say it's a guess).",
    ListRegionsInput,
)
async def list_regions(ctx: OperationContext, args: ListRegionsInput) -> OperationResult:
    available = _available(args.provider)
    data: dict = {"provider": args.provider, "regions": sorted(available)}
    if args.near:
        choice = resolve_region(args.provider, None, available=available,
                                near=(args.near_provider or args.provider, args.near))
        data["guess"] = _region_out(choice)
    return OperationResult(data=data, summary={"provider": args.provider,
                                               "regions": len(available)})


# --- search_products / price_products (category questions, single prices) -----------------------


class SearchProductsInput(BaseModel):
    providers: list[Provider] = Field(min_length=1, max_length=3)
    category: Category
    function: Function | None = Field(  # type: ignore[valid-type]
        default=None, description="Narrow to one kind of product, e.g. object_storage, vm.")
    regions: dict[Provider, str] = Field(
        default_factory=dict, description="A region per provider. Missing ones are guessed "
        "near the first one given, or near the open architecture's region.")
    text: str | None = Field(default=None, max_length=100,
                             description="Search words, e.g. 'hot lrs' or 'm5.large'.")
    reference: str | None = Field(default=None, description="A C… product to compare against: "
                                  "every result then carries a match quality.")


async def _anchor(ctx: OperationContext) -> tuple[str, str] | None:
    """The open architecture's provider and first region, to guess regions near."""
    if ctx.open_architecture_id is None:
        return None
    from src.agent.operations import _open_architecture

    try:
        _arch, detail = await _open_architecture(ctx)
    except ToolError:
        return None
    region = next((c.region for c in detail.collections if c.region), None)
    return (detail.provider, region) if region else None


async def _regions(ctx: OperationContext, providers: list[str],
                   regions: dict[str, str]) -> dict[str, RegionChoice]:
    near = next(((p, r) for p, r in regions.items()), None) or await _anchor(ctx)
    out: dict[str, RegionChoice] = {}
    for provider in providers:
        out[provider] = resolve_region(provider, regions.get(provider),
                                       available=_available(provider), near=near)
    return out


async def _search_rows(searcher, provider: str, region: str, functions: list[str],
                       text: str | None) -> list:
    rows = []
    for function in functions:
        for filters in SEARCHES[provider].get(function, []):
            if text:
                filters = {**filters, "text": text}
            rows.extend(await searcher.search(provider, region, filters))
    return rows


async def search_region(searcher, provider: str, region: str, functions: list[str],
                        text: str | None, reference: Candidate | None = None) -> list[Candidate]:
    """The catalog's products of `functions` in one provider and region, best first (up to
    TOP_N), with match qualities against `reference` when given. Shared by `search_products`
    (024) and `find_products` (025), so both search the catalog the same way."""
    rows = await _search_rows(searcher, provider, region, functions, text)
    # Search words are matched as one phrase. When several words find nothing (a name the
    # catalog doesn't use, e.g. "internet egress"), try each word, longest first.
    words = sorted({w for w in (text or "").split() if len(w) >= 3}, key=lambda w: (-len(w), w))
    if not rows and len(words) > 1:
        for word in words:
            rows = await _search_rows(searcher, provider, region, functions, word)
            if rows:
                break
    units: dict = {}
    if provider == "aws" and rows:
        from src.agent.matching.candidates import _aws_units

        units = _aws_units(region, sorted({r.sku for r in rows}))
    candidates: list[Candidate] = []
    seen: set[str] = set()
    for row in rows:
        if row.sku in seen:
            continue
        seen.add(row.sku)
        target = profile(row, unit=units.get(row.sku) if provider == "aws" else None)
        if target.function not in functions:
            continue
        if excluded(product_label(row), row.attributes):
            continue
        candidate = Candidate(
            source_ref=None, provider=provider, region=region,
            service_code=row.service_code, sku=row.sku, label=product_label(row),
            profile=target, price_types=tuple(row.price_types),
            unit=units.get(row.sku) or row.unit, ram_sku=row.attributes.get("ram_sku"),
        )
        if reference is not None:
            candidate.quality, candidate.differences = quality(reference.profile, target)
        candidates.append(candidate)
    if provider == "gcp":
        from src.agent.matching.candidates import _gcp_ram_skus

        pairs = _gcp_ram_skus(rows)
        for c in candidates:
            c.ram_sku = c.ram_sku or pairs.get(c.sku)
    from src.agent.matching.quality import LABELS

    candidates.sort(key=lambda c: (LABELS.index(c.quality) if c.quality else 0,
                                   functions.index(c.profile.function), c.label, c.sku))
    return [c for c in candidates if c.quality != "no_equivalent"][:TOP_N]


@registry.operation(
    "search_products",
    "Find products in a category on one or more providers (up to 5 each), for a comparison or "
    "a single price. Returns C… references to pick from; the app gives each its match quality "
    "against `reference` when set. Region guesses are flagged.",
    SearchProductsInput,
)
async def search_products(ctx: OperationContext, args: SearchProductsInput) -> OperationResult:
    functions = ([args.function] if args.function else
                 [f for f, c in FUNCTION_CATEGORY.items() if c == args.category])
    if args.function and FUNCTION_CATEGORY[args.function] != args.category:
        raise ToolError(f"{args.function} is in {FUNCTION_CATEGORY[args.function]}, not "
                        f"{args.category}")
    reference = ctx.matches.candidate(args.reference) if args.reference else None
    choices = await _regions(ctx, list(dict.fromkeys(args.providers)), args.regions)
    searcher = _Searcher()
    data: dict = {"category": args.category, "providers": {}}
    found_total = 0
    for provider, choice in choices.items():
        entry: dict = _region_out(choice)
        if not choice.available:
            data["providers"][provider] = entry
            continue
        kept = await search_region(searcher, provider, choice.region, functions, args.text,
                                   reference)
        for c in kept:
            ctx.matches.add_candidate(c)
        entry["products"] = [_candidate_out(c, with_quality=reference is not None)
                             for c in kept]
        if not kept:
            entry["none_found"] = "no product of that kind in this region"
        found_total += len(kept)
        data["providers"][provider] = entry
    return OperationResult(
        data=data,
        summary={"category": args.category, "function": args.function,
                 "regions": {p: c.region for p, c in choices.items()},
                 "candidates": found_total},
    )


class Usage(BaseModel):
    quantity: Decimal = Field(gt=0)
    unit: Literal[tuple(STATED_UNITS)]  # type: ignore[valid-type]


class Size(BaseModel):
    vcpu: int = Field(gt=0)
    memory_gib: Decimal = Field(gt=0)


class PriceProductsInput(BaseModel):
    picks: list[str] = Field(min_length=1, max_length=4,
                             description="C… references; the first is the reference.")
    usage: Usage | Literal["default"] = Field(
        description="The amount, e.g. {quantity: 10, unit: tb}, or 'default' for the app's "
        "default for this kind of product (say which default was used).")
    duration: Duration = "1_month"
    terms: dict[Provider, Term] = Field(default_factory=dict,
                                        description="Per provider; on_demand when missing.")
    purchase_options: dict[Provider, PurchaseOption] = Field(default_factory=dict)
    size: Size | None = Field(default=None, description="vCPU and memory, for machines that "
                              "are priced by size (GCP), when the reference doesn't say.")


def _usage_for(candidate: Candidate, usage, reference: Candidate,
               size: Size | None) -> tuple[Converted | None, str | None, str]:
    """(converted, why not, usage label) for one pick."""
    if usage == "default":
        default = default_usage(reference.profile.function)
        if default is None:
            raise ToolError(f"There's no default amount for "
                            f"{FUNCTION_LABELS.get(reference.profile.function)}; ask the user "
                            "for one.")
        amount, unit = default.amount, default.unit
    else:
        amount, unit = usage.quantity, usage.unit
    stated = stated_quantity(candidate.profile.unit_kind, amount, unit)
    if not isinstance(stated, Converted):
        return None, stated.reason, f"{amount} {unit}"
    label = stated.note or ""
    if usage == "default":
        label = default.label
    options = None
    if candidate.provider == "gcp" and candidate.profile.function in ("vm", "managed_db"):
        specs = reference.profile.specs if reference is not candidate else {}
        vcpu = size.vcpu if size else specs.get("vcpu")
        memory = size.memory_gib if size else specs.get("memory_gib")
        if vcpu is None or memory is None:
            return None, "say how many vCPU and GiB of memory to price (size)", label
        from src.agent.matching.profiles import ProductProfile

        sized = ProductProfile("vm", "compute", candidate.profile.unit_kind,
                               {"vcpu": int(vcpu), "memory_gib": Decimal(str(memory))})
        converted = convert(sized, stated.quantity, candidate.profile, target_provider="gcp",
                            ram_sku=candidate.ram_sku)
        if not isinstance(converted, Converted):
            return None, converted.reason, label
        options = converted.options
    elif candidate.provider == "azure" and candidate.profile.function == "vm":
        options = {"kind": "azure_vm", "version": 1,
                   "os": reference.profile.specs.get("os", "linux")
                   if reference.profile.specs.get("os") in ("linux", "windows") else "linux"}
    return Converted(stated.quantity, options), None, label


@registry.operation(
    "price_products",
    "Price picked products (C… references from search_products) for a usage and duration. "
    "One pick: its price. Two or more: a comparison shown to the user as a table, with "
    "differences against the first pick. Amounts come back as figure references.",
    PriceProductsInput,
)
async def price_products(ctx: OperationContext, args: PriceProductsInput) -> OperationResult:
    picks = [ctx.matches.candidate(ref) for ref in args.picks]
    reference = picks[0]
    sides: list[compare.Side] = []
    cells: dict[str, compare.Cell] = {}
    usage_label = ""
    for pick in picks:
        term, option = compare.term_option(pick.provider, args.terms.get(pick.provider,
                                                                         "on_demand"),
                                           args.purchase_options.get(pick.provider))
        side_id = f"{pick.provider}:{pick.region}"
        if any(s.id == side_id for s in sides):
            raise ToolError(f"two picks for {side_id}: pick one product per provider and region")
        sides.append(compare.Side(side_id, pick.provider, pick.region, False, term, option))
        converted, why, label = _usage_for(pick, args.usage, reference, args.size)
        usage_label = usage_label or label
        cell = compare.Cell(product=pick.label, usage=label)
        if pick is not reference:
            cell.quality = quality(reference.profile, pick.profile)[0]
            cell.shown_quality = cell.quality
            cell.differences = quality(reference.profile, pick.profile)[1]
        if why is not None:
            cell.status, cell.reason = "unconvertible", why
        elif (not_offered := _term_or_unavailable(pick, term)) is not None:
            cell.status, cell.reason = "unavailable", not_offered
        else:
            cell.line = compare.PriceLine("r1", pick.service_code, pick.sku, pick.region,
                                          converted.quantity, term, option, converted.options)
        cells[side_id] = cell
    function = reference.profile.function
    row = compare.Row(FUNCTION_LABELS.get(function, function).capitalize(), None, cells)
    import asyncio

    outcome = await asyncio.to_thread(compare.price_comparison, sides, [row], args.duration)
    snapshot = outcome.snapshots or None
    figures: dict = {}
    for side in sides:
        cell = row.cells[side.id]
        entry: dict = {"product": cell.product, "region": side.region,
                       "term": compare.term_label(side.term, side.purchase_option)}
        if cell.status == "ok" and cell.amount is not None:
            entry["price"] = ctx.figures.add(cell.amount, "price", duration=args.duration,
                                             snapshot={side.provider:
                                                       outcome.snapshots[side.provider]})
            if cell.diff is not None:
                entry["difference"] = ctx.figures.add(cell.diff, "difference",
                                                      duration=args.duration)
            if cell.diff_pct is not None:
                entry["difference_pct"] = ctx.figures.add(cell.diff_pct, "difference_pct",
                                                          kind="percent")
            if cell.quality:
                entry["quality"] = cell.quality
                if cell.differences:
                    entry["differences"] = cell.differences
        else:
            entry["unavailable"] = cell.reason
        figures[side.id] = entry
    data: dict = {"duration": args.duration, "usage": usage_label, "currency": "USD",
                  "prices": figures,
                  "snapshots": {p: s["date"] for p, s in outcome.snapshots.items()}}
    summary: dict = {"picks": [f"{p.provider}:{p.region}:{p.service_code}:{p.sku}"
                               for p in picks],
                     "usage": usage_label, "duration": args.duration}
    if len(picks) > 1 and outcome.any_priced():
        basis = {"question_kind": "category", "category": FUNCTION_CATEGORY.get(function),
                 "duration": args.duration, "reference_side": sides[0].id,
                 "usage": usage_label,
                 "assumptions": _assumptions(args.usage == "default", usage_label,
                                             args.terms, sides)}
        names = " vs ".join(PROVIDER_NAMES[s.provider] for s in sides)
        result = await create_result(ctx.session, ctx.agent_session, ctx.message, outcome,
                                     kind="category_comparison",
                                     title=f"{row.label}: {names}", basis=basis)
        ctx.results.append(result)
        data["result_id"] = str(result.id)
        data["shown_as_table"] = True
        summary["result_id"] = str(result.id)
    return OperationResult(data=data, summary=summary, snapshot=snapshot)


def _assumptions(default_usage_used: bool, usage_label: str, terms: dict,
                 sides: list[compare.Side]) -> list[str]:
    out = []
    if default_usage_used:
        out.append(f"Default usage: {usage_label}")
    for side in sides:
        if side.provider not in terms:
            out.append(f"{PROVIDER_NAMES[side.provider]} on demand (default term)")
        if side.region_guessed:
            out.append(f"{PROVIDER_NAMES[side.provider]} region {side.region} is a guess")
    return out


# --- find_matches / price_matches (the open architecture) ----------------------------------------


class FindMatchesInput(BaseModel):
    target_providers: list[Provider] = Field(min_length=1, max_length=2)
    category: Category | None = Field(default=None, description="Only this part of the "
                                      "architecture, e.g. storage for 'my storage'.")
    target_regions: dict[Provider, str] = Field(
        default_factory=dict, description="One region per target provider for every service; "
        "missing ones are guessed per region of the architecture.")
    hints: dict[str, str] = Field(default_factory=dict, description="S… → search words, to "
                                  "search again for one service (a user's correction).")


@registry.operation(
    "find_matches",
    "For the open architecture (or one category of it), find the closest products on one or "
    "two other providers for every service at once. Returns sources S… with candidates C… and "
    "the app's match quality; then call price_matches with your picks.",
    FindMatchesInput,
)
async def find_matches(ctx: OperationContext, args: FindMatchesInput) -> OperationResult:
    from src.agent.operations import _open_architecture

    _architecture, detail = await _open_architecture(ctx)
    targets = list(dict.fromkeys(args.target_providers))
    if detail.provider in targets:
        raise ToolError(f"The open architecture is already on {detail.provider.upper()}. Say "
                        "so, and offer its current total (price_open_architecture) instead.")
    for ref in args.hints:
        ctx.matches.source(ref)
    sources = await compare.architecture_sources(detail, category=args.category)
    if not sources:
        return OperationResult(data={"empty": True, "message": "No services in the open "
                                     "architecture" + (f" in {args.category}" if args.category
                                                       else "") + "."},
                               summary={"empty": True})
    hints_by_label: dict[str, str] = {}
    if args.hints:
        for ref, text in args.hints.items():
            old = ctx.matches.sources[ref]
            hints_by_label[(old.where or "") + "|" + old.sku] = text
    # A fresh set of sources for this search (the architecture as it is now).
    for source in sources:
        ctx.matches.add_source(source)
    hints = {s.ref: hints_by_label[(s.where or "") + "|" + s.sku] for s in sources
             if (s.where or "") + "|" + s.sku in hints_by_label}
    region_map: dict[str, dict[str, RegionChoice]] = {p: {} for p in targets}
    for provider in targets:
        available = _available(provider)
        for region in sorted({s.region for s in sources}):
            region_map[provider][region] = resolve_region(
                provider, args.target_regions.get(provider), available=available,
                near=(detail.provider, region))
    ctx.matches.latest_sources = [s.ref for s in sources]
    ctx.matches.targets = targets
    ctx.matches.region_choices = region_map
    ctx.matches.category = args.category
    total, offset = len(sources), 0
    found: dict[str, dict[str, list[Candidate]]] = {s.ref: {} for s in sources}
    for region in sorted({s.region for s in sources}):
        group = [s for s in sources if s.region == region]
        targets_here = {p: region_map[p][region].region for p in targets
                        if region_map[p][region].available}

        def progress(done: int, _total: int, label: str, _offset=offset) -> None:
            ctx.progress(_offset + done, total, label)

        if targets_here:
            got = await find_candidates(ctx.matches, group, targets_here, hints=hints,
                                        progress=progress)
            for ref, per in got.items():
                found[ref].update(per)
        else:
            progress(len(group), total, "Matching services")
        offset += len(group)
    out_sources = []
    for source in sources:
        entry: dict = {"ref": source.ref, "service": source.label, "where": source.where,
                       "candidates": {}}
        for provider in targets:
            choice = region_map[provider][source.region]
            if not choice.available:
                entry["candidates"][provider] = {"unavailable": choice.reason}
                continue
            cands = found[source.ref].get(provider, [])
            if cands:
                entry["candidates"][provider] = [_candidate_out(c)
                                                 for c in cands[:SHOWN_TO_MODEL]]
            else:
                entry["candidates"][provider] = {
                    "no_equivalent": ctx.matches.unmatched.get((source.ref, provider),
                                                               "no product in the same category")}
        out_sources.append(entry)
    regions_out = {p: {r: _region_out(c) for r, c in m.items()} for p, m in region_map.items()}
    matched = sum(1 for s in sources for p in targets if found[s.ref].get(p))
    return OperationResult(
        data={"architecture": detail.name, "source_provider": detail.provider,
              "regions": regions_out, "sources": out_sources,
              "next": "Call price_matches with one pick per source and target (the first "
                      "candidate is the app's best; null for no equivalent)."},
        summary={"architecture": detail.name, "targets": targets, "sources": len(sources),
                 "matched": matched,
                 "regions": {p: {r: c.region for r, c in m.items()}
                             for p, m in region_map.items()}},
    )


class Pick(BaseModel):
    source: str
    provider: Provider
    candidate: str | None = Field(description="A C… candidate of this source, or null for no "
                                  "equivalent.")
    shown_quality: Quality | None = Field(default=None, description="Only to lower the app's "
                                          "label; give a reason.")
    reason: str | None = Field(default=None, max_length=200)


class PriceMatchesInput(BaseModel):
    duration: Duration = "1_month"
    terms: dict[Provider, Term] = Field(default_factory=dict,
                                        description="Per target provider; on_demand when "
                                        "missing. The architecture keeps its own terms.")
    purchase_options: dict[Provider, PurchaseOption] = Field(default_factory=dict)
    picks: list[Pick] = Field(default_factory=list, description="Missing picks use the app's "
                              "best candidate.")


@registry.operation(
    "price_matches",
    "Price the open architecture against its matches from find_matches (this message), as a "
    "comparison shown to the user as a table: per service and totals, with differences. "
    "Amounts come back as figure references.",
    PriceMatchesInput,
)
async def price_matches(ctx: OperationContext, args: PriceMatchesInput) -> OperationResult:
    from src.agent.operations import _open_architecture

    book = ctx.matches
    if not book.latest_sources or not book.targets:
        raise ToolError("Call find_matches first, in this message.")
    _architecture, detail = await _open_architecture(ctx)
    sources = [book.sources[ref] for ref in book.latest_sources]
    targets = list(book.targets)
    picks: dict[tuple[str, str], Pick] = {}
    for pick in args.picks:
        source = book.source(pick.source)
        if pick.provider not in targets:
            raise ToolError(f"{pick.provider} wasn't a target of find_matches")
        if source.ref not in book.latest_sources:
            raise ToolError(f"{pick.source} is from an earlier find_matches; use the latest one")
        if pick.candidate is not None:
            candidate = book.candidate(pick.candidate)
            if candidate.source_ref != source.ref or candidate.provider != pick.provider:
                raise ToolError(f"{pick.candidate} isn't a {pick.provider} candidate of "
                                f"{pick.source}")
        picks[(pick.source, pick.provider)] = pick
    region_choices: dict = book.region_choices
    sides = [compare.Side(detail.provider, detail.provider,
                          ", ".join(sorted({s.region for s in sources})), False, "as_saved",
                          "not_applicable")]
    for provider in targets:
        term, option = compare.term_option(provider, args.terms.get(provider, "on_demand"),
                                           args.purchase_options.get(provider))
        choices = region_choices.get(provider, {})
        regions = sorted({c.region for c in choices.values() if c.region})
        side = compare.Side(provider, provider, ", ".join(regions),
                            any(c.guessed for c in choices.values()), term, option)
        if choices and not any(c.available for c in choices.values()):
            side.available = False
            side.reason = next(iter(choices.values())).reason
        sides.append(side)
    rows: list[compare.Row] = []
    defaulted = 0
    for index, source in enumerate(sources):
        key = f"r{index + 1}"
        cells = {detail.provider: compare.Cell(
            product=source.label,
            line=compare.PriceLine(key, source.service_code, source.sku, source.region,
                                   source.usage_quantity, source.pricing_term,
                                   source.purchase_option, source.provider_options))}
        for side in sides[1:]:
            provider = side.provider
            choice = region_choices.get(provider, {}).get(source.region)
            if choice is not None and not choice.available:
                cells[provider] = compare.Cell(status="unavailable", reason=choice.reason)
                continue
            pick = picks.get((source.ref, provider))
            candidates = [c for c in book.candidates.values()
                          if c.source_ref == source.ref and c.provider == provider]
            if pick is None:
                candidate = candidates[0] if candidates else None
                if candidate is not None:
                    defaulted += 1
            else:
                candidate = book.candidate(pick.candidate) if pick.candidate else None
            if candidate is None:
                cells[provider] = compare.Cell(
                    status="unmatched",
                    reason=book.unmatched.get((source.ref, provider),
                                              "no equivalent picked"))
                continue
            shown = lower(candidate.quality or "partial", pick.shown_quality if pick else None,
                          pick.reason if pick else None)
            cell = compare.Cell(product=candidate.label, quality=candidate.quality,
                                shown_quality=shown,
                                quality_reason=pick.reason if pick and shown !=
                                candidate.quality else None,
                                differences=list(candidate.differences),
                                usage=candidate.usage_note)
            if candidate.unconvertible:
                cell.status, cell.reason = "unconvertible", candidate.unconvertible
            elif (not_offered := _term_or_unavailable(candidate, side.term)) is not None:
                cell.status, cell.reason = "unavailable", not_offered
            else:
                cell.line = compare.PriceLine(key, candidate.service_code, candidate.sku,
                                              candidate.region, candidate.quantity, side.term,
                                              side.purchase_option, candidate.options)
            cells[provider] = cell
        rows.append(compare.Row(source.label, source.where, cells))
    import asyncio

    outcome = await asyncio.to_thread(compare.price_comparison, sides, rows, args.duration)
    if not outcome.any_priced():
        return OperationResult(data={"nothing_priced": True,
                                     "not_compared": outcome.not_compared},
                               summary={"nothing_priced": True})
    names = ", ".join(PROVIDER_NAMES[p] for p in targets)
    basis = {"question_kind": "architecture", "architecture": detail.name,
             "category": book.category, "duration": args.duration,
             "reference_side": detail.provider, "usage": "as in the architecture",
             "assumptions": _match_assumptions(args, sides, defaulted)}
    result = await create_result(
        ctx.session, ctx.agent_session, ctx.message, outcome, kind="architecture_comparison",
        title=f"{detail.name}: {PROVIDER_NAMES[detail.provider]} vs {names}", basis=basis)
    ctx.results.append(result)
    totals = {}
    for side in sides:
        total = outcome.totals[side.id]
        entry: dict = {"partial": total["partial"]}
        if total["amount"] is not None:
            snap = outcome.snapshots.get(side.provider)
            entry["total"] = ctx.figures.add(total["amount"], "total", duration=args.duration,
                                             snapshot={side.provider: snap} if snap else None)
        if total["diff"] is not None:
            entry["difference"] = ctx.figures.add(total["diff"], "difference",
                                                  duration=args.duration)
        if total["diff_pct"] is not None:
            entry["difference_pct"] = ctx.figures.add(total["diff_pct"], "difference_pct",
                                                      kind="percent")
        if not side.available:
            entry["unavailable"] = side.reason
        totals[side.id] = entry
    biggest = []
    for row in rows:
        for side in sides[1:]:
            cell = row.cells.get(side.id)
            if cell and cell.diff is not None:
                biggest.append((abs(cell.diff), row.label, side.id, cell))
    biggest.sort(key=lambda item: (-item[0], item[1], item[2]))
    largest = [{"service": label, "provider": side_id,
                "quality": cell.shown_quality,
                "difference": ctx.figures.add(cell.diff, "difference", duration=args.duration),
                **({"difference_pct": ctx.figures.add(cell.diff_pct, "difference_pct",
                                                      kind="percent")}
                   if cell.diff_pct is not None else {})}
               for _a, label, side_id, cell in biggest[:5]]
    lowered = [{"service": r.label, "provider": p, "quality": c.shown_quality}
               for r in rows for p, c in r.cells.items()
               if c.quality and c.quality != "exact" and c.status == "ok"][:10]
    data = {"result_id": str(result.id), "shown_as_table": True, "architecture": detail.name,
            "duration": args.duration, "totals": totals, "largest_differences": largest,
            "not_exact": lowered, "not_compared": outcome.not_compared,
            "default_picks": defaulted,
            "snapshots": {p: s["date"] for p, s in outcome.snapshots.items()}}
    summary = {"result_id": str(result.id), "rows": len(rows), "targets": targets,
               "terms": {s.provider: s.term for s in sides[1:]}, "default_picks": defaulted,
               "picks": {f"{r.label} ({r.where})": {p: c.line.sku for p, c in r.cells.items()
                                                    if c.line is not None}
                         for r in rows}}
    return OperationResult(data=data, summary=summary, snapshot=outcome.snapshots or None)


def _match_assumptions(args: PriceMatchesInput, sides: list[compare.Side],
                       defaulted: int) -> list[str]:
    out = []
    for side in sides[1:]:
        if side.provider not in args.terms:
            out.append(f"{PROVIDER_NAMES[side.provider]} on demand (default term)")
        if side.region_guessed:
            out.append(f"{PROVIDER_NAMES[side.provider]} regions {side.region} are guesses")
    if defaulted:
        out.append(f"{defaulted} match{'es' if defaulted != 1 else ''} use the app's best "
                   "candidate")
    return out
