"""Comparisons (024, research R5): the sources of an open architecture, and pricing every side
of a comparison through the pricing engine.

Each side (a provider in a region) is priced as one transient architecture, never added to the
database session, with `calculate_architecture_price`: the exact code path the Pricing tab uses
(Principle I). Differences and percentages are computed here from the engine's unrounded values;
nothing is estimated. A comparison's totals cover only the rows priced on every side, and are
labelled partial when any row is left out (FR-012).
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from src.agent.matching.book import SourceProduct
from src.agent.matching.profiles import product_label, profile
from src.models.orm import Architecture, Collection, SKUSelection

# The pricing terms of FR-004, as the app names them.
TERMS: dict[str, tuple[str, ...]] = {
    "aws": ("on_demand", "reserved_1yr", "reserved_3yr"),
    "azure": ("on_demand", "savings_plan_1yr", "savings_plan_3yr", "reserved_1yr",
              "reserved_3yr"),
    "gcp": ("on_demand", "commitment_1yr", "commitment_3yr"),
}
PURCHASE_OPTIONS = ("no_upfront", "partial_upfront", "all_upfront")
TERM_LABELS = {
    "on_demand": "on demand", "reserved_1yr": "reserved 1 year", "reserved_3yr": "reserved 3 years",
    "savings_plan_1yr": "savings plan 1 year", "savings_plan_3yr": "savings plan 3 years",
    "commitment_1yr": "committed use 1 year", "commitment_3yr": "committed use 3 years",
    "as_saved": "as in the architecture",
}


def term_option(provider: str, term: str, purchase_option: str | None) -> tuple[str, str]:
    """(pricing_term, purchase_option) for the engine; raises ToolError for a term the provider
    doesn't have in this app (FR-004)."""
    from src.agent.operations import ToolError

    if term not in TERMS[provider]:
        raise ToolError(f"{term} isn't a {provider.upper()} pricing term here. Use one of: "
                        f"{', '.join(TERMS[provider])}.")
    if provider == "aws" and term.startswith("reserved"):
        option = purchase_option or "no_upfront"
        if option not in PURCHASE_OPTIONS:
            raise ToolError(f"purchase option must be one of {', '.join(PURCHASE_OPTIONS)}")
        return term, option
    return term, "not_applicable"


def term_label(term: str, purchase_option: str | None) -> str:
    label = TERM_LABELS.get(term, term)
    if purchase_option and purchase_option != "not_applicable":
        label += f", {purchase_option.replace('_', ' ')}"
    return label


# --- Sources from the open architecture ---------------------------------------------------------


def _selection_label(selection) -> str:
    name = selection.service_name or selection.service_code
    if selection.product_family and selection.product_family not in name:
        return f"{name} ({selection.product_family})"
    return name


def _describe(provider: str, region: str, pairs: list[tuple[str, str]],
              unit_keys: list[tuple[str, str, str]]):
    from src.pricing_data.active_snapshot import get_active_snapshot
    from src.pricing_data.providers.registry import get_provider

    adapter = get_provider(provider)
    snapshot = get_active_snapshot(adapter.code)
    items = adapter.describe(snapshot, pairs, region=region)
    units = adapter.units(snapshot, unit_keys, region=region) if unit_keys else {}
    return items, units


