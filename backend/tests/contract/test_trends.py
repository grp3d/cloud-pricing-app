"""GET /trends/series and GET /trends/movers (019, T068, T084, contracts §8)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from src.config import settings
from src.pricing_data.history.service import history_store
from tests.helpers.history import build_trends_history

URL = "/api/v1/trends/series"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "pricing_parquet"


@pytest.fixture
def history_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "pricing_history_dir", str(tmp_path / "history"))
    return tmp_path / "history"


@pytest.fixture
def aws_history(history_dir):
    return build_trends_history(history_dir)


async def _get(client, headers, **params):
    return await client.get(URL, params=params, headers=headers)


@pytest.mark.asyncio
async def test_response_shape(client, auth_headers, aws_history):
    resp = await _get(client, auth_headers, select="aws:us-east-1,us-west-2")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["metric"], body["category"]) == ("skus_changed", "all")
    (series,) = body["series"]
    assert (series["provider"], series["regions"], series["status"]) == (
        "aws", ["us-east-1", "us-west-2"], "ok")
    assert (series["weeks_built"], series["weeks_total"]) == (4, 4)
    last = series["points"][-1]
    assert last == {
        "week": "2026-10-12", "from_snapshot": "2026-10-05 r1", "to_snapshot": "2026-10-12 r1",
        "increased": 1, "decreased": 1, "increased_pct": 10.0, "decreased_pct": 10.0,
        "compared": 10, "excluded": 1, "gap": False,
    }
    assert [p["gap"] for p in series["points"]] == [False, False, True, False]


@pytest.mark.asyncio
async def test_category_uses_the_seeded_rules(client, auth_headers, aws_history):
    body = (await _get(client, auth_headers, select="aws:us-east-1", category="storage")).json()
    assert body["category"] == "storage"
    assert [p["compared"] for p in body["series"][0]["points"]] == [2, 2, 2, 2]
    net = (await _get(client, auth_headers, select="aws:us-east-1",
                      category="networking")).json()
    # The TIER SKU is AWSDataTransfer, seeded as networking.
    assert [p["decreased"] for p in net["series"][0]["points"]] == [0, 0, 0, 1]


@pytest.mark.asyncio
async def test_several_providers_and_statuses(client, auth_headers, aws_history, history_dir):
    history_store("gcp").update_state(backfill="done", weeks_built=0, weeks_total=0)
    body = (await client.get(URL, headers=auth_headers, params=[
        ("select", "aws:"), ("select", "gcp:us-east1"), ("select", "azure:")])).json()
    by = {s["provider"]: s for s in body["series"]}
    assert by["aws"]["regions"] == [] and by["aws"]["status"] == "ok"
    assert by["gcp"]["status"] == "not_enough_history" and by["gcp"]["points"] == []
    # Azure's history has never been built here: it is still building, 0 of 0 weeks.
    assert by["azure"]["status"] == "building"


@pytest.mark.asyncio
async def test_building_returns_the_weeks_built_so_far(client, auth_headers, aws_history):
    aws_history.update_state(backfill="running", weeks_built=4, weeks_total=10)
    (series,) = (await _get(client, auth_headers, select="aws:")).json()["series"]
    assert (series["status"], series["weeks_built"], series["weeks_total"]) == (
        "building", 4, 10)
    assert len(series["points"]) == 4


@pytest.mark.asyncio
async def test_a_provider_without_a_snapshot_is_unavailable(
    client, auth_headers, history_dir, use_pricing_root, tmp_path
):
    root = tmp_path / "root"
    shutil.copytree(FIXTURE_ROOT, root)
    shutil.rmtree(root / "azure")
    use_pricing_root(root)
    (series,) = (await _get(client, auth_headers, select="azure:")).json()["series"]
    assert (series["status"], series["reason"]) == ("provider_unavailable", "no snapshot available")


@pytest.mark.asyncio
async def test_weeks_limits_the_points(client, auth_headers, aws_history):
    (series,) = (await _get(client, auth_headers, select="aws:", weeks=2)).json()["series"]
    assert [p["week"] for p in series["points"]] == ["2026-10-05", "2026-10-12"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [{}, {"select": "oracle:"}, {"select": "aws:", "category": "food"},
     {"select": "aws:", "weeks": 53}, {"select": "aws:", "metric": "price_trend", "weeks": 0}],
)
async def test_bad_queries_are_422(client, auth_headers, params):
    assert (await _get(client, auth_headers, **params)).status_code == 422


@pytest.mark.asyncio
async def test_requires_an_identity(client):
    assert (await client.get(URL, params={"select": "aws:"})).status_code == 401


# --- GET /trends/movers (T084) --------------------------------------------------------------

MOVERS = "/api/v1/trends/movers"


async def _movers(client, headers, **params):
    return await client.get(MOVERS, params=params, headers=headers)


@pytest.mark.asyncio
async def test_movers_response_shape(client, auth_headers, aws_history):
    resp = await _movers(client, auth_headers, provider="aws")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {k: body[k] for k in ("provider", "category", "regions", "period_weeks", "status",
                                 "from_snapshot", "to_snapshot", "weeks_available",
                                 "message")} == {
        "provider": "aws", "category": "all", "regions": [], "period_weeks": 52, "status": "ok",
        "from_snapshot": "2026-09-07 r1", "to_snapshot": "2026-10-12 r1", "weeks_available": 5,
        "message": None,
    }
    rise = body["increases"][0]
    # Prices are decimal strings as published; % change to 2 decimal places.
    assert {k: rise[k] for k in ("region", "start_price", "end_price", "change_pct",
                                 "tier_note")} == {
        "region": "us-east-1", "start_price": "0.1", "end_price": "0.11", "change_pct": 10.0,
        "tier_note": None,
    }
    assert rise["service_name"] and rise["description"] and rise["unit"]
    assert [m["change_pct"] for m in body["increases"]] == [10.0, 8.33]
    assert [m["change_pct"] for m in body["decreases"]] == [-10.0, -5.56]
    assert body["decreases"][1]["tier_note"] == "Compared on the first non-zero tier"


@pytest.mark.asyncio
async def test_movers_filters(client, auth_headers, aws_history):
    body = (await _movers(client, auth_headers, provider="aws", regions="us-west-2",
                          period_weeks=13)).json()
    assert body["regions"] == ["us-west-2"]
    assert [m["region"] for m in body["increases"]] == ["us-west-2"]
    week = (await _movers(client, auth_headers, provider="aws", period_weeks=1)).json()
    assert (week["from_snapshot"], week["weeks_available"]) == ("2026-10-05 r1", 1)
    # The TIER SKU is AWSDataTransfer, seeded as networking.
    net = (await _movers(client, auth_headers, provider="aws", category="networking")).json()
    assert [m["change_pct"] for m in net["decreases"]] == [-5.56] and net["increases"] == []


@pytest.mark.asyncio
async def test_movers_message_when_nothing_changed(client, auth_headers, aws_history):
    body = (await _movers(client, auth_headers, provider="aws", category="database")).json()
    assert (body["increases"], body["decreases"]) == ([], [])
    assert body["message"] == "No price changes in this period"


@pytest.mark.asyncio
async def test_movers_without_history(client, auth_headers, history_dir):
    history_store("gcp").update_state(backfill="done", weeks_built=0, weeks_total=0)
    body = (await _movers(client, auth_headers, provider="gcp")).json()
    assert (body["status"], body["weeks_available"], body["from_snapshot"]) == (
        "not_enough_history", 0, None)
    assert body["message"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [{}, {"provider": "oracle"}, {"provider": "aws", "period_weeks": 2},
     {"provider": "aws", "period_weeks": 0}, {"provider": "aws", "category": "food"}],
)
async def test_bad_movers_queries_are_422(client, auth_headers, params):
    assert (await _movers(client, auth_headers, **params)).status_code == 422


@pytest.mark.asyncio
async def test_movers_requires_an_identity(client):
    assert (await client.get(MOVERS, params={"provider": "aws"})).status_code == 401
