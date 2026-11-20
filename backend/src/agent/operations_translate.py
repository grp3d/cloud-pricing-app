"""Translation operations (026, contracts/agent-operations.md, research R7–R9).

- `find_translation`: match every service of an architecture on another provider (the app's
  matches only: `src.agent.translation`) and say what still needs the user.
- `propose_translation`: the new architecture as a pending proposal, with its mapping table and
  cost difference.
- `describe_translation`: a translation's figures and caveats again, for a later question.

The model sends references only (M…/I… architectures, S… services, C… choices), never ids or
SKUs (Principle VII).
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy import select

from src.agent import proposals, translation
from src.agent.compare import architecture_sources, term_label, term_option
from src.agent.matching.regions import resolve_region
from src.agent.operations import OperationContext, OperationResult, ToolError, registry
from src.agent.operations_compare import _available

DIRECTIONS = {("aws", "gcp"), ("aws", "azure")}
MAX_ITEMS = 100
PROVIDER_NAMES = {"aws": "AWS", "gcp": "GCP", "azure": "Azure"}
CANT_YET = ("I can translate from AWS to GCP or to Azure, one target at a time. Other "
            "directions aren't available yet.")


# --- Loading the source --------------------------------------------------------------------------


async def _source(ctx: OperationContext, ref: str | None):
    """(ORM architecture, detail) for an M… (own), I… (public) reference, or the open one."""
    from src.agent.operations import _open_architecture
    from src.agent.operations_change import _importable
    from src.models.schemas import ArchitectureDetailOut
    from src.services.architecture_service import attach_units_to_architecture

    if ref is None:
        if ctx.open_architecture_id is None:
            raise ToolError("No architecture is named and none is open: ask which one to "
                            "translate.")
        return await _open_architecture(ctx)
    row = ctx.rows.get(ref)
    if row is None or row[0] not in ("architecture", "importable"):
        raise ToolError(f"unknown architecture {ref!r}: use an M… reference from "
                        "list_my_architectures or an I… from list_importable_architectures in "
                        "this message")
    if row[0] == "architecture":
        previous = ctx.open_architecture_id
        ctx.open_architecture_id = row[1]
        try:
            return await _open_architecture(ctx)
        finally:
            ctx.open_architecture_id = previous
    architecture = await _importable(ctx, row[1])
    if architecture is None:
        raise ToolError("That architecture can't be translated now.")
    detail = ArchitectureDetailOut.model_validate(architecture)
    attach_units_to_architecture(detail, architecture)
    return architecture, detail


def _items(detail) -> int:
    return (len(detail.collections) + len(detail.connectors)
            + sum(len(c.sku_selections) for c in detail.collections)
            + sum(1 for k in detail.connectors if k.sku_selection is not None))


def _regions(provider: str, source_provider: str, detail, wanted: dict[str, str]
             ) -> dict[str, tuple[str, bool]]:
    available = _available(provider)
    out: dict[str, tuple[str, bool]] = {}
    for region in sorted({c.region for c in detail.collections}):
        choice = resolve_region(provider, wanted.get(region), available=available,
                                near=(source_provider, region))
        if not choice.available:
            guess = resolve_region(provider, None, available=available,
                                   near=(source_provider, region))
            hint = (f" The nearest with pricing data is {guess.region} (a guess: ask the user "
                    "to confirm)." if guess.available else "")
            raise ToolError(f"{choice.reason}.{hint}")
        out[region] = (choice.region, choice.guessed)
    return out


def _term(provider: str, term: str | None) -> tuple[str, str]:
    if term is None or term == "on_demand":
        return "on_demand", "not_applicable"
    return term_option(provider, term, None)


def _term_record(provider: str, term: tuple[str, str], sources) -> dict:
    used = term_label(*term) if term[0] != "on_demand" else "on demand"
    reserved = sorted({term_label(s.pricing_term, s.purchase_option) for s in sources
                       if s.pricing_term != "on_demand"})
    why = None
    if reserved and term[0] == "on_demand":
        why = (f"the original uses {', '.join(reserved)}; terms don't carry over between "
               "providers, so the target is priced on demand unless you choose one of "
               f"{PROVIDER_NAMES[provider]}'s terms")
    return {"used": used, "why": why}


# --- find_translation ----------------------------------------------------------------------------


class FindTranslationInput(BaseModel):
    architecture: str | None = Field(default=None, description="An M… (the user's own) or I… "
                                     "(public) reference; omit for the open architecture.")
    provider: str = Field(description="The target provider: gcp or azure.")
    regions: dict[str, str] = Field(default_factory=dict, description="Source region → target "
                                    "region the user chose; missing ones are guessed.")
    term: str | None = Field(default=None, description="A target pricing term the user chose; "
                             "default on demand.")


def _choice_out(choice: translation.Choice) -> dict:
    out = {"ref": choice.ref, "label": choice.label, "quality": choice.quality,
           "origin": choice.origin}
    if choice.differences:
        out["differences"] = choice.differences
    if choice.note:
        out["note"] = choice.note
    return out


def _usage(source) -> str:
    from src.agent.matching.usage import plain_number, quantity_unit

    unit = quantity_unit(source.unit, source.provider) or source.unit or ""
    return f"{plain_number(source.usage_quantity)} {unit}".strip()


@registry.operation(
    "find_translation",
    "Find the equivalent of every service of an architecture on another provider (AWS to GCP "
    "or Azure). Call it first for any request to translate, move or rebuild an architecture on "
    "another cloud. Returns services S… with the app's matches C… and what needs the user.",
    FindTranslationInput,
)
async def find_translation(ctx: OperationContext, args: FindTranslationInput
                           ) -> OperationResult:
    from src.services.architecture_state import read_state

    target = args.provider.lower()
    architecture, detail = await _source(ctx, args.architecture)
    if detail.provider == target:
        raise ToolError(f"{detail.name} is already on {PROVIDER_NAMES[target]}: there's "
                        "nothing to translate.")
    if (detail.provider, target) not in DIRECTIONS:
        raise ToolError(CANT_YET)
    size = _items(detail)
    if size > MAX_ITEMS:
        raise ToolError(f"{detail.name} has {size} items (collections, services and "
                        f"connectors); a translation holds at most {MAX_ITEMS}.")
    regions = _regions(target, detail.provider, detail, args.regions)
    term = _term(target, args.term)
    sources = await architecture_sources(detail)
    for source in sources:
        ctx.matches.add_source(source)
    matches = await translation.match_sources(
        ctx.session, sources, target, {r: t for r, (t, _g) in regions.items()},
        book=ctx.matches)
    priced = proposals.price_state(await read_state(ctx.session, detail.id), "1_month")
    for match in matches:
        reason = priced.unpriceable.get(match.source.selection_id)
        if reason:
            match.unpriceable = reason
    found = translation.Found(architecture_id=detail.id, name=detail.name,
                              source_provider=detail.provider, target_provider=target,
                              regions=regions, matches=matches)
    translation.name_choices(found)
    ctx.translation = found
    services = []
    for match in matches:
        entry: dict = {"ref": match.source.ref, "where": match.source.where,
                       "label": match.source.label, "usage": _usage(match.source),
                       "status": match.status,
                       "default": match.default.ref if match.default else None,
                       "candidates": [_choice_out(c) for c in match.choices]}
        if match.reason:
            entry["reason"] = match.reason
        if match.unpriceable:
            entry["unpriceable_in_original"] = match.unpriceable
        services.append(entry)
    needs = [f"regions guessed: {', '.join(f'{s} → {t}' for s, (t, g) in regions.items() if g)}"]
    needs = needs if any(g for _t, g in regions.values()) else []
    needs += [f"{m.source.ref} has {len(m.choices)} valid equivalents" for m in matches
              if m.status == "choose"]
    needs += [f"{m.source.ref} has only partial matches: left out unless the user chooses one; "
              "offer them" for m in matches if m.status == "partial_only"]
    term_record = _term_record(target, term, sources)
    offers = [{"key": m.source.product_key, "where": m.source.where} for m in matches
              if m.status == "partial_only"]
    return OperationResult(
        data={"source": {"name": detail.name, "provider": detail.provider, "items": size},
              "target_provider": target,
              "regions": [{"source": s, "target": t, "guessed": g}
                          for s, (t, g) in regions.items()],
              "term": term_record, "services": services, "needs_user": needs,
              "next": "Ask only for what needs the user (at most three questions, offering "
                      "the defaults), then call propose_translation."},
        summary={"architecture": detail.name, "target": target, "sources": len(matches),
                 "statuses": {s: sum(1 for m in matches if m.status == s)
                              for s in sorted({m.status for m in matches})},
                 "regions": {s: t for s, (t, _g) in regions.items()},
                 "partial_offers": offers},
    )


# --- propose_translation -------------------------------------------------------------------------


class Pick(BaseModel):
    source: str = Field(description="An S… reference.")
    candidate: str = Field(description="One of that service's C… references.")


class ProposeTranslationInput(BaseModel):
    architecture: str | None = None
    provider: str
    regions: dict[str, str] = Field(default_factory=dict)
    term: str | None = None
    picks: list[Pick] = Field(default_factory=list, max_length=100)
    name: str | None = Field(default=None, max_length=200, description=(
        "Only a name the user asked for. Leave it out to keep the original's name: the "
        "provider already shows where it's listed, so don't add it."))


async def _offered_before(ctx: OperationContext, match: translation.SourceMatch) -> bool:
    """Whether an earlier message of this session offered this source's partial matches (R7)."""
    from src.models.orm import AgentOperation

    rows = (await ctx.session.execute(select(AgentOperation).where(
        AgentOperation.session_id == ctx.agent_session.id,
        AgentOperation.name == "find_translation",
        AgentOperation.outcome == "ok",
        AgentOperation.message_id != ctx.message.id))).scalars()
    wanted = {"key": match.source.product_key, "where": match.source.where}
    return any(wanted in ((row.summary or {}).get("partial_offers") or []) for row in rows)


