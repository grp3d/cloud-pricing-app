"""Cross-cloud translation (026-agent-cross-cloud-translation, research R1, R5–R7).

Every match is the app's, never the model's:

1. **Seeded**: a seed mapping (022's rules, `matching.mappings`) for the source's product key,
   resolved in the chosen target region by 022's SKU or the target's product key. Used as 022
   decided, whatever its label.
2. **Automatic**: otherwise 024's candidate finder. Exact and close candidates are used without
   asking; several qualifying ones are a choice (FR-008: best quality, then lowest engine price).
3. **Partial only**: offered to the user; used only if they pick one in a later message (R7).
4. Otherwise **no equivalent**, with the reason.

The proposal is a new architecture with the original's collections, nesting and connectors
(`build_draft`); both architectures are priced whole by the engine and the difference is taken
over the services priced on both sides (`mapping_rows`, `cost_difference`, R6).
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from src.agent.matching import mappings
from src.agent.matching.book import Candidate, MatchBook, SourceProduct
from src.agent.matching.candidates import find_candidates
from src.agent.matching.profiles import product_label, profile
from src.agent.matching.quality import LABELS, quality
from src.pricing_data.providers import keys

SEEDED, AUTOMATIC, CHOSEN = "seeded", "automatic", "chosen_by_user"
QUALIFYING = ("exact", "close")
PARTIAL_SHOWN = 3
_RANK = {label: rank for rank, label in enumerate(LABELS)}
_QUANTITY = Decimal("0.0001")


@dataclass
class TargetLine:
    service_code: str
    sku: str
    quantity: Decimal
    options: dict | None
    label: str
    unit: str | None
    price_types: tuple[str, ...] = ()


@dataclass
class Choice:
    ref: str
    origin: str  # seeded | automatic
    quality: str
    differences: list[str]
    lines: list[TargetLine]
    note: str | None = None
    usage_note: str | None = None

    @property
    def label(self) -> str:
        return " + ".join(dict.fromkeys(line.label for line in self.lines))


@dataclass
class SourceMatch:
    source: SourceProduct
    target_region: str
    status: str  # matched | choose | partial_only | no_equivalent | not_sold_in_region
    choices: list[Choice] = field(default_factory=list)
    default: Choice | None = None
    reason: str | None = None
    unpriceable: str | None = None  # the source can't be priced in the original (FR-014)


@dataclass
class Found:
    """One message's `find_translation` result: what `propose_translation` builds from."""

    architecture_id: uuid.UUID
    name: str
    source_provider: str
    target_provider: str
    regions: dict[str, tuple[str, bool]]  # source region -> (target region, guessed)
    matches: list[SourceMatch]
    choices: dict[str, tuple[SourceMatch, Choice]] = field(default_factory=dict)

    def match(self, ref: str) -> SourceMatch:
        from src.agent.operations import ToolError

        for m in self.matches:
            if m.source.ref == ref:
                return m
        raise ToolError(f"unknown service {ref!r}: use an S… reference from this message's "
                        "find_translation")


# --- Matching ------------------------------------------------------------------------------------


def _quantity(source: SourceProduct, factor: Decimal | None) -> Decimal:
    if factor is None:
        return source.usage_quantity
    return (Decimal(source.usage_quantity) * Decimal(factor)).quantize(_QUANTITY)


def _resolve(adapter, snapshot, region: str, key: str, service_code: str, sku: str | None):
    """(the target row in `region`, why there is none): 022's own SKU when it is sold there,
    else by product key."""
    if sku:
        found = adapter.describe(snapshot, [(service_code, sku)], region=region)
        item = found.get((service_code, sku))
        if item is not None and adapter.product_key(item) == key:
            return item, None
    return keys.resolve_key(adapter, snapshot, region, key, service_code, hint=sku)


def _region_options(adapter, snapshot, region: str, options: dict | None,
                    service_code: str) -> tuple[dict | None, bool]:
    """A mapping's options for `region`: a GCP machine's RAM key becomes that region's RAM SKU.
    (options, resolved)."""
    if not options:
        return None, True
    out = dict(options)
    ram_key = out.pop("ram_key", None)
    if ram_key:
        ram = keys.find_by_key(adapter, snapshot, region, ram_key, service_code)
        if ram is None:
            return None, False
        out["ram_sku"] = ram.sku
    return out, True


