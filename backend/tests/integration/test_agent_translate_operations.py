"""The translation operations (026, contracts/agent-operations.md) against the provider
fixtures, with the scripted world of tests.helpers.translation: matching order (R5), refusals,
references, structure, the cost record (R6), the partial-match guard (R7), refinement and
describe_translation."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from src.agent import proposals
from src.agent.matching import mappings
from src.agent.operations import ToolError, registry
from src.models.orm import AgentProposal, DataConnector, ServiceMapping
from src.services.architecture_state import ArchitectureState, read_state
from tests.helpers.agent import build_standard, combined_pricing_root
from tests.helpers.translation import (
    EKS,
    LAKE,
    WEB_APP,
    add_message,
    context,
    log_operation,
    make_world,
    one_row_per_service,
)


@pytest.fixture
async def world(db_session, use_pricing_root):
    use_pricing_root(combined_pricing_root())
    return await make_world(db_session)


@pytest.fixture
def no_seeds(monkeypatch):
    async def none(*_args, **_kwargs):
        return []

    monkeypatch.setattr(mappings, "seed_mappings", none)


async def _arch(world, name=WEB_APP, provider="aws", **kwargs):
    return await build_standard(world[0], world[1], provider, name, **kwargs)


def _service(found, label_part: str, where_part: str = ""):
    return next(s for s in found.data["services"]
                if label_part in s["label"] and where_part in s["where"])


async def _proposal(ctx) -> AgentProposal:
    return await ctx.session.get(AgentProposal, ctx.proposals[-1].id)


# --- Matching order (T014, research R5) ----------------------------------------------------------


async def test_seed_mappings_come_first_and_say_so(world):
    ctx = context(world, (await _arch(world)).id)
    found = await registry.run(ctx, "find_translation", {"provider": "gcp"})
    vm = _service(found, "t4g.xlarge", "us-east-1")
    assert vm["status"] == "matched" and vm["candidates"][0]["origin"] == "seeded"
    assert vm["candidates"][0]["quality"] == "close"  # arm64 vs x86_64
    lcu = next(s for s in found.data["services"] if s["status"] == "no_equivalent")
    assert "LCU-hour" in lcu["reason"]


async def test_a_seeded_partial_match_stands_when_nothing_better_is_found(world):
    ctx = context(world, (await _arch(world)).id)
    found = await registry.run(ctx, "find_translation", {"provider": "azure"})
    alb = [s for s in found.data["services"] if "Load Balancer-Application" in s["label"]
           and s["usage"].endswith(" Hrs a day")]
    assert alb and all(s["status"] == "partial_only" for s in alb)
    assert alb and all(s["candidates"][0]["origin"] == "seeded" for s in alb)


async def test_a_better_automatic_match_replaces_a_seeded_partial_one(world, monkeypatch):
    # The fixture has no Application Gateway, so an exact automatic match for the Application
    # Load Balancer is simulated: the seed (Azure Load Balancer, a network load balancer) is
    # partial, so the automatic match is used, and the seed's reason for leaving out the
    # load balancer's capacity units (about Azure Load Balancer) no longer applies.
    from src.agent import translation

    real = translation.find_candidates

    async def with_an_application_gateway(book, sources, targets, **kwargs):
        found = await real(book, sources, targets, **kwargs)
        for source in sources:
            if source.profile.function == "load_balancer":
                for candidate in found.get(source.ref, {}).get("azure", []):
                    candidate.quality, candidate.differences = "exact", []
        return found

    monkeypatch.setattr(translation, "find_candidates", with_an_application_gateway)
    ctx = context(world, (await _arch(world)).id)
    found = await registry.run(ctx, "find_translation", {"provider": "azure"})
    services = found.data["services"]
    alb = [s for s in services if "Load Balancer-Application" in s["label"]]
    hours = [s for s in alb if s["usage"].endswith(" Hrs a day")]
    assert hours and all(s["status"] in ("matched", "choose")
                         and s["candidates"][0]["origin"] == "automatic" for s in hours)
    lcu = [s for s in alb if "LCU" in s["usage"]]
    assert lcu and not any("Azure Load Balancer" in (s.get("reason") or "") for s in lcu)
    # Other services keep their seeds.
    assert any(s["candidates"] and s["candidates"][0]["origin"] == "seeded" for s in services)


async def test_without_a_seed_exact_and_close_are_automatic(world, no_seeds):
    ctx = context(world, (await _arch(world)).id)
    found = await registry.run(ctx, "find_translation", {"provider": "gcp"})
    vm = _service(found, "t4g.xlarge", "us-east-1")
    assert vm["status"] == "matched"
    assert vm["candidates"][0]["origin"] == "automatic"
    assert vm["candidates"][0]["quality"] in ("exact", "close")


async def test_only_partial_candidates_are_offered_with_no_default(world, no_seeds):
    ctx = context(world, (await _arch(world)).id)
    found = await registry.run(ctx, "find_translation", {"provider": "azure"})
    partial = [s for s in found.data["services"] if s["status"] == "partial_only"]
    assert partial
    assert all(s["default"] is None and s["candidates"] for s in partial)
    assert all(c["quality"] == "partial" for s in partial for c in s["candidates"])
    assert any("only partial" in n for n in found.data["needs_user"])
    assert found.summary["partial_offers"]


async def test_several_valid_equivalents_are_a_choice_with_the_best_first(world):
    ctx = context(world, (await _arch(world, LAKE)).id)
    found = await registry.run(ctx, "find_translation", {"provider": "azure"})
    choose = [s for s in found.data["services"] if s["status"] == "choose"]
    assert choose
    for service in choose:
        assert service["default"] == service["candidates"][0]["ref"]
        ranks = ["exact", "close", "partial"]
        qualities = [ranks.index(c["quality"]) for c in service["candidates"]]
        assert qualities == sorted(qualities)
    assert any("valid equivalents" in n for n in found.data["needs_user"])


async def test_a_product_not_sold_in_the_target_region_is_flagged(world):
    ctx = context(world, (await _arch(world, EKS)).id)
    found = await registry.run(ctx, "find_translation", {
        "provider": "gcp", "regions": {"us-west-2": "europe-west1"}})
    flagged = [s for s in found.data["services"] if s["status"] == "not_sold_in_region"]
    assert flagged and all("europe-west1" in s["reason"] for s in flagged)


# --- Refusals and references (T016) --------------------------------------------------------------


async def test_refusals(world, monkeypatch):
    ctx = context(world)
    with pytest.raises(ToolError, match="ask which one"):
        await registry.run(ctx, "find_translation", {"provider": "gcp"})
    gcp = await _arch(world, WEB_APP, "gcp")
    with pytest.raises(ToolError, match="already on GCP"):
        await registry.run(context(world, gcp.id), "find_translation", {"provider": "gcp"})
    with pytest.raises(ToolError, match="AWS to GCP or to Azure"):
        await registry.run(context(world, gcp.id), "find_translation", {"provider": "azure"})
    aws = await _arch(world)
    with pytest.raises(ToolError, match="isn't a GCP region"):
        await registry.run(context(world, aws.id), "find_translation", {
            "provider": "gcp", "regions": {"us-east-1": "mars-north1"}})
    with pytest.raises(ToolError, match="no GCP pricing data for us-central1.*nearest"):
        await registry.run(context(world, aws.id), "find_translation", {
            "provider": "gcp", "regions": {"us-east-1": "us-central1"}})
    from src.agent import operations_translate

    monkeypatch.setattr(operations_translate, "MAX_ITEMS", 5)
    with pytest.raises(ToolError, match="has 18 items.*at most 5"):
        await registry.run(context(world, aws.id), "find_translation", {"provider": "gcp"})
    with pytest.raises(ToolError, match="find_translation"):
        await registry.run(context(world, aws.id), "propose_translation", {"provider": "gcp"})


async def test_regions_are_guessed_one_per_source_region_in_one_result(world):
    ctx = context(world, (await _arch(world)).id)
    found = await registry.run(ctx, "find_translation", {"provider": "azure"})
    assert found.data["regions"] == [
        {"source": "us-east-1", "target": "eastus", "guessed": True},
        {"source": "us-west-2", "target": "westus2", "guessed": True}]
    assert any("regions guessed" in n for n in found.data["needs_user"])


async def test_a_named_own_architecture_is_found_by_reference(world):
    await _arch(world, rename="Prod Web")
    ctx = context(world)
    listed = await registry.run(ctx, "list_my_architectures", {})
    ref = next(a["ref"] for a in listed.data["architectures"] if a["name"] == "Prod Web")
    found = await registry.run(ctx, "find_translation", {"architecture": ref, "provider": "gcp"})
    assert found.data["source"]["name"] == "Prod Web"
    await registry.run(ctx, "propose_translation", {"architecture": ref, "provider": "gcp"})
    assert (await _proposal(ctx)).title == "Prod Web → GCP"


async def test_a_public_architecture_gives_the_users_own_proposal(world):
    db, user, *_ = world
    from src.models.orm import User

    other = User(id=uuid.uuid4(), username=f"p-{uuid.uuid4().hex[:6]}")
    db.add(other)
    await db.flush()
    await build_standard(db, other, "aws", WEB_APP, rename="Shared Web", public=True)
    ctx = context(world)
    listed = await registry.run(ctx, "list_importable_architectures", {"provider": "aws"})
    ref = next(a["ref"] for g in listed.data["groups"] for a in g["architectures"]
               if a["name"] == "Shared Web")
    await registry.run(ctx, "find_translation", {"architecture": ref, "provider": "azure"})
    await registry.run(ctx, "propose_translation", {"architecture": ref, "provider": "azure"})
    proposal = await _proposal(ctx)
    assert proposal.kind == "translate" and proposal.architecture_id is None
    assert proposal.target_state["name"] == "Shared Web"


# --- Structure (T016, FR-006) and the record (T022, SC-003) --------------------------------------


async def test_the_proposal_keeps_collections_nesting_and_connectors(world):
    db = world[0]
    arch = await _arch(world)
    detail_state = await read_state(db, arch.id)
    east, west = detail_state.collections[0], detail_state.collections[1]
    db.add(DataConnector(architecture_id=arch.id, from_collection_id=east.id,
                         to_collection_id=west.id, arrow_style="one_way"))
    await db.commit()
    ctx = context(world, arch.id)
    await registry.run(ctx, "find_translation", {"provider": "gcp"})
    out = await registry.run(ctx, "propose_translation", {"provider": "gcp", "name": "Web GCP"})
    proposal = await _proposal(ctx)
    state = ArchitectureState.model_validate(proposal.target_state)
    assert state.provider == "gcp" and state.name == "Web GCP"
    assert [(c.name, c.region) for c in state.collections] == [
        ("VPC (us-east-1)", "us-east1"), ("VPC (us-west-2)", "us-west1")]
    assert len(state.connectors) == 1
    assert state.connectors[0].arrow_style == "one_way"
    assert (state.connectors[0].from_id, state.connectors[0].to_id) == (
        state.collections[0].id, state.collections[1].id)
    from src.agent.operations import _open_architecture

    one_row_per_service(proposal.translation, (await _open_architecture(ctx))[1])
    assert out.data["rows"] == {"matched": 14, "left_out": 2, "chosen_by_user": 0}
    # Figures reach the model as references only.
    assert all(v is None or str(v).startswith("F") for k, v in out.data["cost"].items()
               if k.startswith(("original", "translation", "compared_"))
               and k != "compared_services")
    text = json.dumps(out.data)
    for row in proposal.translation["rows"]:
        if row["match"] and row["match"]["amount"]:
            assert row["match"]["amount"] not in text


async def test_every_amount_equals_the_engine(world):
    arch = await _arch(world)
    ctx = context(world, arch.id)
    await registry.run(ctx, "find_translation", {"provider": "azure"})
    await registry.run(ctx, "propose_translation", {"provider": "azure"})
    proposal = await _proposal(ctx)
    record = proposal.translation
    target = proposals.price_state(ArchitectureState.model_validate(proposal.target_state),
                                   "1_month")
    source = proposals.price_state(await read_state(world[0], arch.id), "1_month")
    summary = record["summary"]
    assert Decimal(summary["original_total"]["amount"]) == source.total
    assert Decimal(summary["translation_total"]["amount"]) == target.total
    assert summary["translation_total"]["partial"] is True  # LCU figures left out
    compared = [r for r in record["rows"] if r["status"] == "matched"]
    assert summary["compared"]["rows"] == len(compared)
    assert Decimal(summary["compared"]["original"]) == sum(
        Decimal(r["source"]["amount"]) for r in compared)
    assert Decimal(summary["compared"]["translation"]) == sum(
        Decimal(r["match"]["amount"]) for r in compared)
    diff = Decimal(summary["compared"]["translation"]) - Decimal(summary["compared"]["original"])
    assert Decimal(summary["compared"]["diff"]) == diff
    assert len(summary["drivers"]) == 3
    assert set(summary["snapshots"]) == {"aws", "azure"}
    assert proposal.translation["mapping_version"]["seed"] == 1


# --- Partial matches by the user's choice only (T026, R7) ----------------------------------------


async def test_a_partial_match_needs_an_earlier_offer(world, no_seeds):
    db, _user, agent_session, _message = world
    arch = await _arch(world)
    ctx = context(world, arch.id)
    found = await registry.run(ctx, "find_translation", {"provider": "azure"})
    offered = next(s for s in found.data["services"] if s["status"] == "partial_only")
    pick = {"source": offered["ref"], "candidate": offered["candidates"][0]["ref"]}
    with pytest.raises(ToolError, match="Ask the user whether to use this partial match|"
                                        "Ask the user whether"):
        await registry.run(ctx, "propose_translation", {"provider": "azure", "picks": [pick]})
    await log_operation(db, ctx, "find_translation", found)
    before = await db.scalar(select(func.count()).select_from(ServiceMapping))
    later = context(world, arch.id, message=await add_message(db, agent_session, 3))
    again = await registry.run(later, "find_translation", {"provider": "azure"})
    offered = next(s for s in again.data["services"] if s["where"] == offered["where"]
                   and s["label"] == offered["label"] and s["status"] == "partial_only")
    out = await registry.run(later, "propose_translation", {"provider": "azure", "picks": [
        {"source": offered["ref"], "candidate": offered["candidates"][0]["ref"]}]})
    assert out.data["rows"]["chosen_by_user"] == 1
    proposal = await _proposal(later)
    chosen = [r for r in proposal.translation["rows"] if r["origin"] == "chosen_by_user"]
    assert len(chosen) == 1 and chosen[0]["quality"] == "partial" and chosen[0]["differences"]
    assert any("chosen by you" in c for c in out.data["caveats"])
    assert await db.scalar(select(func.count()).select_from(ServiceMapping)) == before


async def test_no_equivalent_is_left_out_and_the_total_partial(world):
    ctx = context(world, (await _arch(world)).id)
    await registry.run(ctx, "find_translation", {"provider": "gcp"})
    await registry.run(ctx, "propose_translation", {"provider": "gcp"})
    proposal = await _proposal(ctx)
    left = [r for r in proposal.translation["rows"] if r["match"] is None]
    assert left and all(r["status"] == "no_equivalent" for r in left)
    assert proposal.translation["summary"]["translation_total"]["partial"] is True
    state = ArchitectureState.model_validate(proposal.target_state)
    assert len(state.services) == 14


# --- Refinement (T034) ---------------------------------------------------------------------------


async def test_a_second_proposal_supersedes_and_a_foreign_pick_is_refused(world):
    db = world[0]
    ctx = context(world, (await _arch(world, LAKE)).id)
    found = await registry.run(ctx, "find_translation", {"provider": "azure"})
    await registry.run(ctx, "propose_translation", {"provider": "azure"})
    first = ctx.proposals[-1].id
    choose = next(s for s in found.data["services"] if s["status"] == "choose")
    other = choose["candidates"][1]["ref"]
    await registry.run(ctx, "propose_translation", {"provider": "azure", "picks": [
        {"source": choose["ref"], "candidate": other}]})
    assert (await db.get(AgentProposal, first)).status == "superseded"
    second = await _proposal(ctx)
    assert second.status == "pending"
    labels = [r["match"]["label"] for r in second.translation["rows"]
              if r["where"] == choose["where"] and r["source"]["label"] == choose["label"]
              and r["match"]]
    assert any("Data Lake" in label for label in labels)
    foreign = next(s for s in found.data["services"] if s["ref"] != choose["ref"]
                   and s["candidates"])
    with pytest.raises(ToolError, match="isn't one of"):
        await registry.run(ctx, "propose_translation", {"provider": "azure", "picks": [
            {"source": choose["ref"], "candidate": foreign["candidates"][0]["ref"]}]})
    assert (await _proposal(ctx)).id == second.id and second.status == "pending"


# --- describe_translation (T037) -----------------------------------------------------------------


async def test_describe_translation_reads_the_record_in_a_later_message(world, monkeypatch):
    db, _user, agent_session, _message = world
    arch = await _arch(world)
    ctx = context(world, arch.id)
    with pytest.raises(ToolError, match="no translation"):
        await registry.run(ctx, "describe_translation", {})
    await registry.run(ctx, "find_translation", {"provider": "gcp"})
    proposed = await registry.run(ctx, "propose_translation", {"provider": "gcp"})
    later = context(world, arch.id, message=await add_message(db, agent_session, 3))
    from src.agent import translation as module

    def fail(*_a, **_k):
        raise AssertionError("describe_translation must not match or price again")

    monkeypatch.setattr(module, "match_sources", fail)
    monkeypatch.setattr(proposals, "price_state", fail)
    out = await registry.run(later, "describe_translation", {})
    assert out.data["proposal"] == proposed.data["proposal"] and out.data["stale"] is False
    assert out.data["caveats"] == proposed.data["caveats"]
    figure = later.figures.get(out.data["cost"]["compared_diff"])
    record = (await _proposal(ctx)).translation
    assert figure.amount == Decimal(record["summary"]["compared"]["diff"])
    with pytest.raises(ToolError, match="unknown translation"):
        await registry.run(later, "describe_translation", {"proposal": "Q99"})


# --- Performance (T043, plan.md's 10 s goal) -------------------------------------------------


@pytest.mark.parametrize("provider", ["gcp", "azure"])
@pytest.mark.parametrize("name", [WEB_APP, LAKE, EKS])
async def test_a_standard_architecture_is_found_and_priced_in_under_10_seconds(world, name,
                                                                             provider):
    """Finding and proposing a translation (matching, pricing both sides, the record) takes well
    under 10 s on the fixtures; this fails before a slowdown reaches users."""
    import time

    arch = await _arch(world, name)
    ctx = context(world, arch.id)
    started = time.perf_counter()
    await registry.run(ctx, "find_translation", {"provider": provider})
    await registry.run(ctx, "propose_translation", {"provider": provider})
    assert time.perf_counter() - started < 10
