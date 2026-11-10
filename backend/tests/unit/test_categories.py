"""Service categories (019, T064, research R9, data-model §2)."""

from __future__ import annotations

import json
import os

import pytest
from alembic import command

from src.ops.db import _alembic_config
from src.services.categories import Categorizer, Rule, load_categorizer
from tests.helpers.pg import execute, scratch_database

RULES = [
    Rule("aws", "service_code", "AmazonEC2", "compute", 0),
    Rule("aws", "product_family", "Storage", "storage", 10),
    Rule("aws", "service_code", "AmazonS3", "storage", 0),
    Rule("azure", "service_family", "Compute", "compute", 0),
    Rule("azure", "service_name", "Bandwidth", "networking", 10),
    Rule("gcp", "taxonomy_1", "Compute", "compute", 0),
    Rule("gcp", "taxonomy_2", "Persistent Disk", "storage", 10),
]


@pytest.mark.parametrize(
    ("provider", "key", "category"),
    [
        ("aws", "AmazonEC2|Compute Instance", "compute"),
        ("aws", "AmazonEC2|Storage", "storage"),  # the product family rule outranks
        ("aws", "AmazonS3|Storage", "storage"),
        ("aws", "AmazonSES|Sending", None),  # uncategorized
        ("azure", "Compute|Virtual Machines", "compute"),
        ("azure", "Networking|Bandwidth", "networking"),
        ("azure", "Compute|Bandwidth", "networking"),
        ("gcp", "Compute|GCE", "compute"),
        ("gcp", "Compute|Persistent Disk", "storage"),
        ("gcp", "Marketplace|Other", None),
        # Rules are per provider: an AWS value means nothing for Azure.
        ("azure", "AmazonEC2|Compute Instance", None),
    ],
)
def test_rules_match_per_provider_and_priority_wins(provider, key, category):
    assert Categorizer(RULES).category_of(provider, key) == category


def test_keys_for_a_category_and_all():
    categorizer = Categorizer(RULES)
    keys = ["AmazonEC2|Compute Instance", "AmazonEC2|Storage", "AmazonSES|Sending"]
    assert categorizer.keys_for("aws", "compute", keys) == {"AmazonEC2|Compute Instance"}
    assert categorizer.keys_for("aws", "storage", keys) == {"AmazonEC2|Storage"}
    assert categorizer.keys_for("aws", "all", keys) == set(keys)  # uncategorized included


@pytest.mark.asyncio
async def test_the_seeded_rules_are_loaded(db_session):
    categorizer = await load_categorizer(db_session)
    assert categorizer.category_of("aws", "AmazonRDS|Database Instance") == "database"
    assert categorizer.category_of("azure", "Storage|Storage") == "storage"
    assert categorizer.category_of("gcp", "Network|Egress") == "networking"


def test_the_seed_loads_idempotently():
    seed = json.loads(open("src/db/seed/service_categories.json").read())["rules"]
    with scratch_database(os.environ["DATABASE_URL"]) as url:
        command.upgrade(_alembic_config(url), "head")
        command.downgrade(_alembic_config(url), "9b1f6e2c4d06")
        assert execute(url, "SELECT count(*) FROM service_category_rules") == [(0,)]
        command.upgrade(_alembic_config(url), "head")
        assert execute(url, "SELECT count(*) FROM service_category_rules") == [(len(seed),)]
        # Re-running the seed keeps a rule already present as it is.
        command.downgrade(_alembic_config(url), "9b1f6e2c4d06")
        execute(url, "INSERT INTO service_category_rules (id, provider, match_field, "
                     "match_value, category, priority) VALUES (gen_random_uuid(), 'aws', "
                     "'service_code', 'AmazonEC2', 'storage', 5)")
        command.upgrade(_alembic_config(url), "head")
        assert execute(url, "SELECT category, priority FROM service_category_rules "
                            "WHERE provider = 'aws' AND match_value = 'AmazonEC2'") == [
            ("storage", 5)
        ]
        assert execute(url, "SELECT count(*) FROM service_category_rules") == [(len(seed),)]
