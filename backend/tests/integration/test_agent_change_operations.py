"""The change operations (025, contracts/agent-operations.md), run through the registry against
the provider fixtures: products by reference, proposals validated like manual edits and priced by
the engine, nothing saved to architectures, and the model never given an id or a SKU."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from src.agent.figures import FigureBook
from src.agent.operations import OperationContext, ToolError, registry
from src.models.orm import AgentMessage, AgentProposal, AgentSession, Architecture, User
from src.services.architecture_state import ArchitectureState
from tests.helpers.agent import combined_pricing_root


@pytest.fixture
async def world(db_session, use_pricing_root):
    use_pricing_root(combined_pricing_root())
    user = User(id=uuid.uuid4(), username=f"o-{uuid.uuid4().hex[:6]}")
    db_session.add(user)
    await db_session.flush()
    now = datetime.now(UTC)
    agent_session = AgentSession(user_id=user.id, started_at=now,
                                 closes_at=now + timedelta(days=3))
    db_session.add(agent_session)
    await db_session.flush()
    message = AgentMessage(session_id=agent_session.id, seq=1, role="user", content="q",
                           status="accepted")
    db_session.add(message)
    await db_session.commit()
    return db_session, user, agent_session, message


def ctx_for(world, architecture_id=None) -> OperationContext:
    db, user, agent_session, message = world
    return OperationContext(session=db, user=user, open_architecture_id=architecture_id,
                            figures=FigureBook(), agent_session=agent_session, message=message)


def _no_ids_or_skus(data: dict, skus: set[str]) -> None:
    text = json.dumps(data)
    for sku in skus:
        assert sku not in text, sku


async def _gcp_parts(ctx):
    return await registry.run(ctx, "find_products", {
        "provider": "gcp", "region": "us-east1",
        "parts": [{"part": "web", "category": "compute", "function": "vm"},
                  {"part": "db", "category": "database"},
                  {"part": "files", "category": "storage", "function": "object_storage"}],
    })


async def test_find_products_gives_references_per_part(world):
    ctx = ctx_for(world)
    found = await _gcp_parts(ctx)
    parts = found.data["parts"]
    assert set(parts) == {"web", "db", "files"}
    for part in parts.values():
        if "products" in part:
            assert 1 <= len(part["products"]) <= 5
            assert all(p["ref"].startswith("C") for p in part["products"])
    assert "products" in parts["files"]
    _no_ids_or_skus(found.data, {c.sku for c in ctx.matches.candidates.values()})


async def test_find_products_says_when_a_part_has_no_product(world):
    ctx = ctx_for(world)
    found = await registry.run(ctx, "find_products", {
        "provider": "gcp", "region": "us-east1",
        "parts": [{"part": "disk", "category": "storage", "function": "block_storage"}]})
    assert found.data["parts"]["disk"] == {
        "none": "the catalog has no product of that kind in this region"}


async def test_find_products_says_when_only_the_words_match_nothing(world):
    ctx = ctx_for(world)
    found = await registry.run(ctx, "find_products", {
        "provider": "gcp", "region": "us-east1",
        "parts": [{"part": "odd", "category": "storage", "function": "object_storage",
                   "text": "zzzz-no-such-thing"}]})
    assert found.data["parts"]["odd"] == {
        "none": "no product of that kind matches 'zzzz-no-such-thing' here; search again with "
                "a word from the product names, or no words"}


async def test_find_products_tries_each_word_when_the_phrase_matches_nothing(world):
    ctx = ctx_for(world)
    found = await registry.run(ctx, "find_products", {
        "provider": "gcp", "region": "us-east1",
        "parts": [{"part": "cold", "category": "storage", "function": "object_storage",
                   "text": "coldline archive"}]})
    products = found.data["parts"]["cold"]["products"]
    assert [p["product"] for p in products] == ["Coldline Storage South Carolina"]


async def test_find_products_refuses_a_region_without_data(world):
    with pytest.raises(ToolError, match="no pricing data for mars-1"):
        await registry.run(ctx_for(world), "find_products", {
            "provider": "gcp", "region": "mars-1",
            "parts": [{"part": "x", "category": "storage"}]})


async def test_propose_new_architecture_makes_a_pending_priced_proposal(world):
    db = world[0]
    ctx = ctx_for(world)
    found = await _gcp_parts(ctx)
    files = found.data["parts"]["files"]["products"][0]["ref"]
    before = await db.scalar(select(func.count()).select_from(Architecture))
    result = await registry.run(ctx, "propose_new_architecture", {
        "name": "Three-tier web app", "provider": "gcp",
        "collections": [{"ref": "new1", "type": "vpc", "name": "Web VPC",
                         "region": "us-east1"},
                        {"ref": "new2", "type": "application", "name": "Files",
                         "region": "us-east1", "parent": "new1"}],
        "services": [{"in": "new2", "product": files, "usage": "default",
                      "group": "storage"}],
        "assumptions": [{"kind": "usage", "text": "1 TB stored for the month"}],
    })
    data = result.data
    assert data["proposal"] == "Q1" and "nothing is saved" in data["status"]
    assert [i["op"] for i in data["items"]] == ["add", "add", "add"]
    assert data["cost"]["after"].startswith("F") and "before" not in data["cost"]
    _no_ids_or_skus(data, {c.sku for c in ctx.matches.candidates.values()})
    assert len(ctx.proposals) == 1
    await db.commit()
    proposal = (await db.execute(select(AgentProposal))).scalar_one()
    assert (proposal.kind, proposal.status, proposal.architecture_id) == ("create", "pending",
                                                                           None)
    target = ArchitectureState.model_validate(proposal.target_state)
    assert [c.name for c in target.collections] == ["Web VPC", "Files"]
    assert target.collections[1].parent_id == target.collections[0].id
    figure = ctx.figures.get(data["cost"]["after"])
    assert figure.amount == Decimal(proposal.cost["after"]["total"]) > 0
    # Nothing saved to architectures.
    assert await db.scalar(select(func.count()).select_from(Architecture)) == before


async def test_an_unknown_reference_is_refused(world):
    ctx = ctx_for(world)
    with pytest.raises(ToolError, match="unknown candidate 'C9'"):
        await registry.run(ctx, "propose_new_architecture", {
            "name": "x", "provider": "gcp",
            "collections": [{"ref": "new1", "type": "vpc", "name": "V", "region": "us-east1"}],
            "services": [{"in": "new1", "product": "C9", "usage": "default"}]})
    with pytest.raises(ToolError, match="unknown collection 'new7'"):
        await _gcp_parts(ctx)
        await registry.run(ctx, "propose_new_architecture", {
            "name": "x", "provider": "gcp",
            "collections": [{"ref": "new1", "type": "vpc", "name": "V", "region": "us-east1"}],
            "services": [{"in": "new7", "product": "C1", "usage": "default"}]})


async def test_validation_failures_name_the_item(world):
    ctx = ctx_for(world)
    with pytest.raises(ToolError, match=r"P1: region 'mars-1' is not currently available"):
        await registry.run(ctx, "propose_new_architecture", {
            "name": "x", "provider": "gcp",
            "collections": [{"ref": "new1", "type": "vpc", "name": "V", "region": "mars-1"}]})
    with pytest.raises(ToolError, match="P2: .*VPC"):
        await registry.run(ctx, "propose_new_architecture", {
            "name": "x", "provider": "gcp",
            "collections": [
                {"ref": "new1", "type": "application", "name": "A", "region": "us-east1"},
                {"ref": "new2", "type": "application", "name": "B", "region": "us-east1",
                 "parent": "new1"}]})


async def test_a_product_from_another_region_is_refused(world):
    ctx = ctx_for(world)
    found = await _gcp_parts(ctx)
    files = found.data["parts"]["files"]["products"][0]["ref"]
    with pytest.raises(ToolError, match="is in us-east1, but V is in us-west1"):
        await registry.run(ctx, "propose_new_architecture", {
            "name": "x", "provider": "gcp",
            "collections": [{"ref": "new1", "type": "vpc", "name": "V", "region": "us-west1"}],
            "services": [{"in": "new1", "product": files, "usage": "default"}]})


# --- US2: changing an existing architecture -------------------------------------------------------

WEB_APP = "Active-Standby Multi-Region Web Application"


async def _prod_web(world, *, owner=None):
    from tests.helpers.agent import build_standard

    db, user = world[0], owner or world[1]
    architecture = await build_standard(db, user, "aws", WEB_APP, rename="Prod Web")
    return architecture.id


async def test_describe_gives_row_references_and_ownership(world):
    architecture_id = await _prod_web(world)
    ctx = ctx_for(world, architecture_id)
    described = await registry.run(ctx, "describe_open_architecture", {})
    data = described.data
    assert data["owned"] is True
    refs = [c["ref"] for c in data["collections"]]
    assert refs == [f"A{i}" for i in range(1, len(refs) + 1)]
    services = [s["ref"] for c in data["collections"] for s in c["services"]]
    assert services[0] == "V1" and len(set(services)) == len(services)
    assert ctx.rows["A1"][0] == "collection" and ctx.rows["V1"][0] == "service"
    again = await registry.run(ctx, "describe_open_architecture", {})
    assert [c["ref"] for c in again.data["collections"]] == refs  # stable within the message


async def _replicate(world, architecture_id, region="us-west-2"):
    ctx = ctx_for(world, architecture_id)
    described = (await registry.run(ctx, "describe_open_architecture", {})).data
    primary = next(c for c in described["collections"] if c["region"] == "us-east-1")
    refs = [s["ref"] for s in primary["services"]][:3]
    found = await registry.run(ctx, "find_region_equivalents",
                               {"services": refs, "region": region})
    return ctx, primary, refs, found


async def test_region_equivalents_keep_usage_and_say_none(world):
    architecture_id = await _prod_web(world)
    ctx, _primary, refs, found = await _replicate(world, architecture_id)
    services = found.data["services"]
    assert set(services) == set(refs)
    assert any("ref" in s for s in services.values())
    for entry in services.values():
        if "ref" in entry:
            candidate = ctx.matches.candidate(entry["ref"])
            assert candidate.region == "us-west-2"
            assert candidate.quantity is not None and candidate.keep_term is not None
            assert entry["quality"] in ("exact", "close")
        else:
            assert entry["none"] == "no equivalent product in us-west-2"


async def test_region_equivalents_refuse_the_same_or_a_missing_region(world):
    architecture_id = await _prod_web(world)
    with pytest.raises(ToolError, match="already in us-east-1"):
        await _replicate(world, architecture_id, region="us-east-1")
    with pytest.raises(ToolError, match="no pricing data for mars-1"):
        await _replicate(world, architecture_id, region="mars-1")


async def test_propose_changes_replicates_scales_and_removes(world):
    db = world[0]
    architecture_id = await _prod_web(world)
    from src.services.architecture_state import fingerprint, read_state

    before = await read_state(db, architecture_id)
    ctx, primary, refs, found = await _replicate(world, architecture_id)
    copies = [e["ref"] for e in found.data["services"].values() if "ref" in e]
    result = await registry.run(ctx, "propose_changes", {
        "title": "Replicate Prod Web to us-west-2",
        "add_collections": [{"ref": "new1", "type": "vpc", "name": "Standby",
                             "region": "us-west-2", "group": "standby"}],
        "add_services": [{"in": "new1", "product": c, "group": "standby"} for c in copies],
        "change_services": [{"ref": refs[0], "scale": "0.5", "group": "resize"}],
        "remove": [{"ref": refs[1], "group": "resize"}],
        "assumptions": [{"kind": "region", "text": "us-west-2 for the standby",
                         "guessed": True}],
    })
    data = result.data
    ops = [i["op"] for i in data["items"]]
    assert ops.count("add") == 1 + len(copies) and "change" in ops and "remove" in ops
    for key in ("before", "after", "difference"):
        assert data["cost"][key].startswith("F")
    assert data["cost"]["contributions"]
    await db.commit()
    proposal = (await db.execute(select(AgentProposal))).scalar_one()
    assert (proposal.kind, proposal.architecture_id) == ("change", architecture_id)
    assert fingerprint(await read_state(db, architecture_id)) == fingerprint(before)
    target = ArchitectureState.model_validate(proposal.target_state)
    standby = next(c for c in target.collections if c.name == "Standby")
    copied = [s for s in target.services if s.collection_id == standby.id]
    originals = {s.id: s for s in before.services}
    # Each copy keeps the term of the service it copies (C1).
    for service in copied:
        assert any(o.pricing_term == service.pricing_term for o in originals.values())
    halved = target.service(ctx.rows[refs[0]][1])
    assert halved.usage_quantity == originals[halved.id].usage_quantity * Decimal("0.5")
    assert target.service(ctx.rows[refs[1]][1]) is None


async def test_propose_changes_keeps_a_term_unless_set(world):
    db = world[0]
    architecture_id = await _prod_web(world)
    ctx, _primary, _refs, found = await _replicate(world, architecture_id)
    copy = next(e["ref"] for e in found.data["services"].values() if "ref" in e)
    await registry.run(ctx, "propose_changes", {
        "title": "Standby",
        "add_collections": [{"ref": "new1", "type": "vpc", "name": "S", "region": "us-west-2"}],
        "add_services": [{"in": "new1", "product": copy},
                         {"in": "new1", "product": copy, "term": "reserved_1yr"}]})
    await db.commit()
    proposal = (await db.execute(select(AgentProposal))).scalar_one()
    target = ArchitectureState.model_validate(proposal.target_state)
    new = [s for s in target.services if s.collection_id == target.collections[-1].id]
    assert new[0].pricing_term == ctx.matches.candidate(copy).keep_term[0]
    assert (new[1].pricing_term, new[1].purchase_option) == ("reserved_1yr", "no_upfront")


async def test_another_users_architecture_cant_be_changed(world, db_session):
    other = User(id=uuid.uuid4(), username=f"x-{uuid.uuid4().hex[:6]}")
    db_session.add(other)
    await db_session.flush()
    architecture_id = await _prod_web(world, owner=other)
    ctx = ctx_for(world, architecture_id)
    with pytest.raises(ToolError, match="isn't available to this user"):
        await registry.run(ctx, "propose_changes", {
            "title": "x", "rename_architecture": "Mine now"})


async def test_list_and_open_my_architectures(world, db_session):
    first = await _prod_web(world)
    other = User(id=uuid.uuid4(), username=f"x-{uuid.uuid4().hex[:6]}")
    db_session.add(other)
    await db_session.flush()
    await _prod_web(world, owner=other)  # someone else's: never listed
    ctx = ctx_for(world)
    listed = (await registry.run(ctx, "list_my_architectures", {})).data["architectures"]
    assert [a["name"] for a in listed] == ["Prod Web"] and listed[0]["is_open"] is False
    opened = await registry.run(ctx, "open_architecture", {"architecture": "M1"})
    assert opened.data["opened"] == "Prod Web" and opened.data["collections"][0]["ref"] == "A1"
    assert ctx.opened == [(first, "Prod Web")] and ctx.open_architecture_id == first
    with pytest.raises(ToolError, match="unknown architecture 'M9'"):
        await registry.run(ctx, "open_architecture", {"architecture": "M9"})


# --- US5: importing through the agent --------------------------------------------------------------


def _content(state: ArchitectureState) -> tuple:
    """A state without ids: what an import must copy (FR-012)."""
    names = {c.id: c.name for c in state.collections}
    collections = sorted((c.type, c.name, c.region, names.get(c.parent_id)) for c in state.collections)
    services = sorted((names.get(s.collection_id), s.service_code, s.sku, s.pricing_term,
                       s.purchase_option, str(s.usage_quantity), str(s.provider_options))
                      for s in state.services if s.collection_id)
    connectors = sorted((names.get(c.from_id), names.get(c.to_id), c.arrow_style,
                         c.arrow_reversed) for c in state.connectors)
    return state.provider, collections, services, connectors


async def _admin_public(world, name="Serverless Microservices Back-End"):
    from tests.helpers.agent import build_standard

    db = world[0]
    owner = User(id=uuid.uuid4(), username=f"adm-{uuid.uuid4().hex[:6]}")
    db.add(owner)
    await db.flush()
    return await build_standard(db, owner, "aws", name, public=True)


async def test_propose_import_copies_like_the_menu(world):
    from src.services.architecture_import import import_architecture
    from src.services.architecture_state import load_architecture, read_state, state_of

    db, user = world[0], world[1]
    source = await _admin_public(world)
    ctx = ctx_for(world)
    listed = await registry.run(ctx, "list_importable_architectures", {})
    entry = next(a for g in listed.data["groups"] for a in g["architectures"]
                 if a["name"] == "Serverless Microservices Back-End")
    assert entry["ref"].startswith("I")
    result = await registry.run(ctx, "propose_import", {"architecture": entry["ref"]})
    assert result.data["proposal"] == "Q1"
    await db.commit()
    proposal = (await db.execute(select(AgentProposal))).scalar_one()
    assert (proposal.kind, proposal.source_architecture_id) == ("import", source.id)
    target = ArchitectureState.model_validate(proposal.target_state)
    assert target.name == "My Serverless Microservices Back-End"

    loaded = await load_architecture(db, source.id)
    menu_copy = await import_architecture(db, loaded, user, "My Serverless Microservices Back-End")
    assert _content(target) == _content(await read_state(db, menu_copy.id))
    assert _content(target) == _content(state_of(loaded))  # and nothing saved by the proposal


async def test_propose_import_takes_a_chosen_name_and_refuses_an_unknown_reference(world):
    db = world[0]
    await _admin_public(world)
    ctx = ctx_for(world)
    listed = await registry.run(ctx, "list_importable_architectures", {})
    ref = listed.data["groups"][0]["architectures"][0]["ref"]
    await registry.run(ctx, "propose_import", {"architecture": ref, "name": "Mine"})
    await db.commit()
    proposal = (await db.execute(select(AgentProposal))).scalar_one()
    assert proposal.target_state["name"] == "Mine"
    with pytest.raises(ToolError, match="unknown architecture 'I9'"):
        await registry.run(ctx, "propose_import", {"architecture": "I9"})


async def test_several_matching_architectures_are_all_listed(world):
    await _admin_public(world)
    await _admin_public(world)
    listed = await registry.run(ctx_for(world), "list_importable_architectures", {})
    names = [a["name"] for g in listed.data["groups"] for a in g["architectures"]]
    assert names.count("Serverless Microservices Back-End") == 2


# --- US6: refining a pending proposal --------------------------------------------------------------


async def test_a_refinement_revises_the_pending_proposal(world):
    db = world[0]
    architecture_id = await _prod_web(world)
    ctx, _primary, _refs, found = await _replicate(world, architecture_id)
    copies = [e["ref"] for e in found.data["services"].values() if "ref" in e][:2]
    await registry.run(ctx, "propose_changes", {
        "title": "Standby",
        "add_collections": [{"ref": "new1", "type": "vpc", "name": "Standby",
                             "region": "us-west-2"}],
        "add_services": [{"in": "new1", "product": c} for c in copies]})
    await db.commit()

    later = ctx_for(world, architecture_id)  # a later message: fresh references
    described = (await registry.run(later, "describe_open_architecture", {})).data
    pending = described["pending_proposal"]
    assert pending["proposal"] == "Q1"
    assert [i["ref"] for i in pending["items"]] == ["P1", "P2", "P3"]
    standby_service = pending["items"][1]["ref"]
    await registry.run(later, "propose_changes", {
        "title": "Standby at half size", "revise_pending": True,
        "change_services": [{"ref": standby_service, "scale": "0.5"}]})
    await db.commit()
    first, second = (await db.execute(select(AgentProposal).order_by(AgentProposal.seq)
                                      )).scalars().all()
    assert (first.status, second.status) == ("superseded", "pending")
    one = ArchitectureState.model_validate(first.target_state)
    two = ArchitectureState.model_validate(second.target_state)
    changed = [s for s in two.services if one.service(s.id) != s]
    assert len(changed) == 1
    assert changed[0].usage_quantity == one.service(changed[0].id).usage_quantity * Decimal("0.5")
    assert [c.id for c in one.collections] == [c.id for c in two.collections]


async def test_a_refinement_can_take_back_an_addition(world):
    db = world[0]
    architecture_id = await _prod_web(world)
    ctx, _primary, _refs, found = await _replicate(world, architecture_id)
    copies = [e["ref"] for e in found.data["services"].values() if "ref" in e][:2]
    await registry.run(ctx, "propose_changes", {
        "title": "Standby",
        "add_collections": [{"ref": "new1", "type": "vpc", "name": "Standby",
                             "region": "us-west-2"}],
        "add_services": [{"in": "new1", "product": c} for c in copies]})
    await db.commit()
    later = ctx_for(world, architecture_id)
    await registry.run(later, "describe_open_architecture", {})
    result = await registry.run(later, "propose_changes", {
        "title": "Standby with one copy", "revise_pending": True, "remove": [{"ref": "P3"}]})
    assert [i["op"] for i in result.data["items"]] == ["add", "add"]


async def test_revising_needs_a_pending_proposal(world):
    architecture_id = await _prod_web(world)
    ctx = ctx_for(world, architecture_id)
    await registry.run(ctx, "describe_open_architecture", {})
    with pytest.raises(ToolError, match="no pending proposal"):
        await registry.run(ctx, "propose_changes", {"title": "x", "revise_pending": True})


# --- Quantities as the Service tab holds them (T065 walk-through, 2026-11-19) -----------------------


async def _a_daily_service(world):
    """The open Prod Web, and a service whose quantity is a daily rate (hours, GB transferred)."""
    architecture_id = await _prod_web(world)
    ctx = ctx_for(world, architecture_id)
    described = (await registry.run(ctx, "describe_open_architecture", {})).data
    service = next(s for c in described["collections"] for s in c["services"]
                   if s.get("quantity_means", "").endswith("(the Service tab's daily rate)"))
    return ctx, service


async def test_describe_says_what_each_quantity_means(world):
    _ctx, service = await _a_daily_service(world)
    from src.agent.matching.usage import plain_number

    assert service["quantity_means"] == (
        f"{plain_number(service['quantity'])} {service['unit']} a day "
        "(the Service tab's daily rate)")


async def test_a_quantity_is_set_exactly_as_the_service_tab_holds_it(world):
    ctx, service = await _a_daily_service(world)
    result = await registry.run(ctx, "propose_changes", {
        "title": "Set it to 500", "change_services": [{"ref": service["ref"], "quantity": "500"}]})
    from src.agent.matching.usage import plain_number

    item = result.data["items"][0]
    assert item["quantity"] == (
        f"{plain_number(service['quantity'])} → 500 {service['unit']} a day")
    proposal = ctx.proposals[0]
    target = ArchitectureState.model_validate(proposal.target_state)
    assert target.service(ctx.rows[service["ref"]][1]).usage_quantity == Decimal("500")
    assert proposal.items[0]["quantity_unit"] == f"{service['unit']} a day"


async def test_doubling_is_scale_and_is_stated_per_day(world):
    ctx, service = await _a_daily_service(world)
    result = await registry.run(ctx, "propose_changes", {
        "title": "Double it", "change_services": [{"ref": service["ref"], "scale": "2"}]})
    from src.agent.matching.usage import plain_number

    doubled = plain_number(Decimal(service["quantity"]) * 2)
    assert result.data["items"][0]["quantity"].endswith(f"→ {doubled} {service['unit']} a day")


async def test_one_kind_of_amount_per_change(world):
    ctx, service = await _a_daily_service(world)
    with pytest.raises(ToolError, match="give one of quantity, usage or scale"):
        await registry.run(ctx, "propose_changes", {
            "title": "Both", "change_services": [{"ref": service["ref"], "quantity": "500",
                                                  "scale": "2"}]})


async def test_unchanged_services_have_a_plain_zero_difference(world):
    """T065: an unchanged service's difference was sent as "0E-13", shown as "+$0E13.undefined"."""
    ctx, service = await _a_daily_service(world)
    await registry.run(ctx, "propose_changes", {
        "title": "Double it", "change_services": [{"ref": service["ref"], "scale": "2"}]})
    cost = ctx.proposals[0].cost
    amounts = [row[key] for rows in (cost["by_service"], cost["by_region"]) for row in rows
               for key in ("before", "after", "difference") if row[key] is not None]
    amounts += [cost["difference"], cost["before"]["total"], cost["after"]["total"]]
    assert all("E" not in a and "e" not in a for a in amounts), amounts
    unchanged = [row for row in cost["by_service"] if row["before"] == row["after"]]
    assert unchanged and all(Decimal(row["difference"]) == 0 for row in unchanged)


