"""Migration 0012 (025-agent-architecture-changes, data-model.md §4): `agent_proposals`, with its
cascades from sessions and messages, the per-session sequence and the kind, status and undo
checks."""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest
from alembic import command

from src.ops.db import _alembic_config
from tests.helpers.pg import execute, scratch_database

TEST_DATABASE_URL = os.environ["DATABASE_URL"]
REV_0011 = "7c3e9a1f4d62"
REV_0012 = "b81d5e0c2a47"


@pytest.fixture
def db_at_0012(monkeypatch):
    monkeypatch.delenv("PRICING_DATA_URI", raising=False)
    with scratch_database(TEST_DATABASE_URL) as url:
        command.upgrade(_alembic_config(url), REV_0011)
        command.upgrade(_alembic_config(url), REV_0012)
        yield url


def _session_and_message(url: str) -> tuple[uuid.UUID, uuid.UUID]:
    user_id, session_id, message_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    execute(url, "INSERT INTO users (id, username) VALUES (%s, %s)", (user_id, f"u-{user_id}"))
    execute(url, "INSERT INTO agent_sessions (id, user_id, started_at, closes_at) "
                 "VALUES (%s, %s, now(), now() + interval '3 days')", (session_id, user_id))
    execute(url, "INSERT INTO agent_messages (id, session_id, seq, role, content, status, "
                 "is_preview) VALUES (%s, %s, 1, 'user', 'q', 'answered', false)",
            (message_id, session_id))
    return session_id, message_id


def _add(url: str, session_id, message_id, seq: int = 1, kind: str = "change",
         status: str = "pending", undo_status: str | None = None) -> uuid.UUID:
    proposal_id = uuid.uuid4()
    execute(url, "INSERT INTO agent_proposals (id, session_id, message_id, seq, kind, title, "
                 "status, undo_status) VALUES (%s, %s, %s, %s, %s, 't', %s, %s)",
            (proposal_id, session_id, message_id, seq, kind, status, undo_status))
    return proposal_id


def _count(url: str) -> int:
    return execute(url, "SELECT count(*) FROM agent_proposals")[0][0]


def test_creates_agent_proposals_with_json_defaults(db_at_0012):
    url = db_at_0012
    session_id, message_id = _session_and_message(url)
    proposal_id = _add(url, session_id, message_id)
    row = execute(url, "SELECT items, cost, assumptions, base_state, target_state, "
                       "created_at IS NOT NULL FROM agent_proposals WHERE id = %s",
                  (proposal_id,))[0]
    assert tuple(row) == ([], {}, [], None, {}, True)


def test_seq_is_unique_per_session_and_values_are_checked(db_at_0012):
    url = db_at_0012
    session_id, message_id = _session_and_message(url)
    _add(url, session_id, message_id, seq=1)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _add(url, session_id, message_id, seq=1)
    for bad in ({"kind": "delete"}, {"status": "maybe"}, {"undo_status": "sometimes"}):
        with pytest.raises(psycopg.errors.CheckViolation):
            _add(url, session_id, message_id, seq=2, **bad)
    _add(url, session_id, message_id, seq=2, kind="create", status="accepted",
         undo_status="available")
    _add(url, session_id, message_id, seq=3, kind="import", status="superseded")


def test_deleting_the_message_or_the_session_removes_proposals(db_at_0012):
    url = db_at_0012
    session_id, message_id = _session_and_message(url)
    _add(url, session_id, message_id)
    execute(url, "DELETE FROM agent_messages WHERE id = %s", (message_id,))
    assert _count(url) == 0

    session_id, message_id = _session_and_message(url)
    _add(url, session_id, message_id)
    execute(url, "DELETE FROM agent_sessions WHERE id = %s", (session_id,))
    assert _count(url) == 0


def test_downgrade_drops_the_table(db_at_0012):
    url = db_at_0012
    command.downgrade(_alembic_config(url), REV_0011)
    tables = {r[0] for r in execute(
        url, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}
    assert "agent_proposals" not in tables
