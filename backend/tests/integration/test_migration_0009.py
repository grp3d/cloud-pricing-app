"""Migration 0009 (022, contracts/migration-0009.md): the GCP and Azure standard architectures
are inserted once, public, under the default Admin, from the checked-in seed files, with
`provider_options`; the AWS four are left alone. It needs no pricing data at run time."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest
from alembic import command

from src.ops.db import _alembic_config
from tests.helpers.pg import execute, scratch_database

TEST_DATABASE_URL = os.environ["DATABASE_URL"]
REV_0008 = "6c3e9a1b5f08"
REV_0009 = "9b4e2c7a1d05"
SEED_DIR = Path(__file__).resolve().parents[2] / "src" / "db" / "seed"


def _seed(provider: str) -> dict:
    return json.loads((SEED_DIR / f"standard_architectures_{provider}.json").read_text())


def _admin(url: str):
    return execute(url, "SELECT id FROM users WHERE is_default_admin LIMIT 1")[0][0]


def _admin_architectures(url: str) -> list[tuple[str, str, bool]]:
    return sorted(
        tuple(row)
        for row in execute(
            url,
            "SELECT a.provider, a.name, a.is_public FROM architectures a "
            "JOIN users u ON u.id = a.user_id WHERE u.is_default_admin AND a.deleted_at IS NULL",
        )
    )


@pytest.fixture
def db_at_0008(monkeypatch):
    # The migration reads only the seed files: no pricing data at run time (spec edge case).
    monkeypatch.delenv("PRICING_DATA_URI", raising=False)
    with scratch_database(TEST_DATABASE_URL) as url:
        command.upgrade(_alembic_config(url), REV_0008)
        yield url


def test_inserts_the_eight_public_admin_architectures_with_the_seeds_contents(db_at_0008):
    url = db_at_0008
    aws_before = [r for r in _admin_architectures(url) if r[0] == "aws"]
    assert len(aws_before) == 4

    command.upgrade(_alembic_config(url), REV_0009)

    rows = _admin_architectures(url)
    assert [r for r in rows if r[0] == "aws"] == aws_before
    for provider in ("gcp", "azure"):
        seed = _seed(provider)
        assert [r for r in rows if r[0] == provider] == sorted(
            (provider, a["name"], True) for a in seed["architectures"]
        )
        for architecture in seed["architectures"]:
            stored = execute(
                url,
                "SELECT c.name, c.region, s.service_code, s.sku, s.usage_quantity, "
                "s.provider_options FROM architectures a "
                "JOIN collections c ON c.architecture_id = a.id "
                "JOIN sku_selections s ON s.collection_id = c.id "
                "WHERE a.provider = %s AND a.name = %s ORDER BY s.created_at",
                (provider, architecture["name"]),
            )
            expected = [
                (
                    c["name"],
                    c["region"],
                    s["service_code"],
                    s["sku"],
                    s["usage_quantity"],
                    s.get("provider_options"),
                )
                for c in architecture["collections"]
                for s in c["sku_selections"]
            ]
            actual = [
                (name, region, code, sku, f"{qty:.4f}", options)
                for name, region, code, sku, qty, options in stored
            ]
            assert actual == expected, f"{provider} {architecture['name']}"


def test_no_default_admin_inserts_nothing(db_at_0008):
    url = db_at_0008
    execute(url, "UPDATE users SET is_default_admin = false")
    command.upgrade(_alembic_config(url), REV_0009)
    count = execute(url, "SELECT count(*) FROM architectures WHERE provider IN ('gcp', 'azure')")
    assert count[0][0] == 0


def test_skips_a_same_name_same_provider_architecture_only(db_at_0008):
    """FR-008: the existence check is name *and* provider, among non-deleted architectures."""
    url = db_at_0008
    owner = _admin(url)
    name = "Serverless Microservices Back-End"
    execute(
        url,
        "INSERT INTO architectures (id, user_id, name, provider, is_public) "
        "VALUES (%s, %s, %s, 'gcp', false)",
        (uuid.uuid4(), owner, name),
    )
    # A deleted Azure one with the name doesn't block the Azure insert.
    execute(
        url,
        "INSERT INTO architectures (id, user_id, name, provider, is_public, deleted_at) "
        "VALUES (%s, %s, %s, 'azure', false, now())",
        (uuid.uuid4(), owner, name),
    )

    command.upgrade(_alembic_config(url), REV_0009)

    gcp = [r for r in _admin_architectures(url) if r[0] == "gcp"]
    azure = [r for r in _admin_architectures(url) if r[0] == "azure"]
    assert len(gcp) == 4  # the pre-existing private one + 3 inserted
    assert ("gcp", name, False) in gcp
    assert len(azure) == 4 and all(public for _p, _n, public in azure)


def test_downgrade_removes_only_the_gcp_and_azure_ones_and_upgrade_restores_them(db_at_0008):
    url = db_at_0008
    command.upgrade(_alembic_config(url), REV_0009)
    command.downgrade(_alembic_config(url), REV_0008)
    rows = _admin_architectures(url)
    assert {r[0] for r in rows} == {"aws"} and len(rows) == 4
    command.upgrade(_alembic_config(url), REV_0009)
    assert len(_admin_architectures(url)) == 12