def _snapshot(record: dict) -> dict:
    """{provider: {date, revision}} behind a translation's figures."""
    return record.get("snapshot_meta") or {
        p: {"date": d, "revision": 0} for p, d in record["summary"]["snapshots"].items()}


def _figures(ctx: OperationContext, record: dict) -> dict:
    summary = record["summary"]
    duration = summary["duration"]
    snapshot = _snapshot(record)

    def ref(amount, label, kind="money"):
        return None if amount is None else ctx.figures.add(
            Decimal(amount), label, duration=duration, snapshot=snapshot, kind=kind)

    compared = summary["compared"]
    return {
        "original_total": ref(summary["original_total"]["amount"], "original total"),
        "translation_total": ref(summary["translation_total"]["amount"], "translation total"),
        "partial": summary["translation_total"]["partial"] or summary["original_total"][
            "partial"],
        "compared_services": compared["rows"],
        "compared_original": ref(compared["original"], "original, matched services"),
        "compared_translation": ref(compared["translation"], "translation, matched services"),
        "compared_diff": ref(compared["diff"], "difference on matched services"),
        "compared_pct": ref(compared["diff_pct"], "difference %", "percent"),
        "drivers": [{"service": d["label"], "where": d["where"],
                     "diff": ref(d["diff"], d["label"])} for d in summary["drivers"]],
        "duration": duration, "snapshot_dates": summary["snapshots"],
    }