def _seed_choice(adapter, snapshot, source: SourceProduct, region: str,
                 alternative: mappings.MappingAlternative) -> Choice | str:
    """The alternative as a choice in `region`, or why it can't be used there (`keys.MISSING`
    or `keys.AMBIGUOUS`)."""
    lines: list[TargetLine] = []
    first = None
    for part in alternative.parts:
        item, why = _resolve(adapter, snapshot, region, part.target_key, part.service_code,
                             part.sku)
        if item is None:
            return why or keys.MISSING
        options, ok = _region_options(adapter, snapshot, region, part.options, part.service_code)
        if not ok:
            return keys.MISSING
        first = first or item
        lines.append(TargetLine(service_code=item.service_code, sku=item.sku,
                                quantity=_quantity(source, part.quantity_factor),
                                options=options, label=product_label(item), unit=item.unit,
                                price_types=tuple(item.price_types)))
    target = profile(first)
    machine = lines[0].options or {}
    if machine.get("kind") == "gcp_machine":
        target.specs.update(vcpu=int(machine["vcpus"]),
                            memory_gib=Decimal(str(machine["memory_gib"])))
    label, differences = quality(source.profile, target)
    factor = alternative.parts[0].quantity_factor
    usage_note = None if factor in (None, Decimal(1)) else \
        "usage converted to the target's unit, as 022's standard architectures do"
    return Choice(ref="", origin=SEEDED, quality=label if label != "no_equivalent" else "partial",
                  differences=differences, lines=lines, note=alternative.note,
                  usage_note=usage_note)


def _candidate_choice(candidate: Candidate) -> Choice:
    line = TargetLine(service_code=candidate.service_code, sku=candidate.sku,
                      quantity=candidate.quantity if candidate.quantity is not None
                      else Decimal(0), options=candidate.options, label=candidate.label,
                      unit=candidate.unit, price_types=tuple(candidate.price_types))
    return Choice(ref="", origin=AUTOMATIC, quality=candidate.quality or "partial",
                  differences=list(candidate.differences), lines=[line],
                  usage_note=candidate.usage_note or candidate.unconvertible)


def _cheapest_first(choices: list[Choice], provider: str, region: str) -> list[Choice]:
    """The best quality first, then the lowest engine price for the source's usage (FR-008);
    unpriced choices last. The order of equal ones is kept."""
    from src.agent.compare import PriceLine, price_lines

    best = min(_RANK[c.quality] for c in choices)
    top = [c for c in choices if _RANK[c.quality] == best]
    if len(top) < 2:
        return sorted(choices, key=lambda c: _RANK[c.quality])
    lines = [PriceLine(key=f"{n}:{i}", service_code=line.service_code, sku=line.sku,
                       region=region, quantity=line.quantity, pricing_term="on_demand",
                       purchase_option="not_applicable", options=line.options)
             for n, choice in enumerate(top) for i, line in enumerate(choice.lines)]
    priced = price_lines(provider, lines, "1_month").amounts

    def cost(n: int, choice: Choice) -> Decimal | None:
        amounts = [priced.get(f"{n}:{i}") for i in range(len(choice.lines))]
        return None if any(a is None for a in amounts) else sum(amounts, Decimal(0))

    ranked = sorted(enumerate(top), key=lambda nc: (cost(*nc) is None, cost(*nc) or 0, nc[0]))
    rest = sorted([c for c in choices if c not in top], key=lambda c: _RANK[c.quality])
    return [c for _n, c in ranked] + rest


