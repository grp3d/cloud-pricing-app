"""Proposals (025, research R5, R6, data-model.md §2–§4).

A proposal is a list of **change items** (add, change or remove a collection, service or
connector, or rename the architecture) over a **base state**. `apply_items` turns the base and
the items into the target state, so the same function gives the proposal's result and each
group's contribution (the groups applied one after another, so the contributions add up to the
total difference exactly, US8).

Nothing here writes architecture rows until the user accepts (FR-003): states are priced as
unsaved ORM graphs through `calculate_architecture_price` (Principle I), and validated with the
same rules the edit routes use (`architecture_rules`, FR-002).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from src.models.schemas import CalculationDuration
from src.services import architecture_rules as rules
from src.services.architecture_state import (
    ArchitectureState,
    CollectionState,
    ConnectorState,
    ServiceState,
    to_transient,
)

# --- Change items -------------------------------------------------------------------------------


@dataclass
class ChangeItem:
    """One change. `before` / `after` are the row's fields as stored in the state (JSON-ready);
    `after` is None for a removal, `before` None for an addition."""

    op: str  # add | change | remove
    target: str  # collection | service | connector | architecture
    id: str | None  # the row id; None for the architecture's name
    label: str
    group: str | None = None
    before: dict | None = None
    after: dict | None = None
    ref: str = ""
    # For a changed service quantity: its unit with period, e.g. "GB a day" (a daily rate).
    quantity_unit: str | None = None

    def to_json(self) -> dict:
        out = {"ref": self.ref, "op": self.op, "target": self.target, "id": self.id,
               "label": self.label, "group": self.group, "before": self.before,
               "after": self.after}
        if self.quantity_unit:
            out["quantity_unit"] = self.quantity_unit
        return out

    @classmethod
    def from_json(cls, data: dict) -> ChangeItem:
        return cls(**{k: data.get(k) for k in ("op", "target", "id", "label", "group", "before",
                                               "after")}, ref=data.get("ref", ""),
                   quantity_unit=data.get("quantity_unit"))


_ROWS = {"collection": ("collections", CollectionState), "service": ("services", ServiceState),
         "connector": ("connectors", ConnectorState)}


def apply_items(base: ArchitectureState, items: list[ChangeItem]) -> ArchitectureState:
    """The state after `items`, in order. Removing a collection also removes its services, the
    connectors that touch it (with their service), and un-nests its children, as deleting it in
    the editor does; removing a connector removes its service."""
    state = base.model_copy(deep=True)
    for item in items:
        if item.target == "architecture":
            state.name = item.after["name"]
            continue
        key, model = _ROWS[item.target]
        rows = getattr(state, key)
        row_id = uuid.UUID(item.id)
        if item.op == "add":
            rows.append(model.model_validate(item.after))
        elif item.op == "change":
            index = next(i for i, r in enumerate(rows) if r.id == row_id)
            rows[index] = model.model_validate({**rows[index].model_dump(), **item.after})
        elif item.op == "remove":
            setattr(state, key, [r for r in rows if r.id != row_id])
            if item.target == "collection":
                state.services = [s for s in state.services if s.collection_id != row_id]
                gone = {c.id for c in state.connectors if row_id in (c.from_id, c.to_id)}
                state.connectors = [c for c in state.connectors if c.id not in gone]
                state.services = [s for s in state.services if s.connector_id not in gone]
                for c in state.collections:
                    if c.parent_id == row_id:
                        c.parent_id = None
            elif item.target == "connector":
                state.services = [s for s in state.services if s.connector_id != row_id]
    return state


def groups_in_order(items: list[ChangeItem]) -> list[str]:
    return list(dict.fromkeys(item.group or "changes" for item in items))


# --- Building -----------------------------------------------------------------------------------


@dataclass
class ServiceSpec:
    """A service to add, resolved from a catalog reference (never named by the model)."""

    service_code: str
    sku: str
    pricing_term: str
    purchase_option: str
    usage_quantity: Decimal
    provider_options: dict | None
    label: str


@dataclass
class Draft:
    """Builds the change items of one proposal. New rows get their ids and `created_at` here, so
    the target state is exactly what accepting saves (research R2)."""

    base: ArchitectureState
    clock: datetime
    items: list[ChangeItem] = field(default_factory=list)
    new_refs: dict[str, uuid.UUID] = field(default_factory=dict)  # "new1" -> collection id
    _tick: int = 0

    def _stamp(self) -> str:
        self._tick += 1
        return (self.clock + timedelta(microseconds=self._tick)).isoformat()

    def _add(self, item: ChangeItem) -> ChangeItem:
        item.ref = f"P{len(self.items) + 1}"
        self.items.append(item)
        return item

    @property
    def state(self) -> ArchitectureState:
        return apply_items(self.base, self.items)

    def add_collection(self, ref: str, *, type: str, name: str, region: str,
                       parent_id: uuid.UUID | None, group: str | None) -> uuid.UUID:
        new_id = uuid.uuid4()
        self.new_refs[ref] = new_id
        after = CollectionState(id=new_id, type=type, name=name, region=region,
                                parent_id=parent_id, created_at=self._stamp())
        self._add(ChangeItem("add", "collection", str(new_id), f"{name} ({region})", group,
                             after=after.model_dump(mode="json")))
        return new_id

    def add_service(self, spec: ServiceSpec, *, collection_id: uuid.UUID | None = None,
                    connector_id: uuid.UUID | None = None, group: str | None,
                    where: str) -> uuid.UUID:
        new_id = uuid.uuid4()
        after = ServiceState(
            id=new_id, collection_id=collection_id, connector_id=connector_id,
            service_code=spec.service_code, sku=spec.sku, pricing_term=spec.pricing_term,
            purchase_option=spec.purchase_option, usage_quantity=spec.usage_quantity,
            provider_options=spec.provider_options, created_at=self._stamp())
        self._add(ChangeItem("add", "service", str(new_id), f"{spec.label} in {where}", group,
                             after=after.model_dump(mode="json")))
        return new_id

    def add_connector(self, from_id: uuid.UUID, to_id: uuid.UUID, *, arrow_style: str,
                      group: str | None, label: str) -> uuid.UUID:
        new_id = uuid.uuid4()
        after = ConnectorState(id=new_id, from_id=from_id, to_id=to_id, arrow_style=arrow_style,
                               created_at=self._stamp())
        self._add(ChangeItem("add", "connector", str(new_id), label, group,
                             after=after.model_dump(mode="json")))
        return new_id

    def change(self, target: str, row_id: uuid.UUID, fields: dict, *, label: str,
               group: str | None, quantity_unit: str | None = None) -> None:
        current = {"collection": self.state.collection, "service": self.state.service,
                   "connector": self.state.connector}[target](row_id)
        if current is None:
            raise rules.RuleError(422, f"{label} isn't in the architecture")
        before = current.model_dump(mode="json")
        changed = {k: v for k, v in fields.items() if before.get(k) != v}
        if changed:
            self._add(ChangeItem("change", target, str(row_id), label, group,
                                 before={k: before[k] for k in changed}, after=changed,
                                 quantity_unit=quantity_unit if "usage_quantity" in changed
                                 else None))

    def remove(self, target: str, row_id: uuid.UUID, *, label: str, group: str | None) -> None:
        current = {"collection": self.state.collection, "service": self.state.service,
                   "connector": self.state.connector}[target](row_id)
        if current is None:
            raise rules.RuleError(422, f"{label} isn't in the architecture")
        self._add(ChangeItem("remove", target, str(row_id), label, group,
                             before=current.model_dump(mode="json")))

    def rename(self, name: str, *, group: str | None) -> None:
        if name != self.state.name:
            self._add(ChangeItem("change", "architecture", None, f"Name: {name}", group,
                                 before={"name": self.state.name}, after={"name": name}))


# --- Validation (FR-002) ------------------------------------------------------------------------


def validate(base: ArchitectureState | None, target: ArchitectureState,
             items: list[ChangeItem]) -> None:
    """Check the target state with the edit routes' rules. Raises `RuleError` with the first
    failure, its `ref` set to the change item it concerns."""
    rules.check_item_count(len(items))
    rules.check_provider(target.provider)
    touched = {item.id: item.ref for item in items}

    def fail(error: rules.RuleError, row_id) -> None:
        error.ref = touched.get(str(row_id))
        raise error

    base_ids = {c.id: c for c in base.collections} if base else {}
    base_content = set()
    if base:
        base_content = ({s.collection_id for s in base.services if s.collection_id}
                        | {c.parent_id for c in base.collections if c.parent_id})
    for collection in target.collections:
        try:
            rules.check_region_available(target.provider, collection.region)
            if collection.parent_id is not None:
                parent = target.collection(collection.parent_id)
                rules.check_nesting(collection.type, collection.region,
                                    None if parent is None else rules.CollectionFacts(
                                        type=parent.type, region=parent.region))
            old = base_ids.get(collection.id)
            if old is not None and old.region != collection.region:
                rules.check_region_change(locked=collection.id in base_content)
        except rules.RuleError as error:
            fail(error, collection.id)
    ids = {c.id for c in target.collections}
    for connector in target.connectors:
        try:
            rules.check_connector_ends(connector.from_id, connector.to_id, ids)
        except rules.RuleError as error:
            fail(error, connector.id)
    owners = [s.connector_id for s in target.services if s.connector_id]
    if len(owners) != len(set(owners)):
        raise rules.RuleError(409, "This Connector already has a Service. Create a new Connector "
                              "to add another.")
    changed = {uuid.UUID(i.id) for i in items if i.target == "service" and i.op != "remove"}
    for service in target.services:
        if service.id not in changed:
            continue
        region = target.service_region(service)
        if region is None:
            fail(rules.RuleError(422, "the service has no collection or connector"), service.id)
        try:
            rules.check_selection(target.provider, service_code=service.service_code,
                                  sku=service.sku, pricing_term=service.pricing_term,
                                  purchase_option=service.purchase_option,
                                  provider_options=service.provider_options, region=region)
        except rules.RuleError as error:
            fail(error, service.id)


# --- Cost (FR-004, research R5) -----------------------------------------------------------------


@dataclass
class Priced:
    total: Decimal
    partial: bool
    by_service: dict[uuid.UUID, Decimal]
    unpriceable: dict[uuid.UUID, str]
    snapshot: dict


def price_state(state: ArchitectureState, duration: str) -> Priced:
    from src.services.price_calculation import calculate_architecture_price

    result = calculate_architecture_price(to_transient(state),
                                          duration=CalculationDuration(duration))
    by_service: dict[uuid.UUID, Decimal] = {}
    for line in result.line_items:
        if line.priceable and line.price is not None:
            by_service[line.sku_selection_id] = (by_service.get(line.sku_selection_id, Decimal(0))
                                                 + Decimal(line.price))
    unpriceable = {u.sku_selection_id: u.reason for u in result.unpriceable}
    total = sum(by_service.values(), Decimal(0))
    return Priced(total, bool(unpriceable), by_service, unpriceable,
                  {"provider": state.provider, "date": str(result.snapshot_date),
                   "revision": int(result.snapshot_revision)})


def _pct(diff: Decimal, base: Decimal) -> Decimal | None:
    return None if base == 0 else diff / base * 100


def service_labels(state: ArchitectureState) -> dict[uuid.UUID, str]:
    """A readable name per service: the catalog's product name and where it is."""
    from src.agent.compare import describe_product

    names = {c.id: c.name for c in state.collections}
    out: dict[uuid.UUID, str] = {}
    for service in state.services:
        region = state.service_region(service) or ""
        product = (describe_product(state.provider, region, service.service_code, service.sku)
                   or f"{service.service_code} {service.sku}")
        if service.collection_id:
            where = names.get(service.collection_id, "?")
        else:
            connector = state.connector(service.connector_id)
            where = (f"{names.get(connector.from_id, '?')} → {names.get(connector.to_id, '?')}"
                     if connector else "?")
        out[service.id] = f"{product} in {where}"
    return out


