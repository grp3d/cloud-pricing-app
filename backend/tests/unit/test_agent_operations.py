"""The read-only operations (023, research R9, FR-002–FR-007, constitution Principle I): every
figure equals the pricing engine's, and nothing beyond the user's own data is reachable."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.agent.figures import FigureBook
from src.agent.operations import OperationContext, ToolError, registry
from src.models.orm import Architecture, Collection, DataConnector, SKUSelection, User
from src.models.schemas import CalculationDuration
from src.services.price_calculation import calculate_architecture_price
from tests.helpers.agent import STANDARD_PRICING_ROOT, build_standard

WEB_APP = "Active-Standby Multi-Region Web Application"


@pytest.fixture
async def owner(db_session):
    user = User(id=uuid.uuid4(), username=f"o-{uuid.uuid4().hex[:6]}")
    db_session.add(user)
    await db_session.commit()
    return user


def _ctx(db, user, architecture_id) -> OperationContext:
    return OperationContext(session=db, user=user, open_architecture_id=architecture_id,
                            figures=FigureBook())


async def _engine_total(db, architecture_id, duration: str) -> Decimal:
    loaded = (await db.execute(
        select(Architecture).where(Architecture.id == architecture_id).options(
            selectinload(Architecture.collections).selectinload(Collection.sku_selections),
            selectinload(Architecture.connectors).selectinload(DataConnector.sku_selection),
        ).execution_options(populate_existing=True)
    )).scalar_one()
    return calculate_architecture_price(loaded, duration=CalculationDuration(duration)).total_price


@pytest.mark.parametrize("provider", ["aws", "gcp", "azure"])
@pytest.mark.parametrize("duration", ["1_month", "1_year"])
async def test_price_total_is_the_engines(db_session, owner, use_pricing_root, provider,
                                          duration):
    if provider != "aws":
        use_pricing_root(STANDARD_PRICING_ROOT)
    arch = await build_standard(db_session, owner, provider, WEB_APP)
    ctx = _ctx(db_session, owner, arch.id)
    result = await registry.run(ctx, "price_open_architecture", {"duration": duration})

    ref = result.data["total"]
    assert ctx.figures.get(ref).amount == await _engine_total(db_session, arch.id, duration)
    assert result.data["duration"] == duration
    assert result.data["unpriceable"] == []
    snap = result.snapshot[provider]
    assert snap["date"] == result.data["snapshot_date"] and isinstance(snap["revision"], int)
    assert ctx.figures.get(ref).snapshot == result.snapshot


async def test_cost_drivers_rank_services_with_the_same_total(db_session, owner):
    arch = await build_standard(db_session, owner, "aws", WEB_APP)
    ctx = _ctx(db_session, owner, arch.id)
    result = await registry.run(ctx, "cost_drivers", {"duration": "1_month", "top": 3})

    drivers = result.data["drivers"]
    assert len(drivers) == 3
    amounts = [ctx.figures.get(d["price"]).amount for d in drivers]
    assert amounts == sorted(amounts, reverse=True)
    assert all(d["service"] for d in drivers)
    total = ctx.figures.get(result.data["total"]).amount
    assert total == await _engine_total(db_session, arch.id, "1_month")
    rest = ctx.figures.get(result.data["all_other_services"]).amount
    assert sum(amounts) + rest == total


async def test_unpriceable_services_are_named(db_session, owner):
    arch = await build_standard(db_session, owner, "aws", WEB_APP)
    collection = (await db_session.execute(
        select(Collection).where(Collection.architecture_id == arch.id))).scalars().first()
    db_session.add(SKUSelection(collection_id=collection.id, service_code="AmazonEC2",
                                sku="NOSUCHSKU", pricing_term="on_demand",
                                purchase_option="not_applicable", usage_quantity=Decimal(1)))
    await db_session.commit()
    result = await registry.run(_ctx(db_session, owner, arch.id), "price_open_architecture",
                                {"duration": "1_month"})
    (item,) = result.data["unpriceable"]
    assert item["service_code"] == "AmazonEC2" and item["sku"] == "NOSUCHSKU"
    assert item["where"] == [collection.name]
    assert result.data["total_excludes_unpriceable"] is True


async def test_describe_returns_collections_and_services(db_session, owner):
    arch = await build_standard(db_session, owner, "aws", WEB_APP)
    result = await registry.run(_ctx(db_session, owner, arch.id),
                                "describe_open_architecture", {})
    data = result.data
    assert data["name"] == WEB_APP and data["provider"] == "aws"
    assert data["collections"] and all({"name", "type", "region", "services"} <= set(c)
                                       for c in data["collections"])
    service = data["collections"][0]["services"][0]
    assert {"service", "sku", "quantity", "price_type"} <= set(service)
    # Describing gives no figures.
    assert not any(k in str(data) for k in ("$", "price\": \"F"))


async def test_another_users_architecture_is_not_reachable(db_session, owner):
    other = User(id=uuid.uuid4(), username="someone-else")
    db_session.add(other)
    await db_session.commit()
    theirs = await build_standard(db_session, other, "aws", WEB_APP, public=True)
    for name, args in [("describe_open_architecture", {}),
                       ("price_open_architecture", {"duration": "1_month"}),
                       ("cost_drivers", {"duration": "1_month"})]:
        with pytest.raises(ToolError, match="isn't available"):
            await registry.run(_ctx(db_session, owner, theirs.id), name, args)


@pytest.mark.parametrize("name", ["describe_open_architecture", "price_open_architecture",
                                  "cost_drivers"])
async def test_nothing_open(db_session, owner, name):
    with pytest.raises(ToolError, match="No architecture is open"):
        await registry.run(_ctx(db_session, owner, None), name, {})


async def test_empty_architecture_has_nothing_to_price(db_session, owner):
    arch = Architecture(user_id=owner.id, name="Empty", provider="aws")
    db_session.add(arch)
    await db_session.commit()
    result = await registry.run(_ctx(db_session, owner, arch.id), "price_open_architecture",
                                {"duration": "1_month"})
    assert result.data == {"empty": True, "message": "The open architecture has no services."}


def test_durations_are_the_apps_three():
    spec = next(s for s in registry.tool_specs() if s.name == "price_open_architecture")
    assert spec.input_schema["properties"]["duration"]["enum"] == ["1_day", "1_month", "1_year"]


async def test_importable_list_matches_the_import_list(db_session, owner):
    from src.services.importable import importable_architectures

    other = User(id=uuid.uuid4(), username="zoe")
    db_session.add(other)
    await db_session.commit()
    await build_standard(db_session, other, "aws", WEB_APP, rename="Zoe web", public=True)
    await build_standard(db_session, other, "aws", WEB_APP, rename="Zoe secret", public=False)
    result = await registry.run(_ctx(db_session, owner, None),
                                "list_importable_architectures", {})
    expected = await importable_architectures(db_session, owner)
    assert [(g["owner"], [a["name"] for a in g["architectures"]])
            for g in result.data["groups"]] == [
        (g.owner_username, [a.name for a in g.architectures]) for g in expected.groups
    ]
    assert "Zoe secret" not in str(result.data)
    assert result.data["groups"][-1]["architectures"][0]["provider"] == "aws"