async def match_sources(session, sources: list[SourceProduct], provider: str,
                        regions: dict[str, str], *, book: MatchBook | None = None
                        ) -> list[SourceMatch]:
    """Match every source on `provider`, each in the target region chosen for its region."""
    from src.pricing_data.active_snapshot import get_active_snapshot
    from src.pricing_data.providers.registry import get_provider

    adapter = get_provider(provider)
    snapshot = get_active_snapshot(provider)
    book = book or MatchBook()
    out: dict[int, SourceMatch] = {}
    automatic: list[tuple[int, SourceProduct]] = []
    for index, source in enumerate(sources):
        region = regions[source.region]
        alternatives = (await mappings.seed_mappings(session, source.provider,
                                                     source.product_key, provider)
                        if source.product_key else [])
        if not alternatives:
            automatic.append((index, source))
            continue
        usable = [a for a in alternatives if a.parts]
        choices = []
        misses: list[str] = []
        for alternative in usable:
            choice = await asyncio.to_thread(_seed_choice, adapter, snapshot, source, region,
                                             alternative)
            if isinstance(choice, Choice):
                choices.append(choice)
            else:
                misses.append(choice)
        if choices and not any(c.quality in QUALIFYING for c in choices):
            # A seeded partial match is offered like any other: used only if the user chooses it.
            out[index] = SourceMatch(source, region, "partial_only", choices[:PARTIAL_SHOWN])
        elif choices:
            ordered = await asyncio.to_thread(_cheapest_first, choices, provider, region) \
                if len(choices) > 1 else choices
            out[index] = SourceMatch(source, region, "choose" if len(ordered) > 1 else "matched",
                                     ordered, ordered[0])
        elif usable:
            name = {"gcp": "GCP", "azure": "Azure", "aws": "AWS"}.get(provider, provider)
            reason = (f"several {name} products match in {region} and nothing tells them "
                      "apart, so none is used" if keys.AMBIGUOUS in misses
                      else f"the matching {name} product isn't sold in {region}")
            out[index] = SourceMatch(source, region, "not_sold_in_region", reason=reason)
        else:
            out[index] = SourceMatch(source, region, "no_equivalent",
                                     reason=alternatives[0].omit_reason)
    for region in sorted({regions[s.region] for _i, s in automatic}):
        group = [(i, s) for i, s in automatic if regions[s.region] == region]
        for _i, s in group:
            if not s.ref:
                book.add_source(s)
        found = await find_candidates(book, [s for _i, s in group], {provider: region})
        for index, source in group:
            candidates = [_candidate_choice(c) for c in found.get(source.ref, {}).get(provider, [])]
            qualifying = [c for c in candidates if c.quality in QUALIFYING]
            if qualifying:
                ordered = await asyncio.to_thread(_cheapest_first, qualifying, provider, region) \
                    if len(qualifying) > 1 else qualifying
                out[index] = SourceMatch(source, region,
                                         "choose" if len(ordered) > 1 else "matched",
                                         ordered, ordered[0])
            elif candidates:
                out[index] = SourceMatch(source, region, "partial_only",
                                         candidates[:PARTIAL_SHOWN])
            else:
                out[index] = SourceMatch(
                    source, region, "no_equivalent",
                    reason=book.unmatched.get((source.ref, provider),
                                              "no product in the same category"))
    return [out[i] for i in range(len(sources))]


def name_choices(found: Found) -> None:
    """Give every choice its C… reference, in source order."""
    for match in found.matches:
        for choice in match.choices:
            choice.ref = f"C{len(found.choices) + 1}"
            found.choices[choice.ref] = (match, choice)


# --- Building the proposal -----------------------------------------------------------------------


@dataclass
class Built:
    draft: object  # src.agent.proposals.Draft
    used: dict[uuid.UUID, tuple[SourceMatch, Choice | None, str | None, list[uuid.UUID]]]
    # source selection id -> (match, the choice used or None, its origin, new service ids)
    term_notes: list[str]


def _line_term(provider: str, line: TargetLine, term: tuple[str, str]) -> tuple[str, str, bool]:
    """The term for one line: the chosen one where the product publishes it, else on demand.
    (pricing_term, purchase_option, fell back)."""
    if term[0] == "on_demand":
        return "on_demand", "not_applicable", False
    if provider in ("gcp", "azure") and line.price_types and term[0] not in line.price_types:
        return "on_demand", "not_applicable", True
    return term[0], term[1], False


