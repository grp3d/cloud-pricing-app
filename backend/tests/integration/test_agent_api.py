"""The agent routes (023, contracts/agent-api.md), end to end through the app with the scripted
model in place of a real one."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from src.agent.clients.scripted import ScriptedModelClient, Turn
from src.agent.model import ModelUnreachable, Usage
from src.models.orm import AgentMessage, AgentSession, AgentSettings, AgentUsage, User


def events_of(text: str) -> list[dict]:
    return [json.loads(line[len("data: "):]) for line in text.splitlines()
            if line.startswith("data: ")]


@pytest.fixture
async def named(db_session):
    async def make(enabled_for_user=False, preview=3) -> dict[str, str]:
        user = User(id=uuid.uuid4(), username=f"u-{uuid.uuid4().hex[:6]}",
                    agent_enabled_for_user=enabled_for_user,
                    agent_preview_input_counter=preview)
        db_session.add(user)
        await db_session.commit()
        return {"Authorization": f"Bearer {user.id}"}

    return make


@pytest.fixture
async def agent_on(db_session):
    db_session.add(AgentSettings(id=1, agent_enabled=True, agent_provider="ollama",
                                 agent_model="test-model"))
    await db_session.commit()


@pytest.fixture
def script(monkeypatch):
    """Replace the model with a script for the next answers."""
    def use(*turns: Turn) -> ScriptedModelClient:
        client = ScriptedModelClient(list(turns))
        monkeypatch.setattr("src.api.agent.build_client", lambda effective: client)
        return client

    return use


async def _start(client, headers):
    response = await client.post("/api/v1/agent/session", json={}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _send(client, headers, content="What is open?", architecture_id=None):
    return await client.post(
        "/api/v1/agent/session/messages",
        json={"content": content, "architecture_id": architecture_id}, headers=headers,
    )


# --- basics (T022) ----------------------------------------------------------------------------


async def test_guests_are_never_offered_the_agent(client, auth_headers, agent_on):
    status = await client.get("/api/v1/agent/status", headers=auth_headers)
    assert status.json()["enabled"] is False
    assert status.json()["reason"] == "guest"
    for method, path in [("post", "/api/v1/agent/session"), ("get", "/api/v1/agent/session"),
                         ("post", "/api/v1/agent/session/messages"),
                         ("get", "/api/v1/agent/session/operations")]:
        kwargs = {"json": {"content": "x"}} if method == "post" else {}
        response = await getattr(client, method)(path, headers=auth_headers, **kwargs)
        assert response.status_code == 403, path


async def test_agent_off_by_default(client, named):
    headers = await named()
    status = (await client.get("/api/v1/agent/status", headers=headers)).json()
    assert (status["enabled"], status["available"], status["reason"]) == (
        False, False, "agent_off"
    )


async def test_start_session_and_stream_an_answer(client, named, agent_on, script, db_session):
    headers = await named()
    script(Turn(text=["It has ", "two collections."], usage=Usage(5, 3)))
    session = await _start(client, headers)
    started = datetime.fromisoformat(session["started_at"])
    assert datetime.fromisoformat(session["closes_at"]) - started == timedelta(days=3)

    arch = str(uuid.uuid4())
    response = await _send(client, headers, architecture_id=arch)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = events_of(response.text)
    kinds = [e["event"] for e in events]
    assert kinds[:2] == ["accepted", "status"]
    assert kinds[-1] == "done"
    assert "".join(e["delta"] for e in events if e["event"] == "text") == "It has two collections."
    assert events[0]["is_preview"] is True and events[0]["preview_inputs_left"] == 2

    detail = (await client.get("/api/v1/agent/session", headers=headers)).json()
    assert [(m["role"], m["status"]) for m in detail["messages"]] == [
        ("user", "answered"), ("agent", "complete")
    ]
    assert detail["messages"][0]["architecture_id"] == arch


async def test_no_session_is_404(client, named, agent_on):
    headers = await named()
    assert (await client.get("/api/v1/agent/session", headers=headers)).status_code == 404
    assert (await _send(client, headers)).status_code == 404


# --- failures and retry (US4, T049) -----------------------------------------------------------


async def test_failed_message_can_be_retried_without_a_new_input(client, named, agent_on,
                                                                 script, db_session):
    headers = await named()
    await _start(client, headers)
    script(Turn(raises=ModelUnreachable("down")))
    events = events_of((await _send(client, headers)).text)
    assert events[-1] == {"event": "error", "kind": "unreachable",
                          "message": "The agent's model can't be reached right now."}
    message = (await db_session.execute(select(AgentMessage))).scalar_one()
    assert message.status == "failed"
    user_id = message.session_id
    inputs_before = (await db_session.execute(
        select(AgentUsage).where(AgentUsage.counts_as_input.is_(True)))).scalars().all()

    script(Turn(text=["Back again."]))
    retried = await client.post(f"/api/v1/agent/session/messages/{message.id}/retry",
                                headers=headers)
    assert retried.status_code == 200
    assert events_of(retried.text)[-1]["event"] == "done"
    inputs_after = (await db_session.execute(
        select(AgentUsage).where(AgentUsage.counts_as_input.is_(True)))).scalars().all()
    assert len(inputs_after) == len(inputs_before)
    status = (await client.get("/api/v1/agent/status", headers=headers)).json()
    assert status["preview_inputs_left"] == 2  # only the first send used a preview input
    assert user_id is not None

    again = await client.post(f"/api/v1/agent/session/messages/{message.id}/retry",
                              headers=headers)
    assert again.status_code == 409


async def test_status_is_sent_before_the_model_answers(client, named, agent_on, script):
    """SC-007: a model that never answers still leaves the user with a status at once."""
    headers = await named()
    await _start(client, headers)
    script(Turn(text=["late"], delay_seconds=3))

    async with client.stream("POST", "/api/v1/agent/session/messages",
                             json={"content": "hi"}, headers=headers) as response:
        lines = response.aiter_lines()
        first = []
        while len(first) < 2:
            line = await asyncio.wait_for(anext(lines), timeout=1)
            if line.startswith("data: "):
                first.append(json.loads(line[6:])["event"])
    assert first == ["accepted", "status"]


# --- limits (US6, T060) -----------------------------------------------------------------------


async def test_refusals_are_423_with_the_reason(client, named, agent_on, script, db_session):
    headers = await named(preview=1)
    await _start(client, headers)
    script(Turn(text=["one"]))
    assert (await _send(client, headers)).status_code == 200
    refused = await _send(client, headers)
    assert refused.status_code == 423
    assert refused.json()["detail"] == {"reason": "preview_used", "resets_on": None}
    status = (await client.get("/api/v1/agent/status", headers=headers)).json()
    assert (status["available"], status["reason"], status["preview_inputs_left"]) == (
        False, "preview_used", 0
    )


async def test_global_cap_refusal_has_the_reset_date(client, named, agent_on, db_session):
    headers = await named(enabled_for_user=True)
    await _start(client, headers)
    row = await db_session.get(AgentSettings, 1)
    row.agent_global_monthly_cap_usd = 0
    await db_session.commit()
    refused = await _send(client, headers)
    assert refused.status_code == 423
    detail = refused.json()["detail"]
    assert detail["reason"] == "global_cap" and detail["resets_on"].endswith("-01")


async def test_two_concurrent_sends_with_one_input_left_accept_only_one(client, named,
                                                                        agent_on, script):
    headers = await named(preview=1)
    await _start(client, headers)
    script(Turn(text=["a"]), Turn(text=["b"]))
    first, second = await asyncio.gather(_send(client, headers), _send(client, headers))
    assert sorted([first.status_code, second.status_code]) in ([200, 409], [200, 423])


async def test_deactivated_user_is_refused(client, named, agent_on, db_session):
    headers = await named(enabled_for_user=True)
    await _start(client, headers)
    user_id = uuid.UUID(headers["Authorization"].removeprefix("Bearer "))
    user = await db_session.get(User, user_id)
    user.is_active = False
    await db_session.commit()
    assert (await _send(client, headers)).status_code == 401


# --- sessions (US3, T040) ---------------------------------------------------------------------


async def test_replacing_a_session_needs_confirmation_and_keeps_usage(client, named, agent_on,
                                                                     script, db_session):
    headers = await named(enabled_for_user=True)
    first = await _start(client, headers)
    script(Turn(text=["hi"], usage=Usage(4, 2)))
    await _send(client, headers)

    conflict = await client.post("/api/v1/agent/session", json={"replace": False},
                                 headers=headers)
    assert (conflict.status_code, conflict.json()["detail"]) == (409, "session_exists")
    replaced = await client.post("/api/v1/agent/session", json={"replace": True},
                                 headers=headers)
    assert replaced.status_code == 201 and replaced.json()["id"] != first["id"]

    assert (await db_session.execute(select(AgentMessage))).scalars().all() == []
    usage = (await db_session.execute(select(AgentUsage))).scalars().all()
    assert len(usage) == 1 and usage[0].session_id is None


async def test_an_expired_session_is_gone(client, named, agent_on, db_session):
    headers = await named()
    await _start(client, headers)
    agent_session = (await db_session.execute(select(AgentSession))).scalar_one()
    agent_session.closes_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.commit()
    assert (await client.get("/api/v1/agent/session", headers=headers)).status_code == 404
    assert (await db_session.execute(select(AgentSession))).scalars().all() == []


async def test_sweep_deletes_expired_sessions(db_session, named, agent_on, client):
    from src.agent.sessions import sweep_expired

    headers = await named()
    await _start(client, headers)
    agent_session = (await db_session.execute(select(AgentSession))).scalar_one()
    agent_session.closes_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.commit()
    assert await sweep_expired(db_session, datetime.now(UTC)) == 1


async def test_a_second_send_while_busy_is_409(client, named, agent_on, db_session):
    headers = await named(enabled_for_user=True)
    await _start(client, headers)
    agent_session = (await db_session.execute(select(AgentSession))).scalar_one()
    agent_session.busy_message_id = uuid.uuid4()
    await db_session.commit()
    busy = await _send(client, headers)
    assert (busy.status_code, busy.json()["detail"]) == (409, "busy")


# --- activity log (US7, T066) -----------------------------------------------------------------


async def test_activity_log_lists_operations_in_order(client, named, agent_on, script):
    from src.agent.model import ToolCall

    headers = await named(enabled_for_user=True)
    await _start(client, headers)
    script(Turn(tool_calls=[ToolCall("c1", "no_such_operation", {"x": 1})]),
           Turn(text=["Sorry, I can't."]))
    await _send(client, headers)
    log = (await client.get("/api/v1/agent/session/operations", headers=headers)).json()
    assert [(o["name"], o["outcome"], o["inputs"]) for o in log] == [
        ("no_such_operation", "error", {"x": 1})
    ]
    assert "unknown operation" in log[0]["summary"]["error"]
    assert {"started_at", "duration_ms", "snapshot", "figures_removed"} <= set(log[0])

    other = await named(enabled_for_user=True)
    await _start(client, other)
    assert (await client.get("/api/v1/agent/session/operations", headers=other)).json() == []



# --- the browser closing the stream (found in use: the session stayed busy) --------------------


async def _read_then_close(db_session, monkeypatch, turns, *, stop_after: str):
    """Stream one answer the way the browser does, and stop reading (the browser closing the
    connection) once an event of kind `stop_after` arrives; then let the answer finish."""
    from src.agent import limits
    from src.agent.settings_service import effective_settings
    from src.api import agent as agent_api
    from tests.conftest import TestSessionLocal

    client = ScriptedModelClient(list(turns))
    monkeypatch.setattr("src.api.agent.build_client", lambda effective: client)
    user = User(id=uuid.uuid4(), username=f"u-{uuid.uuid4().hex[:6]}",
                agent_enabled_for_user=True)
    db_session.add(user)
    await db_session.flush()
    now = datetime.now(UTC)
    session = AgentSession(user_id=user.id, started_at=now, closes_at=now + timedelta(days=3))
    db_session.add(session)
    await db_session.commit()
    message = await limits.accept_message(db_session, user, session, "hi", None,
                                          await effective_settings(db_session), now,
                                          usable=True)
    await db_session.commit()

    response = agent_api._stream(TestSessionLocal, user.id, session.id, message.id,
                                 charge_input=True)
    body = response.body_iterator
    async for chunk in body:
        if f'"event":"{stop_after}"' in chunk:
            break
    await body.aclose()  # the stream is gone; nothing more is read from it
    await asyncio.wait_for(asyncio.gather(*agent_api._answers), 10)
    await db_session.refresh(session)
    await db_session.refresh(message)
    return session, message


async def test_session_is_released_when_the_browser_disconnects_after_done(
    client, named, agent_on, script, db_session
):
    """Through the whole app, as uvicorn runs it: the browser disconnects as soon as it has
    "done", and the request-logging middleware then cancels the app's work."""
    from src.api import agent as agent_api
    from src.main import app

    headers = await named(enabled_for_user=True)
    script(Turn(text=["Fine."]))
    session_id = (await _start(client, headers))["id"]
    body = json.dumps({"content": "hi", "architecture_id": None}).encode()
    got_done = asyncio.Event()
    request_sent = False

    async def receive():
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        await got_done.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.body" and b'"event":"done"' in message.get(
            "body", b""
        ):
            got_done.set()

    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"}, "http_version": "1.1",
        "method": "POST", "scheme": "http", "path": "/api/v1/agent/session/messages",
        "raw_path": b"/api/v1/agent/session/messages", "root_path": "", "query_string": b"",
        "headers": [(b"content-type", b"application/json"),
                    (b"authorization", headers["Authorization"].encode())],
        "client": ("127.0.0.1", 1), "server": ("test", 80),
    }
    await asyncio.wait_for(app(scope, receive, send), 10)
    await asyncio.wait_for(asyncio.gather(*agent_api._answers), 10)
    stored = await db_session.get(AgentSession, uuid.UUID(session_id), populate_existing=True)
    assert stored.busy_message_id is None
    follow_up = await _send(client, headers, content="and then?")
    assert follow_up.status_code != 409


