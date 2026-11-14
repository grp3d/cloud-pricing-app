"""The result CSV route (024, FR-020, FR-021): the caller's own result only, as CSV with the
same rows and figures as the session detail."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta

from src.models.orm import AgentMessage, AgentResult, AgentSession, User


async def _user_with_result(db, *, expired=False) -> tuple[dict, uuid.UUID]:
    user = User(id=uuid.uuid4(), username=f"u-{uuid.uuid4().hex[:6]}")
    db.add(user)
    await db.flush()
    now = datetime.now(UTC)
    started = now - timedelta(days=4) if expired else now
    session = AgentSession(user_id=user.id, started_at=started,
                           closes_at=started + timedelta(days=3))
    db.add(session)
    await db.flush()
    message = AgentMessage(session_id=session.id, seq=1, role="user", content="q",
                           status="answered")
    db.add(message)
    await db.flush()
    result = AgentResult(
        session_id=session.id, message_id=message.id, seq=1, kind="category_comparison",
        title="Object storage: Azure vs GCP", summary="1 row",
        basis={"question_kind": "category", "category": "storage", "duration": "1_month",
               "reference_side": "azure:eastus", "usage": "1 TB stored"},
        sides=[{"id": "azure:eastus", "provider": "azure", "region": "eastus",
                "term": "on_demand"},
               {"id": "gcp:us-east1", "provider": "gcp", "region": "us-east1",
                "region_guessed": True, "term": "on_demand"}],
        rows=[{"label": "Object storage", "cells": {
            "azure:eastus": {"product": "Hot LRS", "amount": "18.4321"},
            "gcp:us-east1": {"product": "Standard", "quality": "close", "amount": "20.005",
                             "diff": "1.5729", "diff_pct": "8.533"}}}],
        totals={"azure:eastus": {"amount": "18.4321"},
                "gcp:us-east1": {"amount": "20.005", "diff": "1.5729", "diff_pct": "8.533"}},
        snapshots={"azure": {"date": "2026-11-02", "revision": 2},
                   "gcp": {"date": "2026-11-02", "revision": 2}})
    db.add(result)
    await db.commit()
    return {"Authorization": f"Bearer {user.id}"}, result.id


def _url(result_id) -> str:
    return f"/api/v1/agent/session/results/{result_id}/csv"


async def test_downloads_the_callers_result_as_csv(client, db_session):
    headers, result_id = await _user_with_result(db_session)
    response = await client.get(_url(result_id), headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == (
        'attachment; filename="comparison-object-storage-azure-vs-gcp-'
        f'{datetime.now(UTC).date().isoformat()}.csv"')
    text = response.content.decode("utf-8")
    assert text.startswith("﻿")
    rows = list(csv.reader(io.StringIO(text[1:])))
    row = next(r for r in rows if r and r[0] == "Object storage")
    assert row == ["Object storage", "Hot LRS", "18.43", "Standard", "close", "20.01", "1.57",
                   "8.5", ""]
    detail = (await client.get("/api/v1/agent/session", headers=headers)).json()
    assert detail["results"][0]["rows"][0]["cells"]["gcp:us-east1"]["amount"] == "20.005"


async def test_another_users_or_an_expired_result_is_404(client, db_session):
    _theirs, result_id = await _user_with_result(db_session)
    mine, _ = await _user_with_result(db_session)
    assert (await client.get(_url(result_id), headers=mine)).status_code == 404
    assert (await client.get(_url(uuid.uuid4()), headers=mine)).status_code == 404
    expired_headers, expired_id = await _user_with_result(db_session, expired=True)
    assert (await client.get(_url(expired_id), headers=expired_headers)).status_code == 404


async def test_guests_cant_download(client, auth_headers):
    response = await client.get(_url(uuid.uuid4()), headers=auth_headers)
    assert response.status_code == 403
