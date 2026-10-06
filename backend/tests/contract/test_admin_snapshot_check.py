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


@pytest.mark.asyncio
async def test_a_second_request_before_the_first_check_starts_gets_409(
    client, admin_headers, monkeypatch
):
    """Two clicks in quick succession: the second must not queue another check, even though
    the first one hasn't taken the monitor lock yet (Copilot review, finding 7)."""
    import threading

    release = threading.Event()
    calls: list[bool] = []

    def slow_run_check(*, at_startup=False):
        calls.append(at_startup)
        release.wait(timeout=5)

    monkeypatch.setattr(active_snapshot, "run_check", slow_run_check)
    try:
        first = await client.post("/api/v1/admin/pricing-snapshot/check", headers=admin_headers)
        second = await client.post("/api/v1/admin/pricing-snapshot/check", headers=admin_headers)
        assert first.status_code == 202
        assert second.status_code == 409
    finally:
        release.set()
    for _ in range(50):
        await asyncio.sleep(0.02)
        third = await client.post("/api/v1/admin/pricing-snapshot/check", headers=admin_headers)
        if third.status_code == 202:
            break
    assert third.status_code == 202  # once the first finishes, a new check can start
    release.set()
