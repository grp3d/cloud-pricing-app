"""The GCP adapter against the T005 fixture (019, T033; research R4 to R8). Expected prices are
the fixture README's."""

from __future__ import annotations

import dataclasses
import shutil
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from src.pricing_data.active_snapshot import get_active_snapshot
from src.pricing_data.providers.gcp import GcpProvider
from src.pricing_data.providers.tiers import (
    UnpriceableTierError,
    normalize_tiers,
    price_for_duration,
)

N2_CORE, N2_RAM = "BB77-5FDA-69D9", "5B01-D157-A097"
EGRESS = "F274-1692-F213"
LICENCE = "92D2-8A8F-DF54"
COMPUTE = "6F81-5844-456A"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "pricing_parquet"

gcp = GcpProvider()
N2_STANDARD_4 = {"kind": "gcp_machine", "version": 1, "vcpus": 4, "memory_gib": 16,
                 "ram_sku": N2_RAM}


@pytest.fixture
def snap():
    return get_active_snapshot("gcp")


def _price(snap, item, term="on_demand", **kw):
    return gcp.price(snap, item=item, pricing_term=term, purchase_option="not_applicable",
                     region="us-east1", **kw)


def test_locations_exclude_global(snap):
    assert gcp.locations(snap) == ["us-east1"]


@pytest.mark.parametrize(
    ("term", "rate"),
    [("on_demand", "0.194236"), ("commitment_1yr", "0.13984992"),
     ("commitment_3yr", "0.10488744")],
)
def test_gcp_machine_is_cores_plus_ram(snap, term, rate):
    quote = _price(snap, N2_CORE, term, options=N2_STANDARD_4)
    assert [t.rate for t in quote.tiers] == [Decimal(rate)]
    assert quote.unit == "h"
    assert [(c.label, c.sku, c.multiplier) for c in quote.components] == [
        ("vCPUs", N2_CORE, 4), ("Memory (GiB)", N2_RAM, 16)
    ]


def test_commitment_prices_of_one_sku(snap):
    assert [t.rate for t in _price(snap, N2_CORE, "commitment_1yr").tiers] == [
        Decimal("0.02275992")
    ]
    assert [t.rate for t in _price(snap, N2_CORE, "commitment_3yr").tiers] == [
        Decimal("0.01706994")
    ]
    # Balanced PD publishes no commitment.
    assert _price(snap, "6AE1-525F-8B80", "commitment_1yr") is None
    assert _price(snap, N2_CORE, "reserved_1yr") is None


def test_a_multi_regional_sku_appears_once(snap):
    items, total = gcp.search(snap, region="us-east1", limit=50, offset=0, text="^N2 Instance Core")
    assert (total, [i.sku for i in items]) == (1, [N2_CORE])
    (core,) = items
    assert core.location_scope == "multi_regional"
    assert core.price_types == ("on_demand", "commitment_1yr", "commitment_3yr")
    assert core.service_name == "Compute Engine"
    assert core.product_family == "Compute > GCE > VMs On Demand > Cores: Per Core > N2"
    assert core.unit == "h"


def test_a_global_licensing_sku_is_found_from_the_region(snap):
    items, total = gcp.search(snap, region="us-east1", limit=50, offset=0, text="Licensing Fee")
    assert (total, [i.sku for i in items]) == (1, [LICENCE])
    assert items[0].location_scope == "global"
    assert [t.rate for t in _price(snap, LICENCE).tiers] == [Decimal("0.046")]


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("vm", {N2_CORE}),
        ("block_storage", {"6AE1-525F-8B80", "0FE3-CAB9-E7E3"}),
        ("object_storage", {"E5F0-6A5D-7BAD", "0D5D-6E23-4250", "420D-7730-6B64",
                            "1CAF-511D-F4EA"}),
        ("data_transfer", {EGRESS}),
        ("managed_db", {"965E-7C36-08E6", "93DA-3F55-CB04"}),
    ],
)
def test_kind_filters(snap, kind, expected):
    items, _ = gcp.search(snap, region="us-east1", limit=50, offset=0, kind=kind)
    assert {i.sku for i in items} == expected


def test_vm_cores_carry_their_ram_sku(snap):
    (core,) = gcp.search(snap, region="us-east1", limit=5, offset=0, kind="vm")[0]
    assert core.attributes["ram_sku"] == N2_RAM


def test_egress_tiers_by_start_amount(snap):
    quote = _price(snap, EGRESS)
    tiers = normalize_tiers(quote.tiers)
    assert [(t.start_quantity, t.rate) for t in tiers] == [
        (0, 0), (1, Decimal("0.12")), (1024, Decimal("0.11")), (10240, Decimal("0.08"))
    ]
    month = price_for_duration(tiers, Decimal(500) / 31, quote.unit, 31, quote.unit_class)
    assert month.cost == pytest.approx(Decimal("59.88"), abs=Decimal("1e-20"))


def test_describe_and_exists(snap):
    keys = [(COMPUTE, N2_CORE), (COMPUTE, "0000-0000-0000"), ("other", N2_CORE)]
    assert set(gcp.describe(snap, keys, region="us-east1")) == {(COMPUTE, N2_CORE)}
    assert gcp.exists(snap, keys, region="us-east1") == {(COMPUTE, N2_CORE)}


def test_null_list_price_is_unpriceable(tmp_path, snap):
    """No real row has a null price, so this test writes its own: the same snapshot, read from
    a copy whose Balanced PD price is null."""
    root = tmp_path / "root"
    shutil.copytree(FIXTURE_ROOT, root)
    (path,) = (root / "gcp" / "parquet" / "sku_price_tier").glob("*/region=us-east1/*.parquet")
    source = tmp_path / "source.parquet"
    shutil.move(path, source)
    with duckdb.connect() as con:
        con.execute(
            "COPY (SELECT * REPLACE (CASE WHEN sku_id = '6AE1-525F-8B80' THEN NULL "
            f"ELSE list_price END AS list_price) FROM read_parquet('{source}')) "
            f"TO '{path}' (FORMAT parquet)"
        )

    copy = dataclasses.replace(snap, base_dir=root)
    quote = gcp.price(copy, item="6AE1-525F-8B80", pricing_term="on_demand",
                      purchase_option="not_applicable", region="us-east1")
    assert quote.tiers[0].rate is None
    with pytest.raises(UnpriceableTierError, match="not published"):
        price_for_duration(normalize_tiers(quote.tiers), Decimal(10), quote.unit, 31,
                           quote.unit_class)
