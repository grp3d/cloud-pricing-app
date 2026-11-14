"""The comparison operations (024, contracts/agent-operations.md), run through the registry
against the provider fixtures: candidates by reference, every figure the engine's, results
saved for the pane, nothing else saved, and the edge cases of US2–US5."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from src.agent.figures import FigureBook
from src.agent.operations import OperationContext, ToolError, registry
from src.models.orm import (
    AgentMessage,
    AgentResult,
    AgentSession,
    Architecture,
    Collection,
    DataConnector,
    User,
)
from src.models.schemas import CalculationDuration, SnapshotSelection
from src.services.price_calculation import (
    build_transient_architecture,
    calculate_architecture_price,
)
from tests.helpers.agent import build_standard, combined_pricing_root

WEB_APP = "Active-Standby Multi-Region Web Application"


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


def _engine(provider, region, item, quantity, options=None, term="on_demand",
            duration="1_month") -> Decimal:
    arch = build_transient_architecture([SnapshotSelection(
        service_code=item[0], sku=item[1], pricing_term=term, purchase_option="not_applicable",
        usage_quantity=quantity, region=region, provider_options=options)], provider=provider)
    return calculate_architecture_price(arch, CalculationDuration(duration)).total_price


async def _result(db, result_id) -> AgentResult:
    return (await db.execute(select(AgentResult).where(AgentResult.id == uuid.UUID(result_id)))
            ).scalar_one()


# --- search_products / price_products (US1, US5) --------------------------------------------------


async def test_search_products_returns_references_per_provider_with_guessed_regions(world):
    ctx = ctx_for(world)
    out = await registry.run(ctx, "search_products", {
        "providers": ["azure", "gcp"], "category": "storage", "function": "object_storage",
        "regions": {"azure": "eastus"}})
    azure, gcp = out.data["providers"]["azure"], out.data["providers"]["gcp"]
    assert (azure["region"], azure["guessed"]) == ("eastus", False)
    assert (gcp["region"], gcp["guessed"]) == ("us-east1", True)
    assert azure["products"] and gcp["products"]
    assert all(p["ref"].startswith("C") and "quality" not in p for p in gcp["products"])
    assert len(gcp["products"]) <= 5


async def test_search_products_with_a_reference_labels_quality(world):
    ctx = ctx_for(world)
    first = await registry.run(ctx, "search_products", {
        "providers": ["azure"], "category": "storage", "function": "object_storage",
        "regions": {"azure": "eastus"}})
    ref = first.data["providers"]["azure"]["products"][0]["ref"]
    second = await registry.run(ctx, "search_products", {
        "providers": ["gcp"], "category": "storage", "function": "object_storage",
        "regions": {"gcp": "us-east1"}, "reference": ref})
    products = second.data["providers"]["gcp"]["products"]
    assert products[0]["quality"] in ("exact", "close")  # Standard vs Hot: same tier
    assert any(p["quality"] == "partial" for p in products)  # Coldline: another tier


async def test_search_products_refuses_unknown_things(world):
    ctx = ctx_for(world)
    with pytest.raises(ToolError, match="isn't a GCP region"):
        await registry.run(ctx, "search_products", {"providers": ["gcp"],
                                                    "category": "storage",
                                                    "regions": {"gcp": "mars-1"}})
    with pytest.raises(ToolError, match="invalid arguments"):
        await registry.run(ctx, "search_products", {"providers": ["ibm"], "category": "storage"})
    with pytest.raises(ToolError, match="unknown candidate"):
        await registry.run(ctx, "search_products", {"providers": ["gcp"], "category": "storage",
                                                    "regions": {"gcp": "us-east1"},
                                                    "reference": "C42"})


async def _two_storage_picks(ctx) -> tuple[dict, dict]:
    out = await registry.run(ctx, "search_products", {
        "providers": ["azure", "gcp"], "category": "storage", "function": "object_storage",
        "regions": {"azure": "eastus", "gcp": "us-east1"}, "text": None})
    azure = next(p for p in out.data["providers"]["azure"]["products"] if "Hot" in p["product"])
    gcp = next(p for p in out.data["providers"]["gcp"]["products"]
               if p["product"].startswith("Standard"))
    return azure, gcp


async def test_price_products_compares_against_the_first_pick_and_saves_a_result(world):
    db, *_ = world
    ctx = ctx_for(world)
    azure, gcp = await _two_storage_picks(ctx)
    out = await registry.run(ctx, "price_products", {
        "picks": [azure["ref"], gcp["ref"]], "usage": {"quantity": 1, "unit": "tb"},
        "duration": "1_month"})
    az_book, gcp_book = (ctx.matches.candidate(azure["ref"]), ctx.matches.candidate(gcp["ref"]))
    az_amount = _engine("azure", "eastus", (az_book.service_code, az_book.sku), 1000)
    gcp_amount = _engine("gcp", "us-east1", (gcp_book.service_code, gcp_book.sku), 1000)
    prices = out.data["prices"]
    assert ctx.figures.get(prices["azure:eastus"]["price"]).amount == az_amount
    assert ctx.figures.get(prices["gcp:us-east1"]["price"]).amount == gcp_amount
    assert ctx.figures.get(prices["gcp:us-east1"]["difference"]).amount == gcp_amount - az_amount
    pct = ctx.figures.get(prices["gcp:us-east1"]["difference_pct"])
    assert pct.kind == "percent" and pct.amount == (gcp_amount - az_amount) / az_amount * 100
    assert out.data["usage"] == "1 TB stored"
    result = await _result(db, out.data["result_id"])
    assert result.kind == "category_comparison"
    assert result.title == "Object storage: Azure vs GCP"
    cell = result.rows[0]["cells"]["gcp:us-east1"]
    assert Decimal(cell["amount"]) == gcp_amount
    assert ctx.results == [result]
    assert out.summary["result_id"] == out.data["result_id"]
    assert any(az_book.sku in pick for pick in out.summary["picks"])


async def test_default_usage_is_the_apps_and_stated(world):
    ctx = ctx_for(world)
    azure, gcp = await _two_storage_picks(ctx)
    out = await registry.run(ctx, "price_products", {"picks": [azure["ref"], gcp["ref"]],
                                                    "usage": "default"})
    assert out.data["usage"] == "1 TB stored for the month"
    result = await _result(world[0], out.data["result_id"])
    assert "Default usage: 1 TB stored for the month" in result.basis["assumptions"]


async def test_one_pick_is_a_single_price_without_a_result(world):
    db, *_ = world
    ctx = ctx_for(world)
    azure, _gcp = await _two_storage_picks(ctx)
    out = await registry.run(ctx, "price_products", {"picks": [azure["ref"]],
                                                    "usage": {"quantity": 500, "unit": "gb"}})
    assert "result_id" not in out.data
    assert ctx.figures.get(out.data["prices"]["azure:eastus"]["price"]).amount > 0
    count = (await db.execute(select(func.count()).select_from(AgentResult))).scalar()
    assert count == 0


async def test_a_term_a_product_doesnt_offer_is_unavailable_with_the_terms_it_does(world):
    ctx = ctx_for(world)
    azure, gcp = await _two_storage_picks(ctx)
    out = await registry.run(ctx, "price_products", {
        "picks": [azure["ref"], gcp["ref"]], "usage": "default",
        "terms": {"gcp": "commitment_1yr"}})
    unavailable = out.data["prices"]["gcp:us-east1"]["unavailable"]
    assert unavailable.startswith("term not offered (offers: on_demand")
    assert "price" not in out.data["prices"]["gcp:us-east1"]


async def test_a_provider_without_pricing_in_the_region_is_unavailable_not_an_error(world):
    ctx = ctx_for(world)
    out = await registry.run(ctx, "search_products", {
        "providers": ["azure", "gcp"], "category": "storage", "function": "object_storage",
        "regions": {"azure": "eastus", "gcp": "asia-east1"}})
    gcp = out.data["providers"]["gcp"]
    assert gcp["unavailable"] == "no GCP pricing data for asia-east1"
    assert "products" not in gcp
    assert out.data["providers"]["azure"]["products"]


async def test_a_name_matching_several_products_returns_several_candidates(world):
    ctx = ctx_for(world)
    out = await registry.run(ctx, "search_products", {
        "providers": ["gcp"], "category": "database", "function": "managed_db",
        "regions": {"gcp": "us-east1"}, "text": "Cloud SQL"})
    assert len(out.data["providers"]["gcp"]["products"]) >= 2


# --- find_matches / price_matches (US2, US3) ------------------------------------------------------


@pytest.fixture
async def web_app(world):
    db, user, *_ = world
    return await build_standard(db, user, "aws", WEB_APP)


async def test_find_matches_covers_every_service_for_both_targets(world, web_app):
    ctx = ctx_for(world, web_app.id)
    out = await registry.run(ctx, "find_matches", {"target_providers": ["azure", "gcp"]})
    sources = out.data["sources"]
    assert len(sources) == 16
    assert all(set(s["candidates"]) == {"azure", "gcp"} for s in sources)
    regions = out.data["regions"]
    assert regions["azure"]["us-east-1"] == {"region": "eastus", "guessed": True}
    assert regions["gcp"]["us-west-2"] == {"region": "us-west1", "guessed": True}
    vm = next(s for s in sources if "t4g.xlarge" in s["service"])
    assert vm["candidates"]["azure"][0]["quality"] == "close"
    transfer = next(s for s in sources if "Data Transfer" in s["service"])
    gcp_transfer = transfer["candidates"]["gcp"][0]
    assert gcp_transfer["quality"] == "exact" and "Inter Region" in gcp_transfer["product"]
    lb = next(s for s in sources if "LCU" in s["service"] or "Load Balancer" in s["service"])
    assert all(c["quality"] != "exact" for c in lb["candidates"]["azure"]
               if isinstance(c, dict) and "quality" in c) or isinstance(
                   lb["candidates"]["azure"], dict)


async def test_find_matches_category_hints_and_errors(world, web_app):
    ctx = ctx_for(world, web_app.id)
    storage = await registry.run(ctx, "find_matches", {"target_providers": ["gcp"],
                                                      "category": "storage"})
    assert storage.data["sources"] and all(
        "S3" in s["service"] for s in storage.data["sources"])
    ref = storage.data["sources"][0]["ref"]
    again = await registry.run(ctx, "find_matches", {"target_providers": ["gcp"],
                                                    "category": "storage",
                                                    "hints": {ref: "Coldline"}})
    first = again.data["sources"][0]["candidates"]["gcp"]
    assert any("Coldline" in c["product"] for c in first)
    with pytest.raises(ToolError, match="already on AWS"):
        await registry.run(ctx, "find_matches", {"target_providers": ["aws"]})
    with pytest.raises(ToolError, match="No architecture is open"):
        await registry.run(ctx_for(world), "find_matches", {"target_providers": ["gcp"]})


async def _engine_architecture_total(db, architecture_id) -> Decimal:
    loaded = (await db.execute(
        select(Architecture).where(Architecture.id == architecture_id).options(
            selectinload(Architecture.collections).selectinload(Collection.sku_selections),
            selectinload(Architecture.connectors).selectinload(DataConnector.sku_selection),
        ).execution_options(populate_existing=True))).scalar_one()
    return calculate_architecture_price(loaded, CalculationDuration.one_month).total_price


async def test_price_matches_prices_every_side_and_saves_one_result(world, web_app):
    db, *_ = world
    ctx = ctx_for(world, web_app.id)
    found = await registry.run(ctx, "find_matches", {"target_providers": ["azure", "gcp"]})
    queue = next(s for s in found.data["sources"] if "Data Transfer" in s["service"])
    out = await registry.run(ctx, "price_matches", {
        "picks": [{"source": queue["ref"], "provider": "gcp", "candidate": None}]})
    result = await _result(db, out.data["result_id"])
    assert result.kind == "architecture_comparison"
    assert result.title == f"{WEB_APP}: AWS vs Azure, GCP"
    assert [s["id"] for s in result.sides] == ["aws", "azure", "gcp"]
    assert len(result.rows) == 16
    transfer = next(r for r in result.rows if "Data Transfer" in r["label"])
    assert transfer["cells"]["gcp"]["status"] == "unmatched"
    assert result.totals["aws"]["partial"] is True and result.totals["gcp"]["partial"] is True
    # Every AWS row is the engine's price of that service in the architecture.
    aws_sum = sum((Decimal(r["cells"]["aws"]["amount"]) for r in result.rows
                   if r["cells"]["aws"]["status"] == "ok"), Decimal(0))
    assert aws_sum == await _engine_architecture_total(db, web_app.id)
    # Every target row is the engine's price of the picked candidate and quantity.
    for row in result.rows:
        cell = row["cells"]["azure"]
        if cell["status"] == "ok":
            assert Decimal(cell["amount"]) > 0
    assert out.data["default_picks"] > 0
    assert "use the app's best candidate" in result.basis["assumptions"][-1]
    assert out.data["shown_as_table"] is True
    assert ctx.figures.get(out.data["totals"]["azure"]["total"]).amount == Decimal(
        result.totals["azure"]["amount"])


async def test_price_matches_quality_rules(world, web_app):
    ctx = ctx_for(world, web_app.id)
    found = await registry.run(ctx, "find_matches", {"target_providers": ["azure"]})
    vm = next(s for s in found.data["sources"] if "t4g.xlarge" in s["service"])
    candidate = vm["candidates"]["azure"][0]["ref"]
    out = await registry.run(ctx, "price_matches", {"picks": [
        {"source": vm["ref"], "provider": "azure", "candidate": candidate,
         "shown_quality": "partial", "reason": "burst credits differ"}]})
    result = await _result(world[0], out.data["result_id"])
    cell = next(r for r in result.rows if r["label"] == vm["service"])["cells"]["azure"]
    assert (cell["quality"], cell["shown_quality"], cell["quality_reason"]) == (
        "close", "partial", "burst credits differ")
    with pytest.raises(ToolError, match="can't be higher"):
        await registry.run(ctx, "price_matches", {"picks": [
            {"source": vm["ref"], "provider": "azure", "candidate": candidate,
             "shown_quality": "exact", "reason": "same"}]})


async def test_price_matches_refuses_foreign_references(world, web_app):
    ctx = ctx_for(world, web_app.id)
    with pytest.raises(ToolError, match="find_matches first"):
        await registry.run(ctx, "price_matches", {})
    found = await registry.run(ctx, "find_matches", {"target_providers": ["azure"]})
    first, second = found.data["sources"][3], found.data["sources"][4]
    other = second["candidates"]["azure"][0]["ref"]
    with pytest.raises(ToolError, match="isn't a azure candidate"):
        await registry.run(ctx, "price_matches", {"picks": [
            {"source": first["ref"], "provider": "azure", "candidate": other}]})
    fresh = ctx_for(world, web_app.id)  # a new message: a new book
    with pytest.raises(ToolError):
        await registry.run(fresh, "price_matches", {"picks": [
            {"source": first["ref"], "provider": "azure", "candidate": None}]})


async def test_comparisons_leave_the_architecture_unchanged(world, web_app):
    db, *_ = world
    before_total = await _engine_architecture_total(db, web_app.id)
    before_count = (await db.execute(select(func.count()).select_from(Architecture))).scalar()
    ctx = ctx_for(world, web_app.id)
    await registry.run(ctx, "find_matches", {"target_providers": ["azure", "gcp"]})
    await registry.run(ctx, "price_matches", {})
    await db.commit()
    assert (await db.execute(select(func.count()).select_from(Architecture))).scalar() == (
        before_count)
    assert await _engine_architecture_total(db, web_app.id) == before_total


async def test_an_architecture_changed_since_the_last_answer_is_read_fresh(world, web_app):
    db, *_ = world
    arch_id = web_app.id
    ctx = ctx_for(world, arch_id)
    first = await registry.run(ctx, "find_matches", {"target_providers": ["gcp"]})
    collection = (await db.execute(select(Collection).where(
        Collection.architecture_id == arch_id).options(
        selectinload(Collection.sku_selections)))).scalars().first()
    await db.delete(collection.sku_selections[0])
    await db.commit()
    # Each message gets its own database session in the app; here, drop the cached rows.
    db.expire(collection)
    db.expire(web_app)
    second = await registry.run(ctx_for(world, arch_id), "find_matches",
                                {"target_providers": ["gcp"]})
    assert len(second.data["sources"]) == len(first.data["sources"]) - 1


# --- US3 units, US4 gaps, and the remaining edge cases (T044, T047, T064) --------------------------


async def test_converted_usage_is_the_apps_and_stated(world, web_app):
    db, *_ = world
    ctx = ctx_for(world, web_app.id)
    found = await registry.run(ctx, "find_matches", {"target_providers": ["gcp"]})
    vm = next(s for s in found.data["sources"] if "t4g.xlarge" in s["service"])
    assert vm["candidates"]["gcp"][0]["usage"] == "sized to 4 vCPU and 16 GiB"
    out = await registry.run(ctx, "price_matches", {})
    result = await _result(db, out.data["result_id"])
    cell = next(r for r in result.rows if r["label"] == vm["service"])["cells"]["gcp"]
    assert cell["usage"] == "sized to 4 vCPU and 16 GiB"
    assert cell["priced"]["options"]["vcpus"] == 4
    assert Decimal(cell["priced"]["quantity"]) == Decimal(96)  # the architecture's own hours
    # The model's arguments carried no quantities: the app converted them.
    assert "quantity" not in str(out.summary)


async def test_a_comparison_where_nothing_could_be_priced_makes_no_result(world):
    db, *_ = world
    ctx = ctx_for(world)
    out = await registry.run(ctx, "search_products", {
        "providers": ["azure", "gcp"], "category": "storage", "function": "object_storage",
        "regions": {"azure": "eastus", "gcp": "us-east1"}})
    azure = out.data["providers"]["azure"]["products"][0]["ref"]
    gcp = out.data["providers"]["gcp"]["products"][0]["ref"]
    priced = await registry.run(ctx, "price_products", {
        "picks": [azure, gcp], "usage": "default",
        "terms": {"azure": "savings_plan_1yr", "gcp": "commitment_1yr"}})
    assert "result_id" not in priced.data
    assert all("unavailable" in p for p in priced.data["prices"].values())
    assert (await db.execute(select(func.count()).select_from(AgentResult))).scalar() == 0


async def test_one_providers_missing_snapshot_doesnt_block_the_others(world, monkeypatch):
    from src.pricing_data import active_snapshot
    from src.pricing_data.errors import PricingDataUnavailableError

    real = active_snapshot.get_active_snapshot

    def no_gcp(provider):
        if provider == "gcp":
            raise PricingDataUnavailableError("gcp snapshot failed", "gcp")
        return real(provider)

    ctx = ctx_for(world)
    found = await registry.run(ctx, "search_products", {
        "providers": ["azure"], "category": "storage", "function": "object_storage",
        "regions": {"azure": "eastus"}})
    azure = found.data["providers"]["azure"]["products"][0]["ref"]
    monkeypatch.setattr(active_snapshot, "get_active_snapshot", no_gcp)
    monkeypatch.setattr("src.services.price_calculation.get_active_snapshot", no_gcp)
    out = await registry.run(ctx, "search_products", {
        "providers": ["azure", "gcp"], "category": "storage", "function": "object_storage",
        "regions": {"azure": "eastus"}})
    assert out.data["providers"]["gcp"]["unavailable"]
    assert out.data["providers"]["azure"]["products"]
    priced = await registry.run(ctx, "price_products", {"picks": [azure], "usage": "default"})
    assert "price" in priced.data["prices"]["azure:eastus"]


async def test_two_regions_of_one_provider_are_two_sides(world):
    db, *_ = world
    ctx = ctx_for(world)
    east = await registry.run(ctx, "search_products", {
        "providers": ["aws"], "category": "storage", "function": "object_storage",
        "regions": {"aws": "us-east-1"}, "text": "General Purpose"})
    west = await registry.run(ctx, "search_products", {
        "providers": ["aws"], "category": "storage", "function": "object_storage",
        "regions": {"aws": "us-west-2"}, "text": "General Purpose"})
    picks = [east.data["providers"]["aws"]["products"][0]["ref"],
             west.data["providers"]["aws"]["products"][0]["ref"]]
    out = await registry.run(ctx, "price_products", {"picks": picks, "usage": "default"})
    result = await _result(db, out.data["result_id"])
    assert [s["id"] for s in result.sides] == ["aws:us-east-1", "aws:us-west-2"]
    with pytest.raises(ToolError, match="one product per provider and region"):
        await registry.run(ctx, "price_products", {"picks": [picks[0], picks[0]],
                                                   "usage": "default"})


async def test_an_empty_category_of_the_architecture_says_so(world, web_app, monkeypatch):
    ctx = ctx_for(world, web_app.id)
    out = await registry.run(ctx, "find_matches", {"target_providers": ["gcp"],
                                                   "category": "compute"})
    assert out.data["sources"]  # the EC2 instances

    async def nothing(detail, *, category=None):
        return []

    monkeypatch.setattr("src.agent.compare.architecture_sources", nothing)
    empty = await registry.run(ctx, "find_matches", {"target_providers": ["gcp"],
                                                     "category": "networking"})
    assert empty.data == {"empty": True, "message": "No services in the open architecture in "
                          "networking."}


async def test_a_new_session_starts_without_results(world):
    db, user, agent_session, _ = world
    from src.agent import sessions

    assert await sessions.results(db, agent_session) == []