def build_draft(detail, found: Found, picks: dict[str, Choice], name: str,
                term: tuple[str, str], clock) -> Built:
    """The new architecture: the original's collections (parents first), nesting and connectors,
    each service replaced by its match; services with no match are left out (FR-003, FR-006)."""
    from src.agent.proposals import Draft, ServiceSpec
    from src.services.architecture_state import ArchitectureState

    provider = found.target_provider
    draft = Draft(ArchitectureState(name=name, provider=provider), clock)
    by_selection = {m.source.selection_id: m for m in found.matches}
    used: dict = {}
    fallbacks: list[str] = []
    ids: dict = {}

    def add(selection_id, *, collection_id=None, connector_id=None, where: str) -> None:
        match = by_selection.get(selection_id)
        if match is None:
            return
        choice = picks.get(match.source.ref, match.default)
        origin = None
        new_ids: list[uuid.UUID] = []
        if choice is not None:
            origin = CHOSEN if choice.quality == "partial" and match.source.ref in picks \
                else choice.origin
            for line in choice.lines:
                pricing_term, option, fell_back = _line_term(provider, line, term)
                if fell_back:
                    fallbacks.append(line.label)
                new_ids.append(draft.add_service(
                    ServiceSpec(line.service_code, line.sku, pricing_term, option,
                                line.quantity, line.options, line.label),
                    collection_id=collection_id, connector_id=connector_id, group=None,
                    where=where))
        used[selection_id] = (match, choice, origin, new_ids)

    pending = list(detail.collections)
    while pending:  # parents before children, in the original's order otherwise
        progressed = False
        for collection in list(pending):
            parent = collection.parent_collection_id
            if parent is not None and parent not in ids:
                continue
            region = found.regions[collection.region][0]
            ids[collection.id] = draft.add_collection(
                f"new{len(ids) + 1}", type=collection.type, name=collection.name,
                region=region, parent_id=ids.get(parent), group=None)
            for selection in collection.sku_selections:
                add(selection.id, collection_id=ids[collection.id], where=collection.name)
            pending.remove(collection)
            progressed = True
        if not progressed:  # a parent outside the architecture: keep the rest top level
            for collection in pending:
                collection.parent_collection_id = None
    for connector in detail.connectors:
        if connector.from_collection_id not in ids or connector.to_collection_id not in ids:
            continue
        new = draft.add_connector(ids[connector.from_collection_id],
                                  ids[connector.to_collection_id],
                                  arrow_style=connector.arrow_style, group=None,
                                  label="Connector")
        if connector.arrow_reversed:
            draft.items[-1].after["arrow_reversed"] = True
        if connector.sku_selection is not None:
            add(connector.sku_selection.id, connector_id=new, where="a connector")
    notes = []
    if fallbacks:
        notes.append("on demand for " + ", ".join(dict.fromkeys(fallbacks)) +
                     ": the chosen term isn't published for them")
    return Built(draft, used, notes)


# --- The mapping table and the cost difference ---------------------------------------------------


def _amount(value) -> str | None:
    return None if value is None else f"{Decimal(value):f}"