async def test_an_answer_the_browser_left_still_finishes_and_is_saved(
    db_session, agent_on, monkeypatch
):
    session, message = await _read_then_close(
        db_session, monkeypatch, [Turn(text=["Saved anyway."], delay_seconds=0.5)],
        stop_after="accepted")
    assert session.busy_message_id is None
    assert message.status == "answered"
    replies = (await db_session.execute(
        select(AgentMessage).where(AgentMessage.session_id == session.id,
                                   AgentMessage.role == "agent")
    )).scalars().all()
    assert [r.content for r in replies] == ["Saved anyway."]


# --- 024: results (contracts/agent-api.md) -------------------------------------------------------


@pytest.fixture
def result_operation(monkeypatch):
    """A registry whose one operation saves a comparison result, like price_matches does."""
    from pydantic import BaseModel

    from src.agent import operations as ops
    from src.models.orm import AgentResult

    class NoArgs(BaseModel):
        pass

    registry = ops.Registry()

    @registry.operation("makes_result", "Saves a result.", NoArgs)
    async def makes_result(ctx, args):
        result = AgentResult(
            session_id=ctx.agent_session.id, message_id=ctx.message.id, seq=1,
            kind="category_comparison", title="Object storage: Azure vs GCP", summary="1 row",
            basis={"question_kind": "category", "category": "storage", "duration": "1_month",
                   "reference_side": "azure:eastus", "usage": "1 TB stored"},
            sides=[{"id": "azure:eastus", "provider": "azure", "region": "eastus",
                    "term": "on_demand"},
                   {"id": "gcp:us-east1", "provider": "gcp", "region": "us-east1",
                    "region_guessed": True, "term": "on_demand"}],
            rows=[{"label": "Object storage", "cells": {
                "azure:eastus": {"product": "Hot LRS", "amount": "18.4"},
                "gcp:us-east1": {"product": "Standard", "quality": "close", "amount": "20",
                                 "diff": "1.6", "diff_pct": "8.6956"}}}],
            totals={"azure:eastus": {"amount": "18.4"},
                    "gcp:us-east1": {"amount": "20", "diff": "1.6", "diff_pct": "8.6956"}},
            snapshots={"azure": {"date": "2026-11-02", "revision": 2}})
        ctx.session.add(result)
        await ctx.session.flush()
        ctx.results.append(result)
        return ops.OperationResult(data={"result_id": str(result.id)}, summary={})

    monkeypatch.setattr(ops, "registry", registry)
    return registry


