"""Migration 0013 (026-agent-cross-cloud-translation, data-model.md §1–§2): `service_mappings`,
seeded once from the generated files, and the `translate` proposal kind with its `translation`
record."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import psycopg
import pytest
from alembic import command

from src.ops.db import _alembic_config
from tests.helpers.pg import execute, scratch_database

TEST_DATABASE_URL = os.environ["DATABASE_URL"]
REV_0012 = "b81d5e0c2a47"
REV_0013 = "c4f2a9d8e1b3"
SEED_DIR = Path(__file__).resolve().parents[2] / "src" / "db" / "seed"


def _seed_rows() -> int:
    return sum(len(json.loads((SEED_DIR / f"service_mappings_{p}.json").read_text())["mappings"])
               for p in ("gcp", "azure"))


@pytest.fixture
def db_at_0013(monkeypatch):
    monkeypatch.delenv("PRICING_DATA_URI", raising=False)
    with scratch_database(TEST_DATABASE_URL) as url:
        command.upgrade(_alembic_config(url), REV_0012)
        command.upgrade(_alembic_config(url), REV_0013)
        yield url


def _count(url: str) -> int:
    return execute(url, "SELECT count(*) FROM service_mappings")[0][0]


def test_seeds_every_mapping_row_once(db_at_0013):
    url = db_at_0013
    assert _count(url) == _seed_rows() > 0
    providers = {r[0] for r in execute(url, "SELECT DISTINCT target_provider FROM "
                                            "service_mappings")}
    assert providers == {"gcp", "azure"}
    row = execute(url, "SELECT version, origin, source_provider FROM service_mappings LIMIT 1")[0]
    assert tuple(row) == (1, "seed_022", "aws")


def test_reapplying_inserts_nothing_twice(db_at_0013):
    url = db_at_0013
    command.downgrade(_alembic_config(url), REV_0012)
    command.upgrade(_alembic_config(url), REV_0013)
    assert _count(url) == _seed_rows()


def test_mapping_constraints(db_at_0013):
    url = db_at_0013
    insert = ("INSERT INTO service_mappings (id, version, source_provider, source_key, "
              "target_provider, alternative, part, target_key, omit_reason, origin) "
              "VALUES (%s, 1, %s, 'k', %s, 1, 1, %s, %s, 'seed_022')")
    with pytest.raises(psycopg.errors.CheckViolation):  # neither a target nor a reason
        execute(url, insert, (uuid.uuid4(), "aws", "gcp", None, None))
    with pytest.raises(psycopg.errors.CheckViolation):  # both
        execute(url, insert, (uuid.uuid4(), "aws", "gcp", "t", "r"))
    with pytest.raises(psycopg.errors.CheckViolation):  # same provider
        execute(url, insert, (uuid.uuid4(), "aws", "aws", "t", None))
    execute(url, insert, (uuid.uuid4(), "aws", "gcp", "t", None))
    with pytest.raises(psycopg.errors.UniqueViolation):
        execute(url, insert, (uuid.uuid4(), "aws", "gcp", "t2", None))


def test_translate_kind_and_translation_record(db_at_0013):
    url = db_at_0013
    user_id, session_id, message_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    execute(url, "INSERT INTO users (id, username) VALUES (%s, %s)", (user_id, f"u-{user_id}"))
    execute(url, "INSERT INTO agent_sessions (id, user_id, started_at, closes_at) "
                 "VALUES (%s, %s, now(), now() + interval '3 days')", (session_id, user_id))
    execute(url, "INSERT INTO agent_messages (id, session_id, seq, role, content, status, "
                 "is_preview) VALUES (%s, %s, 1, 'user', 'q', 'answered', false)",
            (message_id, session_id))
    proposal_id = uuid.uuid4()
    execute(url, "INSERT INTO agent_proposals (id, session_id, message_id, seq, kind, title, "
                 "translation) VALUES (%s, %s, %s, 1, 'translate', 't', %s)",
            (proposal_id, session_id, message_id, json.dumps({"rows": []})))
    row = execute(url, "SELECT translation FROM agent_proposals WHERE id = %s", (proposal_id,))
    assert row[0][0] == {"rows": []}
    with pytest.raises(psycopg.errors.CheckViolation):
        execute(url, "INSERT INTO agent_proposals (id, session_id, message_id, seq, kind, "
                     "title) VALUES (%s, %s, %s, 2, 'move', 't')",
                (uuid.uuid4(), session_id, message_id))


def test_downgrade_removes_both(db_at_0013):
    url = db_at_0013
    command.downgrade(_alembic_config(url), REV_0012)
    tables = execute(url, "SELECT count(*) FROM information_schema.tables "
                          "WHERE table_name = 'service_mappings'")[0][0]
    columns = execute(url, "SELECT count(*) FROM information_schema.columns "
                           "WHERE table_name = 'agent_proposals' AND column_name = "
                           "'translation'")[0][0]
    assert (tables, columns) == (0, 0)