async def architecture_sources(detail, *, category: str | None = None) -> list[SourceProduct]:
    """The open architecture's services as comparison sources, in canvas order (collections,
    then connectors). `category` limits them to one app category ("my storage")."""
    provider = detail.provider
    names = {c.id: c.name for c in detail.collections}
    regions = {c.id: c.region for c in detail.collections}
    entries = []  # (selection, where, region)
    owners: dict = {}  # selection id -> ("collection" | "connector", id)
    for collection in detail.collections:
        for selection in collection.sku_selections:
            entries.append((selection, collection.name, collection.region))
            owners[selection.id] = ("collection", collection.id)
    for connector in detail.connectors:
        if connector.sku_selection is not None:
            where = (f"connector {names.get(connector.from_collection_id, '?')} → "
                     f"{names.get(connector.to_collection_id, '?')}")
            entries.append((connector.sku_selection, where,
                            regions.get(connector.from_collection_id)))
            owners[connector.sku_selection.id] = ("connector", connector.id)
    by_region: dict[str, list] = defaultdict(list)
    for entry in entries:
        by_region[entry[2]].append(entry)
    described: dict[tuple[str, str, str], tuple] = {}
    for region, group in by_region.items():
        pairs = sorted({(s.service_code, s.sku) for s, _w, _r in group})
        keys = sorted({(s.sku, s.pricing_term.value, s.purchase_option.value)
                       for s, _w, _r in group})
        items, units = await asyncio.to_thread(_describe, provider, region, pairs, keys)
        for selection, _where, _region in group:
            item = items.get((selection.service_code, selection.sku))
            unit = units.get((selection.sku, selection.pricing_term.value,
                              selection.purchase_option.value))
            described[(region, selection.service_code, selection.sku)] = (item, unit)
    from src.pricing_data.providers.registry import get_provider

    adapter = get_provider(provider)
    sources: list[SourceProduct] = []
    for selection, where, region in entries:
        item, unit = described[(region, selection.service_code, selection.sku)]
        if item is None:
            from src.agent.matching.profiles import ProductProfile

            source_profile = ProductProfile("other", None, "unknown", {})
            label = _selection_label(selection)
        else:
            source_profile = profile(item, unit=unit if provider == "aws" else None)
            label = _selection_label(selection)
            if item.attributes.get("instanceType"):
                label = f"{label} {item.attributes['instanceType']}"
        options = selection.provider_options
        if hasattr(options, "model_dump"):
            options = options.model_dump(mode="json")
        if provider == "azure" and options and options.get("os"):
            source_profile.specs.setdefault("os", options["os"])
        if provider == "gcp" and options and options.get("kind") == "gcp_machine":
            source_profile.specs["vcpu"] = int(options["vcpus"])
            source_profile.specs["memory_gib"] = Decimal(str(options["memory_gib"]))
        if category and source_profile.category != category:
            continue
        sources.append(SourceProduct(
            provider=provider, region=region, service_code=selection.service_code,
            sku=selection.sku, label=label, where=where,
            usage_quantity=Decimal(selection.usage_quantity), unit=unit,
            pricing_term=selection.pricing_term.value,
            purchase_option=selection.purchase_option.value, profile=source_profile,
            provider_options=options,
            product_key=adapter.product_key(item) if item is not None else None,
            selection_id=selection.id, owner=owners.get(selection.id),
        ))
    return sources


# --- Pricing sides ------------------------------------------------------------------------------


@dataclass
class PriceLine:
    key: str
    service_code: str
    sku: str
    region: str
    quantity: Decimal
    pricing_term: str
    purchase_option: str
    options: dict | None = None


@dataclass
class SidePricing:
    amounts: dict[str, Decimal] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)
    snapshot: dict | None = None  # {"date", "revision"}
    error: str | None = None


def price_lines(provider: str, lines: list[PriceLine], duration: str) -> SidePricing:
    """Price `lines` for one provider through the engine, as one transient architecture."""
    from src.models.schemas import CalculationDuration
    from src.pricing_data.errors import PricingDataUnavailableError
    from src.services.price_calculation import calculate_architecture_price

    out = SidePricing()
    if not lines:
        return out
    architecture = Architecture(id=uuid.uuid4(), name="comparison", provider=provider)
    collections: dict[str, Collection] = {}
    keys: dict[uuid.UUID, str] = {}
    for line in lines:
        collection = collections.get(line.region)
        if collection is None:
            collection = Collection(id=uuid.uuid4(), type="application_component",
                                    name="comparison", region=line.region)
            collection.sku_selections = []
            collections[line.region] = collection
        selection = SKUSelection(
            id=uuid.uuid4(), collection_id=collection.id, service_code=line.service_code,
            sku=line.sku, pricing_term=line.pricing_term, purchase_option=line.purchase_option,
            usage_quantity=line.quantity, provider_options=line.options,
        )
        collection.sku_selections.append(selection)
        keys[selection.id] = line.key
    architecture.collections = list(collections.values())
    architecture.connectors = []
    try:
        result = calculate_architecture_price(architecture,
                                              duration=CalculationDuration(duration))
    except PricingDataUnavailableError as exc:
        out.error = str(exc)
        return out
    out.snapshot = {"date": str(result.snapshot_date), "revision": int(result.snapshot_revision)}
    for item in result.line_items:
        key = keys.get(item.sku_selection_id)
        if key is None:
            continue
        if item.priceable and item.price is not None:
            out.amounts[key] = out.amounts.get(key, Decimal(0)) + Decimal(item.price)
    for item in result.unpriceable:
        key = keys.get(item.sku_selection_id)
        if key is not None:
            out.amounts.pop(key, None)
            out.reasons[key] = item.reason
    return out


# --- Building a comparison ----------------------------------------------------------------------