async def test_a_result_is_streamed_and_returned_with_the_session(
        client, named, agent_on, script, result_operation):
    from src.agent.model import ToolCall

    headers = await named()
    script(Turn(tool_calls=[ToolCall("c1", "makes_result", {})], usage=Usage(5, 3)),
           Turn(text=["GCP is a little dearer."], usage=Usage(5, 3)))
    await _start(client, headers)
    events = events_of((await _send(client, headers, "storage on Azure vs GCP?")).text)
    kinds = [e["event"] for e in events]
    assert kinds[kinds.index("operation") + 1] == "result"
    streamed = next(e for e in events if e["event"] == "result")["result"]
    assert streamed["title"] == "Object storage: Azure vs GCP"
    assert streamed["sides"][1]["region_guessed"] is True

    detail = (await client.get("/api/v1/agent/session", headers=headers)).json()
    assert [r["id"] for r in detail["results"]] == [streamed["id"]]
    user, agent = detail["messages"]
    assert (user["result_ids"], agent["result_ids"]) == ([], [streamed["id"]])


async def test_a_result_made_before_a_failure_is_kept_on_the_question(
        client, named, agent_on, script, result_operation):
    from src.agent.model import ToolCall

    headers = await named()
    script(Turn(tool_calls=[ToolCall("c1", "makes_result", {})], usage=Usage(5, 3)),
           Turn(raises=ModelUnreachable("down")))
    await _start(client, headers)
    events = events_of((await _send(client, headers, "storage?")).text)
    assert events[-1]["event"] == "error"
    detail = (await client.get("/api/v1/agent/session", headers=headers)).json()
    assert len(detail["results"]) == 1
    [user] = detail["messages"]
    assert (user["status"], user["result_ids"]) == ("failed", [detail["results"][0]["id"]])