def _amount(value) -> str:
    """A plain decimal string: never Python's exponent form ("0E-13" for an unchanged service's
    zero difference), which the UI can't read."""
    return f"{Decimal(value):f}"


def cost_summary(base: ArchitectureState | None, items: list[ChangeItem],
                 target: ArchitectureState, duration: str) -> dict:
    """The proposal's cost: before and after totals, the difference and percentage, by service
    and by region, the unpriceable items, and each group's contribution. Amounts are unrounded
    decimal strings; the UI and the figure references round them."""
    after = price_state(target, duration)
    before = price_state(base, duration) if base is not None else None
    labels = service_labels(target)
    if base is not None:
        labels = {**service_labels(base), **labels}

    def region_of(service_id: uuid.UUID) -> str:
        for state in (target, base):
            if state is None:
                continue
            service = state.service(service_id)
            if service is not None:
                return state.service_region(service) or "global"
        return "global"

    ids = list(dict.fromkeys([*(s.id for s in (base.services if base else [])),
                              *(s.id for s in target.services)]))
    by_service, by_region = [], {}
    for service_id in ids:
        b = before.by_service.get(service_id) if before else None
        a = after.by_service.get(service_id)
        in_before = base is not None and base.service(service_id) is not None
        in_after = target.service(service_id) is not None
        b_val = (b if b is not None else Decimal(0)) if in_before else None
        a_val = (a if a is not None else Decimal(0)) if in_after else None
        row = {"label": labels.get(service_id, str(service_id)),
               "before": None if b_val is None else _amount(b_val),
               "after": None if a_val is None else _amount(a_val),
               "difference": None if before is None else _amount((a_val or 0) - (b_val or 0))}
        by_service.append(row)
        region = region_of(service_id)
        totals = by_region.setdefault(region, [Decimal(0), Decimal(0)])
        totals[0] += b_val or 0
        totals[1] += a_val or 0
    cost: dict = {
        "duration": duration,
        "snapshot": after.snapshot,
        "after": {"total": _amount(after.total), "partial": after.partial},
        "by_service": by_service,
        "by_region": [
            {"label": region, "before": None if before is None else _amount(b), "after": _amount(a),
             "difference": None if before is None else _amount(a - b)}
            for region, (b, a) in sorted(by_region.items())
        ],
        "unpriceable": [{"label": labels.get(sid, str(sid)), "reason": reason}
                        for sid, reason in after.unpriceable.items()],
        "contributions": [],
    }
    if before is not None:
        diff = after.total - before.total
        cost["before"] = {"total": _amount(before.total), "partial": before.partial}
        cost["difference"] = _amount(diff)
        pct = _pct(diff, before.total)
        cost["percent"] = None if pct is None else _amount(pct)
        groups = groups_in_order(items)
        if len(groups) > 1:
            previous = before.total
            for index, group in enumerate(groups):
                upto = set(groups[: index + 1])
                state = apply_items(base, [i for i in items if (i.group or "changes") in upto])
                total = (after.total if index == len(groups) - 1
                         else price_state(state, duration).total)
                cost["contributions"].append({"group": group, "difference": _amount(total - previous)})
                previous = total
    return cost