# --- Resizing a GCP machine (T065, 2026-11-19) ------------------------------------------------------


async def _a_gcp_machine(world):
    from tests.helpers.agent import build_standard

    db, user = world[0], world[1]
    architecture = await build_standard(db, user, "gcp", WEB_APP, rename="GCP Web")
    ctx = ctx_for(world, architecture.id)
    described = (await registry.run(ctx, "describe_open_architecture", {})).data
    machine = next(s for c in described["collections"] for s in c["services"] if "size" in s)
    return ctx, machine


async def test_a_gcp_machine_is_resized_in_place(world):
    ctx, machine = await _a_gcp_machine(world)
    vcpu, memory = machine["size"]["vcpu"], Decimal(machine["size"]["memory_gib"])
    result = await registry.run(ctx, "propose_changes", {
        "title": "Double the vCPUs and memory",
        "change_services": [{"ref": machine["ref"],
                             "size": {"vcpu": vcpu * 2, "memory_gib": str(memory * 2)}}]})
    from src.agent.matching.usage import plain_number

    item = result.data["items"][0]
    assert item["size"] == (f"{vcpu} vCPU, {plain_number(memory)} GiB → {vcpu * 2} vCPU, "
                            f"{plain_number(memory * 2)} GiB")
    assert "quantity" not in item  # the hours per day stay as they are
    target = ArchitectureState.model_validate(ctx.proposals[0].target_state)
    service = target.service(ctx.rows[machine["ref"]][1])
    assert (service.provider_options["vcpus"], Decimal(service.provider_options["memory_gib"])) \
        == (vcpu * 2, memory * 2)
    assert Decimal(ctx.proposals[0].cost["difference"]) > 0  # a bigger machine costs more


async def test_size_is_refused_for_a_service_that_isnt_a_gcp_machine(world):
    ctx, service = await _a_daily_service(world)
    with pytest.raises(ToolError, match="applies to GCP machines only"):
        await registry.run(ctx, "propose_changes", {
            "title": "Bigger", "change_services": [{"ref": service["ref"],
                                                    "size": {"vcpu": 8, "memory_gib": 32}}]})
