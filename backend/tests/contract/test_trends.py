"""GET /trends/series (019, T068, contracts §8)."""

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