def check_applies(state: ArchitectureState, items: list[ChangeItem]) -> None:
    """Every row a change or removal refers to is still there (a stale proposal, FR-007)."""
    find = {"collection": state.collection, "service": state.service,
            "connector": state.connector}
    for item in items:
        if item.target != "architecture" and item.op != "add":
            if find[item.target](uuid.UUID(item.id)) is None:
                raise rules.RuleError(422, f"{item.label} is no longer in the architecture, so "
                                      "this proposal can't be accepted. Ask the agent again.",
                                      ref=item.ref)


# --- Storage and the user's actions (research R6, R9; contracts/agent-api.md) --------------------

from sqlalchemy import func as sa_func  # noqa: E402
from sqlalchemy import select  # noqa: E402

from src.models.orm import AgentOperation, AgentProposal, Architecture  # noqa: E402
from src.models.schemas import (  # noqa: E402
    AgentProposalOut,
    ProposalAcceptBody,
    ProposalUndoOut,
)
from src.services.architecture_state import (  # noqa: E402
    apply_state,
    fingerprint,
    load_architecture,
    read_state,
    state_of,
)


class ProposalActionError(Exception):
    """An action the user can't take now: the HTTP status and a brief, precise detail."""

    def __init__(self, status: int, detail):
        super().__init__(str(detail))
        self.status = status
        self.detail = detail