def mapping_rows(built: Built, source_priced, target_priced) -> list[dict]:
    """One row per source service, in the original's order (data-model.md §3)."""
    from src.agent.operations_change import size_text

    rows = []
    for selection_id, (match, choice, origin, new_ids) in built.used.items():
        source = match.source
        source_amount = source_priced.by_service.get(selection_id)
        unpriced_source = source_priced.unpriceable.get(selection_id)
        row = {
            "where": source.where or "",
            "source": {"label": source.label, "region": source.region,
                       "quantity": _amount(source.usage_quantity), "unit": source.unit,
                       "amount": _amount(source_amount)},
            "status": match.status if choice is None else "matched",
            "match": None, "quality": None, "origin": None, "differences": [],
            "reason": match.reason, "assumptions": [],
            "alternatives": max(len(match.choices) - 1, 0) if match.status == "choose" else 0,
        }
        if choice is None and match.status == "partial_only":
            row["reason"] = "only partial matches: used only if you choose one"
        if choice is not None:
            amounts = [target_priced.by_service.get(i) for i in new_ids]
            missing = [target_priced.unpriceable.get(i) for i in new_ids
                       if i in target_priced.unpriceable]
            first = choice.lines[0]
            row["match"] = {"label": choice.label, "region": match.target_region,
                            "quantity": _amount(first.quantity), "unit": first.unit,
                            "size": size_text(first.options),
                            "amount": None if missing or any(a is None for a in amounts)
                            else _amount(sum(amounts, Decimal(0)))}
            row["quality"], row["origin"] = choice.quality, origin
            row["differences"] = list(choice.differences)
            row["assumptions"] = [n for n in (choice.note, choice.usage_note) if n]
            if missing:
                row["status"], row["reason"] = "unpriceable", missing[0]
        if unpriced_source:
            row["status"] = "unpriceable"
            row["reason"] = f"can't be priced in the original: {unpriced_source}"
        rows.append(row)
    return rows


TOP_DRIVERS = 3


def _compared(row: dict) -> bool:
    return (row["status"] == "matched" and row["source"]["amount"] is not None
            and row["match"] is not None and row["match"]["amount"] is not None)


def cost_difference(rows: list[dict], source_priced, target_priced, duration: str) -> dict:
    """Both totals, and the difference over the rows priced on both sides (R6)."""
    compared = [r for r in rows if _compared(r)]
    original = sum((Decimal(r["source"]["amount"]) for r in compared), Decimal(0))
    translated = sum((Decimal(r["match"]["amount"]) for r in compared), Decimal(0))
    diff = translated - original
    pct = None if original == 0 else diff / original * 100
    left_out = [f"{r['source']['label']} in {r['where']}: {r['reason'] or r['status']}"
                for r in rows if not _compared(r)]
    drivers = sorted(compared, key=lambda r: (-abs(Decimal(r["match"]["amount"])
                                                   - Decimal(r["source"]["amount"])),
                                              r["where"], r["source"]["label"]))[:TOP_DRIVERS]
    not_exact = [f"{r['source']['label']} → {r['match']['label']}: {r['quality']}"
                 + (", chosen by you" if r["origin"] == CHOSEN else "")
                 for r in rows if r["match"] is not None and r["quality"] != "exact"]
    snapshots = {source_priced.snapshot["provider"]: source_priced.snapshot["date"],
                 target_priced.snapshot["provider"]: target_priced.snapshot["date"]}
    return {
        "duration": duration,
        "original_total": {"amount": _amount(source_priced.total),
                           "partial": bool(source_priced.unpriceable)},
        "translation_total": {"amount": _amount(target_priced.total),
                              "partial": bool(left_out) or bool(target_priced.unpriceable)},
        "compared": {"original": _amount(original) if compared else None,
                     "translation": _amount(translated) if compared else None,
                     "diff": _amount(diff) if compared else None,
                     "diff_pct": _amount(pct) if compared and pct is not None else None,
                     "rows": len(compared)},
        "left_out": left_out,
        "drivers": [{"where": r["where"], "label": r["source"]["label"],
                     "diff": _amount(Decimal(r["match"]["amount"])
                                     - Decimal(r["source"]["amount"]))} for r in drivers],
        "not_exact": not_exact,
        "snapshots": snapshots,
    }


def caveats(record: dict) -> list[str]:
    """Everything a cost answer must name (FR-015): left-out and unpriceable services, partial
    totals, matches that aren't exact (chosen partial ones named), guessed regions, the term."""
    out = list(record["summary"]["left_out"])
    out += record["summary"]["not_exact"]
    guessed = [f"{r['source']} → {r['target']}" for r in record["regions"] if r["guessed"]]
    if guessed:
        out.append("regions guessed: " + ", ".join(guessed))
    if record["term"].get("why"):
        out.append(f"pricing term {record['term']['used']}: {record['term']['why']}")
    if record["summary"]["translation_total"]["partial"]:
        out.append("the totals are partial: compare only the matched services")
    return out
