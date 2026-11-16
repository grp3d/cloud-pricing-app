"""The evaluation runner (023, research R8, FR-025, FR-025a, clarification 3).

Each case (`cases/*.yaml`) sets up an architecture, sends its messages through the real agent
loop with a given model client, and applies fixed checks: the operations that must run (or
that none may), the figures that must equal the pricing engine's to the cent, phrases that must
or must not appear, and whether the request must be declined. No model grades the answers.
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.agent import proposals
from src.agent.figures import format_usd
from src.agent.loop import LoopContext, answer
from src.agent.settings_service import EffectiveAgentSettings
from src.models.orm import (
    AgentMessage,
    AgentResult,
    AgentSession,
    Architecture,
    Collection,
    DataConnector,
    SKUSelection,
    User,
)
from src.models.schemas import (
    AgentOpenArchitectureEvent,
    AgentOperationEvent,
    AgentTextEvent,
    CalculationDuration,
    ProposalAcceptBody,
)
from src.services.architecture_state import ArchitectureState, fingerprint, read_state
from src.services.price_calculation import calculate_architecture_price
from tests.helpers.agent import build_standard

CASES_DIR = Path(__file__).parent / "cases"
DECLINE_WORDS = ("can't", "cannot", "can not", "unable", "not able", "won't")


def load_cases() -> list[dict]:
    return [yaml.safe_load(p.read_text()) for p in sorted(CASES_DIR.glob("gc-*.yaml"))]


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class CaseResult:
    id: str
    title: str
    text: str = ""
    operations: list[str] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.error is None and all(c.passed for c in self.checks)


def _effective(provider: str) -> EffectiveAgentSettings:
    return EffectiveAgentSettings(
        enabled=True, provider=provider, model="eval", base_url="http://localhost:11434",
        timeout_seconds=120, global_monthly_cap_usd=Decimal("1000"),
        default_user_monthly_inputs=1000, price_per_input_token_usd=Decimal(0),
        price_per_output_token_usd=Decimal(0),
    )


async def _owner(db, username: str) -> User:
    if username == "Admin":
        return (await db.execute(select(User).where(User.is_default_admin))).scalar_one()
    user = User(id=uuid.uuid4(), username=f"{username}")
    db.add(user)
    await db.flush()
    return user


async def _setup(db, case: dict) -> tuple[User, Architecture | None]:
    user = User(id=uuid.uuid4(), username=f"eval-{uuid.uuid4().hex[:6]}",
                agent_enabled_for_user=True)
    db.add(user)
    await db.flush()
    for other in case.get("others") or []:
        owner = await _owner(db, other["owner"])
        for spec in other["architectures"]:
            await build_standard(db, owner, spec["provider"], spec["name"],
                                 rename=spec.get("rename"), public=spec.get("public", False))
    arch_spec = case.get("architecture")
    if not arch_spec:
        await db.commit()
        return user, None
    architecture = await build_standard(db, user, arch_spec["provider"], arch_spec["name"])
    collections = (await db.execute(
        select(Collection).where(Collection.architecture_id == architecture.id)
        .order_by(Collection.created_at))).scalars().all()
    if arch_spec.get("rename_first_collection"):
        collections[0].name = arch_spec["rename_first_collection"]
    if arch_spec.get("add_unpriceable"):
        bad = arch_spec["add_unpriceable"]
        db.add(SKUSelection(collection_id=collections[0].id, service_code=bad["service_code"],
                            sku=bad["sku"], pricing_term="on_demand",
                            purchase_option="not_applicable", usage_quantity=Decimal(1)))
    await db.commit()
    return user, architecture


async def _engine(db, architecture: Architecture, duration: str):
    loaded = (await db.execute(
        select(Architecture).where(Architecture.id == architecture.id).options(
            selectinload(Architecture.collections.and_(Collection.deleted_at.is_(None)))
            .selectinload(Collection.sku_selections),
            selectinload(Architecture.connectors.and_(DataConnector.deleted_at.is_(None)))
            .selectinload(DataConnector.sku_selection),
        ).execution_options(populate_existing=True)
    )).scalar_one()
    return calculate_architecture_price(loaded, duration=CalculationDuration(duration))


async def _figure_checks(db, architecture, specs) -> list[Check]:
    checks = []
    for spec in specs or []:
        result = await _engine(db, architecture, spec["duration"])
        if spec["of"] == "total":
            amount = result.total_price
        else:  # top_service: the largest single service
            per: dict = {}
            for item in result.line_items:
                if item.priceable and item.price is not None:
                    per[item.sku_selection_id] = per.get(item.sku_selection_id, 0) + item.price
            amount = max(per.values())
        checks.append(Check(f"figure {spec['of']} {spec['duration']}", True,
                            format_usd(amount)))
    return checks


def _engine_cell(provider: str, priced: dict, duration: str):
    from src.agent.compare import PriceLine, price_lines

    line = PriceLine("x", priced["service_code"], priced["sku"], priced["region"],
                     Decimal(priced["quantity"]), priced["pricing_term"],
                     priced["purchase_option"], priced.get("options"))
    return price_lines(provider, [line], duration).amounts.get("x")


def _result_checks(expect: dict, results: list, text: str) -> list[Check]:
    """024 checks on the comparison results the conversation made."""
    checks: list[Check] = []
    if expect.get("no_result"):
        checks.append(Check("makes no result", not results, f"{len(results)} results"))
    if expect.get("result_rows"):
        checks.append(Check("makes a result", bool(results)))
        for result in results:
            providers = {s["id"]: s["provider"] for s in result.sides}
            duration = result.basis["duration"]
            for row in result.rows:
                for side_id, cell in row["cells"].items():
                    if cell["status"] != "ok":
                        continue
                    engine = _engine_cell(providers[side_id], cell["priced"], duration)
                    checks.append(Check(f"row {row['label']} {side_id} is the engine's",
                                        engine is not None and Decimal(cell["amount"]) == engine,
                                        f"{cell['amount']} vs {engine}"))
    if expect.get("providers"):
        sides = [s["provider"] for s in results[-1].sides] if results else []
        checks.append(Check(f"compares {expect['providers']}", sides == expect["providers"],
                            f"{sides}"))
    if "partial_total" in expect:
        partial = bool(results) and any(t.get("partial") for t in results[-1].totals.values())
        checks.append(Check("total labelled partial" if expect["partial_total"]
                            else "total complete", partial == expect["partial_total"]))
    for label, wanted in (expect.get("qualities") or {}).items():
        found = None
        for result in results:
            for row in result.rows:
                if label.lower() in row["label"].lower():
                    for side_id, quality in wanted.items():
                        cell = row["cells"].get(side_id, {})
                        found = cell.get("shown_quality") or cell.get("quality")
                        checks.append(Check(f"{label} on {side_id} is {quality}",
                                            found == quality, f"was {found}"))
        if found is None:
            checks.append(Check(f"{label} compared", False, "no such row"))
    if expect.get("unavailable"):
        side = expect["unavailable"]
        cells = [r["cells"].get(side, {}) for res in results for r in res.rows]
        checks.append(Check(f"{side} unavailable with no figure",
                            all(c.get("status") != "ok" and c.get("amount") is None
                                for c in cells) if cells else True))
    if expect.get("max_questions") is not None:
        asked = text.count("?")
        checks.append(Check(f"at most {expect['max_questions']} questions",
                            asked <= expect["max_questions"], f"{asked} asked"))
    return checks


async def run_case(db, case: dict, client) -> CaseResult:
    out = CaseResult(case["id"], case["title"])
    user, architecture = await _setup(db, case)
    now = datetime.now(UTC)
    agent_session = AgentSession(user_id=user.id, started_at=now,
                                 closes_at=now + timedelta(days=3))
    db.add(agent_session)
    await db.commit()
    open_id = architecture.id if architecture else None
    start_state = await read_state(db, open_id) if open_id else None
    for seq, content in enumerate(case["messages"], start=1):
        message = AgentMessage(session_id=agent_session.id, seq=seq * 2 - 1, role="user",
                               content=content, status="accepted", architecture_id=open_id)
        db.add(message)
        await db.commit()
        context = LoopContext(session=db, user=user, agent_session=agent_session,
                              user_message=message, client=client,
                              effective=_effective(client.provider))
        async for event in answer(context):
            if isinstance(event, AgentTextEvent):
                out.text += event.delta
            elif isinstance(event, AgentOperationEvent):
                if event.outcome == "ok":
                    out.operations.append(event.name)
            elif isinstance(event, AgentOpenArchitectureEvent):
                open_id = event.architecture_id  # 025: the browser opens it
            elif event.event == "error":
                out.error = f"{event.kind}: {event.message}"
        # A failed answer rolls the session back, which expires these; reload them so the
        # checks below report the error instead of failing on a lazy load.
        await db.refresh(agent_session)
        if architecture is not None:
            await db.refresh(architecture)
        if out.error:
            break
    expect = case.get("expect") or {}
    lower = out.text.lower()
    for name in expect.get("operations") or []:
        out.checks.append(Check(f"operation {name}", name in out.operations,
                                f"ran {out.operations}"))
    if expect.get("no_operations"):
        out.checks.append(Check("runs no operation", not out.operations,
                                f"ran {out.operations}"))
    for check in await _figure_checks(db, architecture, expect.get("figures")):
        check.passed = check.detail in out.text
        check.detail = f"expected {check.detail}"
        out.checks.append(check)
    for phrase in expect.get("contains") or []:
        # A list is one requirement worded several ways: any of them passes.
        options = phrase if isinstance(phrase, list) else [phrase]
        out.checks.append(Check(f"contains {phrase!r}",
                                any(o.lower() in lower for o in options)))
    for phrase in expect.get("not_contains") or []:
        out.checks.append(Check(f"does not contain {phrase!r}", phrase.lower() not in lower))
    if expect.get("order"):
        positions = [lower.find(p.lower()) for p in expect["order"]]
        out.checks.append(Check(f"order {expect['order']}",
                                -1 not in positions and positions == sorted(positions)))
    results = (await db.execute(select(AgentResult).where(
        AgentResult.session_id == agent_session.id).order_by(AgentResult.seq))).scalars().all()
    out.checks.extend(_result_checks(expect, results, out.text))
    # 025: proposals, nothing saved before accept, and the user's actions afterwards.
    found = await proposals.session_proposals(db, agent_session)
    if architecture is not None and start_state is not None and (
            expect.get("proposal") or case.get("actions")):
        now_state = await read_state(db, architecture.id)
        out.checks.append(Check("nothing saved before accept",
                                now_state is not None
                                and fingerprint(now_state) == fingerprint(start_state)))
    out.checks.extend(proposal_checks(expect, found))
    if case.get("actions") and not out.error:
        out.checks.extend(await run_actions(db, user, agent_session, found, case["actions"]))
    if "refused" in expect:
        declined = any(w in lower for w in DECLINE_WORDS)
        out.checks.append(Check("declines" if expect["refused"] else "doesn't decline",
                                declined == expect["refused"]))
    return out



# --- 025: proposals (research R10) ---------------------------------------------------------------


def _services_check(proposal, op: str, spec: dict) -> Check:
    """Exactly these services added (or changed) in `spec["region"]`, by service code, and none
    elsewhere, whichever collection the model put them in (025, GC-20, GC-23 to GC-25)."""
    target = ArchitectureState.model_validate(proposal.target_state)
    regions = {c.id: c.region for c in target.collections}
    by_id = {str(s.id): s for s in target.services}
    ids = [i["id"] for i in proposal.items if i["op"] == op and i["target"] == "service"]
    found: Counter = Counter()
    elsewhere = 0
    for service_id in ids:
        service = by_id.get(service_id)
        if service and regions.get(service.collection_id) == spec["region"]:
            found[service.service_code] += 1
        else:
            elsewhere += 1
    wanted = Counter(spec["codes"])
    verb = "adds" if op == "add" else "changes"
    return Check(f"{verb} {dict(wanted)} in {spec['region']}",
                 found == wanted and elsewhere == 0,
                 f"{dict(found)}, {elsewhere} elsewhere")


def proposal_checks(expect: dict, found: list) -> list[Check]:
    """Checks on the session's latest proposal: its kind and items, figures equal to the
    engine's for its base and target states, and contributions that add up."""
    checks: list[Check] = []
    if expect.get("no_proposal"):
        checks.append(Check("makes no proposal", not found, f"{len(found)} proposals"))
    wanted = expect.get("proposal")
    if not wanted:
        return checks
    checks.append(Check("makes a proposal", bool(found)))
    if not found:
        return checks
    latest = found[-1]
    if "kind" in wanted:
        checks.append(Check(f"proposal is a {wanted['kind']}", latest.kind == wanted["kind"],
                            f"was {latest.kind}"))
    counts = {op: sum(1 for i in latest.items if i["op"] == op)
              for op in ("add", "change", "remove")}
    for op, least in (wanted.get("at_least") or {}).items():
        checks.append(Check(f"at least {least} {op}", counts[op] >= least, f"{counts[op]}"))
    for op in wanted.get("none_of") or []:
        checks.append(Check(f"no {op}", counts[op] == 0, f"{counts[op]}"))
    for key, op in (("adds_services", "add"), ("changes_services", "change")):
        if key in wanted:
            checks.append(_services_check(latest, op, wanted[key]))
    if "name" in wanted:
        name = latest.target_state.get("name")
        checks.append(Check(f"named {wanted['name']!r}", name == wanted["name"], f"{name!r}"))
    duration = latest.cost["duration"]
    after = proposals.price_state(ArchitectureState.model_validate(latest.target_state),
                                  duration).total
    checks.append(Check("after total is the engine's",
                        Decimal(latest.cost["after"]["total"]) == after,
                        f"{latest.cost['after']['total']} vs {after}"))
    rows = sum(Decimal(r["after"]) for r in latest.cost["by_service"] if r["after"] is not None)
    checks.append(Check("service rows add up to the total",
                        rows == Decimal(latest.cost["after"]["total"]),
                        f"{rows} vs {latest.cost['after']['total']}"))
    if latest.base_state is not None:
        before = proposals.price_state(ArchitectureState.model_validate(latest.base_state),
                                       duration).total
        checks.append(Check("before total is the engine's",
                            Decimal(latest.cost["before"]["total"]) == before,
                            f"{latest.cost['before']['total']} vs {before}"))
    if wanted.get("partial") is not None:
        partial = latest.cost["after"]["partial"]
        checks.append(Check("total labelled partial" if wanted["partial"] else "total complete",
                            partial == wanted["partial"]))
    if latest.cost.get("contributions"):
        total = sum(Decimal(c["difference"]) for c in latest.cost["contributions"])
        checks.append(Check("contributions add up",
                            total == Decimal(latest.cost["difference"]),
                            f"{total} vs {latest.cost['difference']}"))
    return checks