async def db_clock(session) -> datetime:
    """The database's local time, as the `created_at` server defaults use, so new rows sort
    after existing ones."""
    return await session.scalar(select(sa_func.localtimestamp()))


async def create_proposal(session, agent_session, message, *, kind: str, title: str,
                          base: ArchitectureState | None, target: ArchitectureState,
                          items: list[ChangeItem], cost: dict, assumptions: list[dict],
                          architecture_id: uuid.UUID | None,
                          source_architecture_id: uuid.UUID | None = None) -> AgentProposal:
    """Save a pending proposal; any pending one in the session is superseded (one pending per
    session, research R6). Nothing is written to architectures."""
    now = datetime.now(UTC)
    for pending in (await session.execute(select(AgentProposal).where(
            AgentProposal.session_id == agent_session.id,
            AgentProposal.status == "pending"))).scalars():
        pending.status = "superseded"
        pending.decided_at = now
    current = await session.scalar(select(sa_func.max(AgentProposal.seq)).where(
        AgentProposal.session_id == agent_session.id))
    proposal = AgentProposal(
        session_id=agent_session.id, message_id=message.id, seq=(current or 0) + 1, kind=kind,
        architecture_id=architecture_id, source_architecture_id=source_architecture_id,
        title=title[:200], status="pending", items=[i.to_json() for i in items],
        base_state=None if base is None else base.model_dump(mode="json"),
        target_state=target.model_dump(mode="json"),
        base_fingerprint=None if base is None else fingerprint(base),
        cost=cost, assumptions=assumptions,
    )
    session.add(proposal)
    await session.flush()
    return proposal