def _rows_count(record: dict) -> dict:
    rows = record["rows"]
    return {"matched": sum(1 for r in rows if r["status"] == "matched"),
            "left_out": sum(1 for r in rows if r["match"] is None),
            "chosen_by_user": sum(1 for r in rows if r["origin"] == translation.CHOSEN)}


@registry.operation(
    "propose_translation",
    "Propose the translation as a new architecture on the target provider, with the mapping "
    "table and the cost difference. The user sees it beside you and decides; nothing is saved "
    "until they accept. Picks choose among a service's candidates, or take a partial match the "
    "user chose after you offered it.",
    ProposeTranslationInput,
)
async def propose_translation(ctx: OperationContext, args: ProposeTranslationInput
                              ) -> OperationResult:
    from src.agent.matching import mappings
    from src.services import architecture_rules as rules
    from src.services.architecture_state import fingerprint, read_state

    found: translation.Found | None = ctx.translation
    target = args.provider.lower()
    if found is None or found.target_provider != target:
        raise ToolError("Call find_translation for this architecture and provider in this "
                        "message first.")
    architecture, detail = await _source(ctx, args.architecture)
    if detail.id != found.architecture_id:
        raise ToolError("Call find_translation for this architecture in this message first.")
    regions = _regions(target, detail.provider, detail, args.regions)
    if {s: t for s, (t, _g) in regions.items()} != {
            s: t for s, (t, _g) in found.regions.items()}:
        raise ToolError("The regions differ from find_translation's: call it again with these "
                        "regions.")
    term = _term(target, args.term)
    picks: dict[str, translation.Choice] = {}
    for pick in args.picks:
        match = found.match(pick.source)
        entry = found.choices.get(pick.candidate)
        if entry is None or entry[0] is not match:
            raise ToolError(f"{pick.candidate} isn't one of {pick.source}'s candidates; pick one "
                            "find_translation returned for it.")
        choice = entry[1]
        if match.status == "partial_only":
            if not await _offered_before(ctx, match):
                raise ToolError(f"{pick.source} has only partial matches. Ask the user whether "
                                "to use one first; it can be used only if they choose it.")
        picks[pick.source] = choice
    name = args.name or detail.name
    built = translation.build_draft(detail, found, picks, name, term,
                                    await proposals.db_clock(ctx.session))
    draft = built.draft
    target_state = draft.state
    try:
        proposals.validate(None, target_state, draft.items)
    except rules.RuleError as error:
        where = f"{error.ref}: " if error.ref else ""
        raise ToolError(f"{where}{error.message}") from error
    source_state = await read_state(ctx.session, detail.id)
    duration = "1_month"
    source_priced = proposals.price_state(source_state, duration)
    target_priced = proposals.price_state(target_state, duration)
    rows = translation.mapping_rows(built, source_priced, target_priced)
    record = {
        "source_architecture_id": str(detail.id), "source_name": detail.name,
        "source_provider": detail.provider, "target_provider": target,
        "regions": [{"source": s, "target": t, "guessed": g}
                    for s, (t, g) in regions.items()],
        "term": _term_record(target, term, [m.source for m in found.matches]),
        "source_fingerprint": fingerprint(source_state),
        "mapping_version": {"seed": await mappings.seed_version(ctx.session),
                            "snapshots": {source_priced.snapshot["provider"]:
                                          source_priced.snapshot["date"],
                                          target_priced.snapshot["provider"]:
                                          target_priced.snapshot["date"]}},
        "snapshot_meta": {p["provider"]: {"date": p["date"], "revision": p["revision"]}
                          for p in (source_priced.snapshot, target_priced.snapshot)},
        "rows": rows,
        "summary": translation.cost_difference(rows, source_priced, target_priced, duration),
        "choices": [{"source_key": m.source.product_key, "where": m.source.where,
                     "picked": picks[m.source.ref].label,
                     "chosen_by_user": picks[m.source.ref].quality == "partial"}
                    for m in found.matches if m.source.ref in picks],
    }
    if built.term_notes:
        record["term"]["why"] = "; ".join(filter(None, [record["term"]["why"],
                                                        *built.term_notes]))
    cost = proposals.cost_summary(None, draft.items, target_state, duration)
    title = f"{detail.name} → {PROVIDER_NAMES[target]}"
    proposal = await proposals.create_proposal(
        ctx.session, ctx.agent_session, ctx.message, kind="translate", title=title, base=None,
        target=target_state, items=draft.items, cost=cost, assumptions=[],
        architecture_id=None, source_architecture_id=detail.id, translation=record)
    ctx.proposals.append(proposal)
    data = {
        "proposal": f"Q{proposal.seq}",
        "status": "pending: shown to the user beside you; nothing is saved until they accept",
        "name": name, "rows": _rows_count(record), "cost": _figures(ctx, record),
        "caveats": translation.caveats(record),
    }
    summary = {"proposal": str(proposal.id), "kind": "translate", "source": detail.name,
               "target": target, "rows": _rows_count(record),
               "origins": {o: sum(1 for r in rows if r["origin"] == o)
                           for o in (translation.SEEDED, translation.AUTOMATIC,
                                     translation.CHOSEN)},
               "mapping_version": record["mapping_version"]}
    return OperationResult(data=data, summary=summary,
                           snapshot=_snapshot(record))


