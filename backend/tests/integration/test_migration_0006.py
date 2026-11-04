"""Migration 0006 (019, T014; data-model §1–§5) on real Postgres: upgrade from 0005 keeps every
existing row and gives the new columns their defaults; downgrade to 0005 works.
Constitution V: Postgres read/write, test-first."""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest
from alembic import command

from src.ops.db import _alembic_config, alembic_revision, connect
from tests.helpers.pg import execute, scratch_database

TEST_DATABASE_URL = os.environ["DATABASE_URL"]
REV_0005 = "7c2e9d41b8a3"
REV_0006 = "9b1f6e2c4d06"


def _seed_0005_rows(url: str) -> dict[str, uuid.UUID]:
    """One architecture with two collections, a connector and two selections, at 0005."""
    ids = {name: uuid.uuid4() for name in ("arch", "a", "b", "conn", "sel", "csel")}
    owner = execute(url, "SELECT id FROM users WHERE is_default_admin LIMIT 1")[0][0]
    execute(url, "INSERT INTO architectures (id, user_id, name, provider, is_public) "
                 "VALUES (%s, %s, %s, 'aws', false)", (ids["arch"], owner, "Before 0006"))
    for key, name in (("a", "A"), ("b", "B")):
        execute(url, "INSERT INTO collections (id, architecture_id, type, name, region) "
                     "VALUES (%s, %s, 'application_component', %s, 'us-east-1')",
                (ids[key], ids["arch"], name))
    execute(url, "INSERT INTO data_connectors (id, architecture_id, from_collection_id, "
                 "to_collection_id) VALUES (%s, %s, %s, %s)",
            (ids["conn"], ids["arch"], ids["a"], ids["b"]))
    execute(url, "INSERT INTO sku_selections (id, collection_id, service_code, sku, pricing_term, "
                 "purchase_option, usage_quantity) VALUES (%s, %s, 'AmazonEC2', 'SKU1', "
                 "'on_demand', 'not_applicable', 24)", (ids["sel"], ids["a"]))
    execute(url, "INSERT INTO sku_selections (id, connector_id, service_code, sku, pricing_term, "
                 "purchase_option, usage_quantity) VALUES (%s, %s, 'AWSDataTransfer', 'SKU2', "
                 "'on_demand', 'not_applicable', 10)", (ids["csel"], ids["conn"]))
    return ids


@pytest.fixture
def db_at_0005():
    with scratch_database(TEST_DATABASE_URL) as url:
        command.upgrade(_alembic_config(url), REV_0005)
        yield url


def test_upgrade_keeps_rows_and_sets_defaults(db_at_0005):
    url = db_at_0005
    ids = _seed_0005_rows(url)
    command.upgrade(_alembic_config(url), REV_0006)

    assert execute(url, "SELECT name FROM architectures WHERE id = %s", (ids["arch"],)) == [
        ("Before 0006",)
    ]
    assert execute(
        url, "SELECT arrow_style, arrow_reversed FROM data_connectors WHERE id = %s", (ids["conn"],)
    ) == [("none", False)]
    assert execute(
        url, "SELECT provider_options, usage_quantity FROM sku_selections WHERE id = %s",
        (ids["sel"],),
    ) == [(None, 24)]
    tables = {r[0] for r in execute(url, "SELECT tablename FROM pg_tables WHERE schemaname='public'")}
    assert {"user_preferences", "service_category_rules", "connector_branches"} <= tables


def test_widened_columns_and_checks(db_at_0005):
    url = db_at_0005
    ids = _seed_0005_rows(url)
    command.upgrade(_alembic_config(url), REV_0006)

    for term in ("savings_plan_1yr", "savings_plan_3yr", "commitment_1yr", "commitment_3yr"):
        execute(url, "UPDATE sku_selections SET pricing_term = %s WHERE id = %s",
                (term, ids["sel"]))
    execute(url, "UPDATE collections SET region = 'northamerica-northeast1' WHERE id = %s",
            (ids["a"],))  # 23 characters
    with pytest.raises(psycopg.errors.CheckViolation):
        execute(url, "UPDATE sku_selections SET pricing_term = 'spot' WHERE id = %s",
                (ids["sel"],))
    with pytest.raises(psycopg.errors.CheckViolation):
        execute(url, "UPDATE data_connectors SET arrow_style = 'zigzag' WHERE id = %s",
                (ids["conn"],))
    with pytest.raises(psycopg.errors.CheckViolation):
        execute(url, "INSERT INTO service_category_rules (id, provider, match_field, match_value, "
                     "category, priority) VALUES (%s, 'aws', 'service_code', 'X', 'food', 0)",
                (uuid.uuid4(),))


def test_branches_cascade_with_their_connector(db_at_0005):
    url = db_at_0005
    ids = _seed_0005_rows(url)
    command.upgrade(_alembic_config(url), REV_0006)
    execute(url, "INSERT INTO connector_branches (id, connector_id, collection_id) "
                 "VALUES (%s, %s, %s)", (uuid.uuid4(), ids["conn"], ids["b"]))
    execute(url, "DELETE FROM sku_selections WHERE connector_id = %s", (ids["conn"],))
    execute(url, "DELETE FROM data_connectors WHERE id = %s", (ids["conn"],))
    assert execute(url, "SELECT count(*) FROM connector_branches") == [(0,)]


def test_preferences_are_deleted_with_their_user(db_at_0005):
    url = db_at_0005
    command.upgrade(_alembic_config(url), REV_0006)
    user = uuid.uuid4()
    execute(url, "INSERT INTO users (id, is_active, is_admin, is_default_admin) "
                 "VALUES (%s, true, false, false)", (user,))  # a guest: no username
    execute(url, "INSERT INTO user_preferences (user_id) VALUES (%s)", (user,))
    assert execute(url, "SELECT data, schema_version FROM user_preferences") == [({}, 1)]
    execute(url, "DELETE FROM users WHERE id = %s", (user,))
    assert execute(url, "SELECT count(*) FROM user_preferences") == [(0,)]


def test_downgrade_to_0005_restores_the_old_schema(db_at_0005):
    url = db_at_0005
    ids = _seed_0005_rows(url)
    command.upgrade(_alembic_config(url), REV_0006)
    command.downgrade(_alembic_config(url), REV_0005)

    with connect(url, autocommit=True) as conn:
        assert alembic_revision(conn) == REV_0005
    tables = {r[0] for r in execute(url, "SELECT tablename FROM pg_tables WHERE schemaname='public'")}
    assert not {"user_preferences", "service_category_rules", "connector_branches"} & tables
    columns = {r[0] for r in execute(
        url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'data_connectors'"
    )}
    assert "arrow_style" not in columns
    assert execute(url, "SELECT count(*) FROM sku_selections WHERE id IN (%s, %s)",
                   (ids["sel"], ids["csel"])) == [(2,)]
    with pytest.raises(psycopg.errors.CheckViolation):
        execute(url, "UPDATE sku_selections SET pricing_term = 'commitment_1yr' WHERE id = %s",
                (ids["sel"],))