@dataclass
class Side:
    id: str
    provider: str
    region: str | None
    region_guessed: bool
    term: str
    purchase_option: str
    available: bool = True
    reason: str | None = None

    def out(self) -> dict:
        return {"id": self.id, "provider": self.provider, "region": self.region or "",
                "region_guessed": self.region_guessed, "term": self.term,
                "purchase_option": None if self.purchase_option == "not_applicable"
                else self.purchase_option}


@dataclass
class Cell:
    product: str | None = None
    line: PriceLine | None = None
    quality: str | None = None
    shown_quality: str | None = None
    quality_reason: str | None = None
    differences: list[str] = field(default_factory=list)
    usage: str | None = None
    status: str = "ok"  # ok | unavailable | unmatched | unconvertible
    reason: str | None = None
    amount: Decimal | None = None
    diff: Decimal | None = None
    diff_pct: Decimal | None = None


@dataclass
class Row:
    label: str
    where: str | None
    cells: dict[str, Cell]


@dataclass
class ComparisonOutcome:
    sides: list[Side]
    rows: list[Row]
    totals: dict[str, dict]
    snapshots: dict[str, dict]
    not_compared: list[str]

    @property
    def priced_rows(self) -> int:
        return sum(1 for r in self.rows if all(c.status == "ok" for c in r.cells.values()))

    def any_priced(self) -> bool:
        return any(c.status == "ok" and c.amount is not None
                   for r in self.rows for c in r.cells.values())


def _pct(diff: Decimal, base: Decimal) -> Decimal | None:
    return None if base == 0 else diff / base * 100


def price_comparison(sides: list[Side], rows: list[Row], duration: str) -> ComparisonOutcome:
    """Price every cell's line, then the differences against the first side (the reference),
    and the totals over the rows priced on every side."""
    snapshots: dict[str, dict] = {}
    for side in sides:
        if not side.available:
            for row in rows:
                cell = row.cells.setdefault(side.id, Cell())
                cell.status, cell.reason, cell.line = "unavailable", side.reason, None
            continue
        lines = [row.cells[side.id].line for row in rows
                 if side.id in row.cells and row.cells[side.id].status == "ok"
                 and row.cells[side.id].line is not None]
        priced = price_lines(side.provider, lines, duration)
        if priced.error is not None:
            side.available, side.reason = False, priced.error
        if priced.snapshot is not None:
            snapshots[side.provider] = priced.snapshot
        for row in rows:
            cell = row.cells.setdefault(side.id, Cell(status="unmatched",
                                                      reason="not compared"))
            if cell.status != "ok" or cell.line is None:
                continue
            if priced.error is not None:
                cell.status, cell.reason = "unavailable", priced.error
            elif cell.line.key in priced.amounts:
                cell.amount = priced.amounts[cell.line.key]
            else:
                cell.status = "unavailable"
                cell.reason = priced.reasons.get(cell.line.key, "no price published")
    reference = sides[0].id
    for row in rows:
        ref = row.cells.get(reference)
        for side in sides[1:]:
            cell = row.cells.get(side.id)
            if (cell and ref and cell.status == "ok" and ref.status == "ok"
                    and cell.amount is not None and ref.amount is not None):
                cell.diff = cell.amount - ref.amount
                cell.diff_pct = _pct(cell.diff, ref.amount)
    complete = [r for r in rows if all(r.cells.get(s.id) and r.cells[s.id].status == "ok"
                                       for s in sides)]
    partial = len(complete) != len(rows)
    totals: dict[str, dict] = {}
    for side in sides:
        amount = (sum((r.cells[side.id].amount for r in complete), Decimal(0))
                  if complete else None)
        totals[side.id] = {"amount": amount, "partial": partial, "diff": None, "diff_pct": None}
    ref_total = totals[reference]["amount"]
    for side in sides[1:]:
        total = totals[side.id]
        if total["amount"] is not None and ref_total is not None:
            total["diff"] = total["amount"] - ref_total
            total["diff_pct"] = _pct(total["diff"], ref_total)
    not_compared = []
    for row in rows:
        if row in complete:
            continue
        why = sorted({f"{s.provider.upper()}: {row.cells[s.id].reason}" for s in sides
                      if row.cells.get(s.id) and row.cells[s.id].status != "ok"
                      and row.cells[s.id].reason})
        not_compared.append(f"{row.label} ({'; '.join(why)})" if why else row.label)
    return ComparisonOutcome(sides, rows, totals, snapshots, not_compared)


def describe_product(provider: str, region: str, service_code: str, sku: str) -> str | None:
    items, _units = _describe(provider, region, [(service_code, sku)], [])
    item = items.get((service_code, sku))
    return product_label(item) if item else None