async def run_actions(db, user, agent_session, found: list, actions: list) -> list[Check]:
    """Play the user's decisions on the latest proposal (`accept`, `reject`, `undo`, `redo`,
    `manual_edit`, `undo_refused`), checking the saved architecture after each."""
    checks: list[Check] = []
    if not found:
        return [Check("a proposal to act on", False)]
    proposal = found[-1]
    base = (ArchitectureState.model_validate(proposal.base_state)
            if proposal.base_state is not None else None)
    target = ArchitectureState.model_validate(proposal.target_state)

    async def saved():
        return await read_state(db, proposal.architecture_id) if proposal.architecture_id else None

    def same(state, expected) -> bool:
        if expected is None:
            return state is None
        if state is None:
            return False
        if proposal.kind != "change":  # a new architecture: compare content, not ids
            return state.name == expected.name and len(state.services) == len(expected.services)
        return fingerprint(state) == fingerprint(expected)

    for action in actions:
        name = action if isinstance(action, str) else next(iter(action))
        try:
            if name == "accept":
                await proposals.accept(db, user, agent_session, proposal.id,
                                       ProposalAcceptBody(architecture_id=proposal.architecture_id))
                checks.append(Check("accept saves the proposal", same(await saved(), target)))
            elif name == "reject":
                await proposals.reject(db, user, agent_session, proposal.id)
                checks.append(Check("reject changes nothing",
                                    base is None or same(await saved(), base)))
            elif name == "undo":
                await proposals.undo(db, user, agent_session, proposal.id)
                checks.append(Check("undo restores the architecture", same(await saved(), base)))
            elif name == "undo_refused":
                try:
                    await proposals.undo(db, user, agent_session, proposal.id)
                    checks.append(Check("undo is refused", False, "undo was allowed"))
                except proposals.ProposalActionError as exc:
                    checks.append(Check("undo is refused", True, str(exc.detail)))
            elif name == "redo":
                await proposals.redo(db, user, agent_session, proposal.id)
                checks.append(Check("redo applies it again", same(await saved(), target)))
            elif name == "manual_edit":
                row = (await db.execute(select(SKUSelection).join(Collection).where(
                    Collection.architecture_id == proposal.architecture_id,
                    Collection.deleted_at.is_(None)).limit(1))).scalar_one()
                row.usage_quantity = Decimal(row.usage_quantity) + 1
                await db.commit()
                latest = proposals._latest_accepted(
                    await proposals.session_proposals(db, agent_session))
                view = await proposals.undo_view(db, user, proposal, latest)
                checks.append(Check("a manual edit ends undo",
                                    view is not None and view.end_reason == "edited",
                                    f"{view}"))
        except proposals.ProposalActionError as exc:
            checks.append(Check(f"{name} allowed", False, str(exc.detail)))
    return checks