async def session_proposals(session, agent_session) -> list[AgentProposal]:
    return list((await session.execute(select(AgentProposal).where(
        AgentProposal.session_id == agent_session.id).order_by(AgentProposal.seq))).scalars())


async def _owned_state(session, user, architecture_id) -> tuple[Architecture | None,
                                                                 ArchitectureState | None]:
    architecture = await load_architecture(session, architecture_id) if architecture_id else None
    if architecture is None or architecture.user_id != user.id:
        return None, None
    return architecture, state_of(architecture)


def _latest_accepted(proposals: list[AgentProposal]) -> AgentProposal | None:
    accepted = [p for p in proposals if p.status == "accepted"]
    return max(accepted, key=lambda p: p.seq) if accepted else None


async def undo_view(session, user, proposal: AgentProposal,
                    latest: AgentProposal | None) -> ProposalUndoOut | None:
    """Whether the accepted proposal can be undone or redone now (research R3). A manual edit, a
    later accepted proposal or deleting the architecture ends it for good; the end is saved."""
    if proposal.status != "accepted" or proposal.undo_status is None:
        return None
    if proposal.undo_status != "ended":
        reason = None
        if latest is not None and latest.id != proposal.id:
            reason = "superseded"
        else:
            _arch, state = await _owned_state(session, user, proposal.architecture_id)
            current = None if state is None else fingerprint(state)
            created = proposal.kind in ("create", "import")
            if proposal.undo_status == "available":
                if current is None:
                    reason = "deleted"
                elif current != proposal.after_fingerprint:
                    reason = "edited"
            elif proposal.undo_status == "undone":
                if created and current is not None:
                    reason = "edited"
                elif not created and current != proposal.before_fingerprint:
                    reason = "deleted" if current is None else "edited"
        if reason is not None:
            proposal.undo_status, proposal.undo_end_reason = "ended", reason
    if proposal.undo_status == "ended":
        return ProposalUndoOut(status="ended", can_undo=False, can_redo=False,
                               end_reason=proposal.undo_end_reason)
    return ProposalUndoOut(status=proposal.undo_status,
                           can_undo=proposal.undo_status == "available",
                           can_redo=proposal.undo_status == "undone")


