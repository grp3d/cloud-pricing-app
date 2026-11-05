"""Migration 0008 (019, FR-026): connectors that existed before 019 keep their arrowhead
(`none` → `one_way`); a reversed or already styled connector is left alone."""

from __future__ import annotations

import os
import uuid

import pytest
from alembic import command

from src.ops.db import _alembic_config
from tests.helpers.pg import execute, scratch_database

TEST_DATABASE_URL = os.environ["DATABASE_URL"]
REV_0007 = "4d8a2f7c9e07"
REV_0008 = "6c3e9a1b5f08"


@pytest.fixture
def db_at_0007():
    with scratch_database(TEST_DATABASE_URL) as url:
        command.upgrade(_alembic_config(url), REV_0007)
        yield url


def test_existing_connectors_become_one_way(db_at_0007):
    url = db_at_0007
    owner = execute(url, "SELECT id FROM users WHERE is_default_admin LIMIT 1")[0][0]
    arch, a, b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    execute(url, "INSERT INTO architectures (id, user_id, name, provider, is_public) "
                 "VALUES (%s, %s, 'Before 0008', 'aws', false)", (arch, owner))
    for cid, name in ((a, "A"), (b, "B")):
        execute(url, "INSERT INTO collections (id, architecture_id, type, name, region) "
                     "VALUES (%s, %s, 'application_component', %s, 'us-east-1')",
                (cid, arch, name))
    rows = {"plain": ("none", False), "two_way": ("two_way", False), "reversed": ("none", True)}
    ids = {key: uuid.uuid4() for key in rows}
    for key, (style, reversed_) in rows.items():
        execute(url, "INSERT INTO data_connectors (id, architecture_id, from_collection_id, "
                     "to_collection_id, arrow_style, arrow_reversed) "
                     "VALUES (%s, %s, %s, %s, %s, %s)",
                (ids[key], arch, a, b, style, reversed_))

    command.upgrade(_alembic_config(url), REV_0008)

    def style(key):
        return execute(url, "SELECT arrow_style FROM data_connectors WHERE id = %s",
                       (ids[key],))[0][0]

    assert (style("plain"), style("two_way"), style("reversed")) == ("one_way", "two_way", "none")
    command.downgrade(_alembic_config(url), REV_0007)
    assert style("plain") == "one_way"  # downgrade leaves styles as they are
