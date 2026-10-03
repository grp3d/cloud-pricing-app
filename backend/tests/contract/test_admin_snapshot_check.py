"""`POST /admin/pricing-snapshot/check` (018-app-cloud-deployment, FR-012;
contracts/admin-api.md): admin-only, starts one check now, 409 while one is running."""

from __future__ import annotations

import asyncio

import pytest

from src.pricing_data import active_snapshot


@pytest.mark.asyncio
async def test_non_admin_is_rejected(client, auth_headers):
    resp = await client.post("/api/v1/admin/pricing-snapshot/check", headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_starts_a_check(client, admin_headers, monkeypatch):
    ran = asyncio.Event()
    calls: list[bool] = []

    def fake_run_check(*, at_startup=False):
        calls.append(at_startup)
        ran.set()

    monkeypatch.setattr(active_snapshot, "run_check", fake_run_check)
    resp = await client.post("/api/v1/admin/pricing-snapshot/check", headers=admin_headers)
    assert resp.status_code == 202
    assert resp.json() == {"started": True}
    await asyncio.wait_for(ran.wait(), timeout=5)
    assert calls == [False]


@pytest.mark.asyncio
async def test_a_running_check_answers_409(client, admin_headers):
    with active_snapshot._lock:  # a check in progress holds the monitor lock
        resp = await client.post("/api/v1/admin/pricing-snapshot/check", headers=admin_headers)
    assert resp.status_code == 409
    assert resp.json() == {"error": "check_in_progress"}