async def to_out(session, user, proposal: AgentProposal,
                 latest: AgentProposal | None = None) -> AgentProposalOut:
    architecture, state = await _owned_state(session, user, proposal.architecture_id)
    stale = (proposal.status == "pending" and proposal.kind == "change"
             and (state is None or fingerprint(state) != proposal.base_fingerprint))
    name = architecture.name if architecture is not None else (
        proposal.target_state.get("name") if proposal.kind != "change" else None)
    return AgentProposalOut(
        id=proposal.id, message_id=proposal.message_id, seq=proposal.seq, kind=proposal.kind,
        architecture_id=proposal.architecture_id, architecture_name=name, title=proposal.title,
        status=proposal.status, stale=stale,
        items=[{k: v for k, v in i.items() if k != "id"} for i in proposal.items],
        cost=proposal.cost, assumptions=proposal.assumptions,
        undo=await undo_view(session, user, proposal, latest),
        created_at=proposal.created_at, decided_at=proposal.decided_at,
    )


async def _log(session, proposal: AgentProposal, name: str, summary: dict) -> None:
    current = await session.scalar(select(sa_func.max(AgentOperation.seq)).where(
        AgentOperation.message_id == proposal.message_id))
    session.add(AgentOperation(
        session_id=proposal.session_id, message_id=proposal.message_id, seq=(current or 0) + 1,
        name=name, inputs={"proposal_id": str(proposal.id),
                           "architecture_id": str(proposal.architecture_id)
                           if proposal.architecture_id else None},
        outcome="ok", summary={"title": proposal.title, "items": len(proposal.items), **summary},
        snapshot={proposal.cost.get("snapshot", {}).get("provider", "?"):
                  {k: v for k, v in proposal.cost.get("snapshot", {}).items()
                   if k != "provider"}} if proposal.cost.get("snapshot") else None,
        started_at=datetime.now(UTC), duration_ms=0,
    ))


async def _proposal_for(session, agent_session, proposal_id: uuid.UUID) -> AgentProposal:
    proposal = await session.get(AgentProposal, proposal_id)
    if proposal is None or proposal.session_id != agent_session.id:
        raise ProposalActionError(404, "Proposal not found")
    if agent_session.busy_message_id is not None:
        raise ProposalActionError(409, "busy")
    return proposal


def _decided(proposal: AgentProposal) -> None:
    proposal.decided_at = datetime.now(UTC)


async def reject(session, user, agent_session, proposal_id: uuid.UUID) -> AgentProposal:
    proposal = await _proposal_for(session, agent_session, proposal_id)
    if proposal.status != "pending":
        raise ProposalActionError(409, "This proposal isn't waiting for a decision.")
    proposal.status = "rejected"
    _decided(proposal)
    await _log(session, proposal, "reject_proposal", {})
    await session.commit()
    return proposal


async def _end_earlier_undo(session, agent_session, keep: AgentProposal) -> None:
    for other in await session_proposals(session, agent_session):
        if other.id != keep.id and other.status == "accepted" and other.undo_status != "ended":
            other.undo_status, other.undo_end_reason = "ended", "superseded"


