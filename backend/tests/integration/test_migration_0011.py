"""Migration 0011 (024-agent-pricing-questions, data-model.md §1): `agent_results`, with its
cascades from sessions and messages, the per-session sequence and the kind check."""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest
from alembic import command

from src.ops.db import _alembic_config
from tests.helpers.pg import execute, scratch_database

TEST_DATABASE_URL = os.environ["DATABASE_URL"]
REV_0010 = "4f7a2c9e1b30"
REV_0011 = "7c3e9a1f4d62"


@pytest.fixture
def db_at_0010(monkeypatch):
    monkeypatch.delenv("PRICING_DATA_URI", raising=False)
    with scratch_database(TEST_DATABASE_URL) as url:
        command.upgrade(_alembic_config(url), REV_0010)
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


def _add_result(url: str, session_id, message_id, seq: int = 1,
                kind: str = "architecture_comparison") -> uuid.UUID:
    result_id = uuid.uuid4()
    execute(url, "INSERT INTO agent_results (id, session_id, message_id, seq, kind, title, "
                 "summary) VALUES (%s, %s, %s, %s, %s, 't', 's')",
            (result_id, session_id, message_id, seq, kind))
    return result_id


def _count(url: str) -> int:
    return execute(url, "SELECT count(*) FROM agent_results")[0][0]


def test_creates_agent_results_with_json_defaults(db_at_0010):
    url = db_at_0010
    command.upgrade(_alembic_config(url), REV_0011)
    session_id, message_id = _session_and_message(url)
    result_id = _add_result(url, session_id, message_id)
    row = execute(url, "SELECT basis, sides, rows, totals, snapshots, created_at IS NOT NULL "
                       "FROM agent_results WHERE id = %s", (result_id,))[0]
    assert tuple(row) == ({}, [], [], {}, {}, True)


def test_seq_is_unique_per_session_and_kind_is_checked(db_at_0010):
    url = db_at_0010
    command.upgrade(_alembic_config(url), REV_0011)
    session_id, message_id = _session_and_message(url)
    _add_result(url, session_id, message_id, seq=1)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _add_result(url, session_id, message_id, seq=1)
    with pytest.raises(psycopg.errors.CheckViolation):
        _add_result(url, session_id, message_id, seq=2, kind="something_else")
    _add_result(url, session_id, message_id, seq=2, kind="category_comparison")


def test_deleting_the_message_or_the_session_removes_results(db_at_0010):
    url = db_at_0010
    command.upgrade(_alembic_config(url), REV_0011)
    session_id, message_id = _session_and_message(url)
    _add_result(url, session_id, message_id, seq=1)
    execute(url, "DELETE FROM agent_messages WHERE id = %s", (message_id,))
    assert _count(url) == 0

    session_id, message_id = _session_and_message(url)
    _add_result(url, session_id, message_id, seq=1)
    execute(url, "DELETE FROM agent_sessions WHERE id = %s", (session_id,))
    assert _count(url) == 0


def test_downgrade_drops_the_table(db_at_0010):
    url = db_at_0010
    command.upgrade(_alembic_config(url), REV_0011)
    command.downgrade(_alembic_config(url), REV_0010)
    tables = {r[0] for r in execute(
        url, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}
    assert "agent_results" not in tables
