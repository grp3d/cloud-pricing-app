"""Migration 0010 (023-agent-foundation, data-model.md §1–§6): the agent tables and the three
per-user agent columns, with their defaults, cascades and constraints."""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest
from alembic import command

from src.ops.db import _alembic_config
from tests.helpers.pg import execute, scratch_database

TEST_DATABASE_URL = os.environ["DATABASE_URL"]
REV_0009 = "9b4e2c7a1d05"
REV_0010 = "4f7a2c9e1b30"
AGENT_TABLES = ("agent_settings", "agent_sessions", "agent_messages", "agent_operations",
                "agent_usage")


def _tables(url: str) -> set[str]:
    return {r[0] for r in execute(
        url, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    )}


@pytest.fixture
def db_at_0009(monkeypatch):
    monkeypatch.delenv("PRICING_DATA_URI", raising=False)
    with scratch_database(TEST_DATABASE_URL) as url:
        command.upgrade(_alembic_config(url), REV_0009)
        yield url


def _named_user(url: str) -> uuid.UUID:
    user_id = uuid.uuid4()
    execute(url, "INSERT INTO users (id, username) VALUES (%s, %s)", (user_id, f"u-{user_id}"))
    return user_id


def test_adds_the_tables_and_user_columns_with_defaults(db_at_0009):
    url = db_at_0009
    existing = _named_user(url)
    command.upgrade(_alembic_config(url), REV_0010)

    assert set(AGENT_TABLES) <= _tables(url)
    row = execute(
        url,
        "SELECT agent_enabled_for_user, agent_preview_input_counter, agent_monthly_input_limit "
        "FROM users WHERE id = %s",
        (existing,),
    )[0]
    assert tuple(row) == (False, 3, None)


def test_agent_settings_holds_one_row_only(db_at_0009):
    url = db_at_0009
    command.upgrade(_alembic_config(url), REV_0010)
    execute(url, "INSERT INTO agent_settings (id) VALUES (1)")
    with pytest.raises(psycopg.errors.CheckViolation):
        execute(url, "INSERT INTO agent_settings (id) VALUES (2)")


def test_one_session_per_user_and_deleting_it_keeps_usage(db_at_0009):
    url = db_at_0009
    command.upgrade(_alembic_config(url), REV_0010)
    user_id = _named_user(url)
    session_id, message_id = uuid.uuid4(), uuid.uuid4()
    execute(
        url,
        "INSERT INTO agent_sessions (id, user_id, started_at, closes_at) "
        "VALUES (%s, %s, now(), now() + interval '3 days')",
        (session_id, user_id),
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        execute(
            url,
            "INSERT INTO agent_sessions (id, user_id, started_at, closes_at) "
            "VALUES (%s, %s, now(), now() + interval '3 days')",
            (uuid.uuid4(), user_id),
        )
    execute(
        url,
        "INSERT INTO agent_messages (id, session_id, seq, role, content, status, is_preview) "
        "VALUES (%s, %s, 1, 'user', 'hi', 'answered', true)",
        (message_id, session_id),
    )
    execute(
        url,
        "INSERT INTO agent_operations (id, session_id, message_id, seq, name, inputs, outcome, "
        "summary, started_at, duration_ms) VALUES (%s, %s, %s, 1, 'describe_open_architecture', "
        "'{}', 'ok', '{}', now(), 3)",
        (uuid.uuid4(), session_id, message_id),
    )
    execute(
        url,
        "INSERT INTO agent_usage (id, user_id, session_id, message_id, provider, model, "
        "input_tokens, output_tokens, cost_usd, counts_as_input, is_preview) VALUES "
        "(%s, %s, %s, %s, 'ollama', 'llama3.1', 10, 5, 0, true, true)",
        (uuid.uuid4(), user_id, session_id, message_id),
    )

    execute(url, "DELETE FROM agent_sessions WHERE id = %s", (session_id,))

    assert execute(url, "SELECT count(*) FROM agent_messages")[0][0] == 0
    assert execute(url, "SELECT count(*) FROM agent_operations")[0][0] == 0
    usage = execute(url, "SELECT session_id, message_id FROM agent_usage")
    assert len(usage) == 1 and usage[0][0] is None and usage[0][1] == message_id


def test_preview_counter_and_limit_cannot_be_negative(db_at_0009):
    url = db_at_0009
    command.upgrade(_alembic_config(url), REV_0010)
    user_id = _named_user(url)
    for column in ("agent_preview_input_counter", "agent_monthly_input_limit"):
        with pytest.raises(psycopg.errors.CheckViolation):
            execute(url, f"UPDATE users SET {column} = -1 WHERE id = %s", (user_id,))


def test_downgrade_removes_everything(db_at_0009):
    url = db_at_0009
    command.upgrade(_alembic_config(url), REV_0010)
    command.downgrade(_alembic_config(url), REV_0009)
    assert not set(AGENT_TABLES) & _tables(url)
    columns = {r[0] for r in execute(
        url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'users'"
    )}
    assert not {c for c in columns if c.startswith("agent_")}