async def accept(session, user, agent_session, proposal_id: uuid.UUID,
                 body: ProposalAcceptBody) -> tuple[AgentProposal, uuid.UUID | None]:
    """Save exactly the proposed state (FR-003, FR-005). A stale change proposal is checked and
    re-priced first; the user sees the new figures and accepts again (FR-007)."""
    proposal = await _proposal_for(session, agent_session, proposal_id)
    if proposal.status != "pending":
        raise ProposalActionError(409, "This proposal isn't waiting for a decision.")
    items = [ChangeItem.from_json(i) for i in proposal.items]
    target = ArchitectureState.model_validate(proposal.target_state)
    if proposal.kind == "change":
        architecture, current = await _owned_state(session, user, proposal.architecture_id)
        if current is None:
            raise ProposalActionError(409, "The architecture this proposal changes is gone.")
        if body.architecture_id != proposal.architecture_id:
            raise ProposalActionError(409, f"Open {architecture.name} to accept this change.")
        if fingerprint(current) != proposal.base_fingerprint:
            try:
                check_applies(current, items)
                target = apply_items(current, items)
                validate(current, target, items)
            except rules.RuleError as error:
                raise ProposalActionError(422, error.message) from error
            proposal.base_state = current.model_dump(mode="json")
            proposal.target_state = target.model_dump(mode="json")
            proposal.base_fingerprint = fingerprint(current)
            proposal.cost = cost_summary(current, items, target, proposal.cost["duration"])
            if not body.confirm_restaled:
                await session.commit()
                raise ProposalActionError(409, {"error": "stale",
                                                "proposal": str(proposal.id)})
        try:
            validate(current, target, items)
        except rules.RuleError as error:
            raise ProposalActionError(422, error.message) from error
        await apply_state(session, proposal.architecture_id, target)
        proposal.before_fingerprint = proposal.base_fingerprint
        opened = None
    else:
        try:
            validate(None, target, items)
        except rules.RuleError as error:
            raise ProposalActionError(422, error.message) from error
        new_id = uuid.uuid4()
        session.add(Architecture(id=new_id, user_id=user.id, name=target.name,
                                 provider=target.provider, is_public=False))
        await session.flush()
        await apply_state(session, new_id, target)
        proposal.architecture_id = new_id
        proposal.before_fingerprint = None
        opened = new_id
    saved = await read_state(session, proposal.architecture_id)
    proposal.after_fingerprint = fingerprint(saved)
    proposal.status, proposal.undo_status, proposal.undo_end_reason = "accepted", "available", None
    _decided(proposal)
    await _end_earlier_undo(session, agent_session, proposal)
    await _log(session, proposal, "accept_proposal", {})
    await session.commit()
    return proposal, opened


_ENDED = {
    "edited": "Your latest edit means the agent's previous change can no longer be undone.",
    "superseded": "A later change replaced this one, so it can no longer be undone.",
    "session_ended": "The session has ended, so this change can no longer be undone.",
    "deleted": "The architecture was deleted, so this change can no longer be undone.",
}


async def _undoable(session, user, agent_session, proposal_id, want: str) -> AgentProposal:
    proposal = await _proposal_for(session, agent_session, proposal_id)
    latest = _latest_accepted(await session_proposals(session, agent_session))
    view = await undo_view(session, user, proposal, latest)
    if view is None:
        raise ProposalActionError(409, "This proposal wasn't accepted.")
    if view.status == "ended":
        await session.commit()  # the end is kept
        raise ProposalActionError(409, _ENDED[view.end_reason])
    if (want == "undo" and not view.can_undo) or (want == "redo" and not view.can_redo):
        raise ProposalActionError(409, "There's nothing to " + want + ".")
    return proposal


async def undo(session, user, agent_session, proposal_id: uuid.UUID) -> AgentProposal:
    """Put the architecture back exactly as it was before the accept (FR-005). A created or
    imported architecture is soft deleted, keeping its ids for redo."""
    proposal = await _undoable(session, user, agent_session, proposal_id, "undo")
    if proposal.kind == "change":
        await apply_state(session, proposal.architecture_id,
                          ArchitectureState.model_validate(proposal.base_state))
    else:
        architecture = await session.get(Architecture, proposal.architecture_id)
        architecture.deleted_at = datetime.now(UTC).replace(tzinfo=None)
    proposal.undo_status = "undone"
    await _log(session, proposal, "undo_proposal", {})
    await session.commit()
    return proposal


async def redo(session, user, agent_session, proposal_id: uuid.UUID) -> AgentProposal:
    proposal = await _undoable(session, user, agent_session, proposal_id, "redo")
    if proposal.kind == "change":
        await apply_state(session, proposal.architecture_id,
                          ArchitectureState.model_validate(proposal.target_state))
    else:
        architecture = await session.get(Architecture, proposal.architecture_id)
        architecture.deleted_at = None
    proposal.undo_status = "available"
    await _log(session, proposal, "redo_proposal", {})
    await session.commit()
    return proposal