# --- describe_translation ------------------------------------------------------------------------


class DescribeTranslationInput(BaseModel):
    proposal: str | None = Field(default=None, description="A Q… reference; omit for the "
                                 "pending translation, else the latest one.")


@registry.operation(
    "describe_translation",
    "A translation's totals, difference and caveats as figures, to answer a later question "
    "about it (for example which provider is cheaper). Read-only.",
    DescribeTranslationInput,
)
async def describe_translation(ctx: OperationContext, args: DescribeTranslationInput
                               ) -> OperationResult:
    found = [p for p in await proposals.session_proposals(ctx.session, ctx.agent_session)
             if p.kind == "translate"]
    if not found:
        raise ToolError("There's no translation in this conversation yet.")
    if args.proposal:
        chosen = next((p for p in found if f"Q{p.seq}" == args.proposal), None)
        if chosen is None:
            raise ToolError(f"unknown translation {args.proposal!r}")
    else:
        pending = [p for p in found if p.status == "pending"]
        chosen = (pending or found)[-1]
    stale = await proposals.translation_stale(ctx.session, chosen)
    record = chosen.translation
    data = {"proposal": f"Q{chosen.seq}", "status": chosen.status, "stale": stale,
            "source": record["source_name"], "target_provider": record["target_provider"],
            "rows": _rows_count(record), "cost": _figures(ctx, record),
            "caveats": translation.caveats(record)}
    if stale:
        data["note"] = ("The original or the pricing data changed since this translation; "
                        "offer to translate it again.")
    return OperationResult(data=data, summary={"proposal": str(chosen.id), "stale": stale},
                           snapshot=_snapshot(record))

