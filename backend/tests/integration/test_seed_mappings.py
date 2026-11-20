"""Seed mappings (026, research R3, R4): every mapping's target key finds 022's own SKU in each
region 022 used it, and the lookup returns a source's alternatives, parts and omissions."""

from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pytest

from src.agent.matching import mappings
from src.pricing_data.active_snapshot import get_active_snapshot
from src.pricing_data.providers import keys
from src.pricing_data.providers.registry import get_provider
from tests.helpers.agent import combined_pricing_root

SEED_DIR = Path(__file__).resolve().parents[2] / "src" / "db" / "seed"


def _seed(provider: str) -> dict:
    return json.loads((SEED_DIR / f"service_mappings_{provider}.json").read_text())


def _regions_of_skus(provider: str) -> dict[str, set[str]]:
    """022's provider seed: the regions each SKU is used in."""
    seed = json.loads((SEED_DIR / f"standard_architectures_{provider}.json").read_text())
    regions: dict[str, set[str]] = defaultdict(set)
    for architecture in seed["architectures"]:
        for collection in architecture["collections"]:
            for selection in collection["sku_selections"]:
                regions[selection["sku"]].add(collection["region"])
                ram = (selection.get("provider_options") or {}).get("ram_sku")
                if ram:
                    regions[ram].add(collection["region"])
    return regions


@pytest.mark.parametrize("provider", ["gcp", "azure"])
def test_every_target_key_finds_022s_sku_in_022s_regions(provider, use_pricing_root):
    use_pricing_root(combined_pricing_root())
    adapter = get_provider(provider)
    snapshot = get_active_snapshot(provider)
    regions = _regions_of_skus(provider)
    checked = 0
    for row in _seed(provider)["mappings"]:
        if row["target_key"] is None:
            continue
        for region in sorted(regions[row["target_sku"]]):
            found = keys.find_by_key(adapter, snapshot, region, row["target_key"],
                                     row["target_service_code"])
            assert found is not None, (row["target_key"], region)
            assert found.sku == row["target_sku"], (row["target_key"], region)
            checked += 1
    assert checked >= 20


async def test_lookup_returns_alternatives_parts_and_omissions(db_session):
    glue = await mappings.seed_mappings(db_session, "aws", "aws|AWSGlue|ETL-DPU-Hour|Jobrun",
                                        "gcp")
    assert len(glue) == 1
    [alternative] = glue
    assert [p.part for p in alternative.parts] == [1, 2]
    assert [p.quantity_factor for p in alternative.parts] == [Decimal(4), Decimal(16)]
    assert alternative.omit_reason is None

    storage = await mappings.seed_mappings(db_session, "aws", "aws|AmazonS3|TimedStorage-ByteHrs|",
                                           "azure")
    assert [a.number for a in storage] == [1, 2]

    lcu = await mappings.seed_mappings(db_session, "aws",
                                       "aws|AWSELB|LCUUsage|LoadBalancing:Application", "gcp")
    assert len(lcu) == 1 and lcu[0].parts == []
    assert "LCU-hour" in lcu[0].omit_reason

    assert await mappings.seed_mappings(db_session, "aws", "aws|Nothing|x|", "gcp") == []
    assert await mappings.seed_version(db_session) == 1


# --- Round trip, part 2 (T015, SC-006) -----------------------------------------------------------

REGIONS = {"gcp": {"us-east-1": "us-east1", "us-west-2": "us-west1", "eu-west-1": "europe-west1"},
           "azure": {"us-east-1": "eastus", "us-west-2": "westus2", "eu-west-1": "westeurope"}}


def _selection_key(selection) -> tuple:
    options = dict(selection.get("provider_options") or {})
    return (selection["service_code"], selection["sku"],
            Decimal(selection["usage_quantity"]).quantize(Decimal("0.0001")),
            json.dumps(options, sort_keys=True))


def _state_key(service) -> tuple:
    options = service.provider_options
    if hasattr(options, "model_dump"):
        options = options.model_dump(mode="json")
    options = {k: v for k, v in (options or {}).items() if v is not None}
    if "memory_gib" in options:
        options["memory_gib"] = str(Decimal(str(options["memory_gib"])).normalize())
    return (service.service_code, service.sku,
            Decimal(service.usage_quantity).quantize(Decimal("0.0001")),
            json.dumps(options, sort_keys=True))


def _normal(keys: list[tuple]) -> list[tuple]:
    out = []
    for code, sku, qty, options in keys:
        data = json.loads(options)
        if "memory_gib" in data:
            data["memory_gib"] = str(Decimal(str(data["memory_gib"])).normalize())
        out.append((code, sku, qty, json.dumps(data, sort_keys=True)))
    return sorted(out)


@pytest.mark.parametrize("provider", ["gcp", "azure"])
@pytest.mark.parametrize("name", ["Active-Standby Multi-Region Web Application",
                                  "Modern Data Lake & ETL Analytics Pipeline",
                                  "Serverless Microservices Back-End",
                                  "Containerized Microservices Platform (EKS)"])
async def test_translating_a_standard_architecture_reproduces_022(db_session, use_pricing_root,
                                                                  provider, name):
    from src.agent.operations import registry
    from tests.helpers.agent import build_standard, seed_definition
    from tests.helpers.translation import (
        add_message,
        context,
        log_operation,
        make_world,
    )

    use_pricing_root(combined_pricing_root())
    world = await make_world(db_session)
    architecture = await build_standard(db_session, world[1], "aws", name)
    # 022 used its partial matches; a translation uses a partial match only when the user
    # chooses it after it was offered, so it's offered in one message and chosen in the next.
    first = context(world, architecture.id)
    offered = await registry.run(first, "find_translation", {"provider": provider,
                                                             "regions": REGIONS[provider]})
    await log_operation(db_session, first, "find_translation", offered)
    ctx = context(world, architecture.id, message=await add_message(db_session, world[2], 3))
    found = await registry.run(ctx, "find_translation", {"provider": provider,
                                                          "regions": REGIONS[provider]})
    expected = seed_definition(provider, name)
    expected_by_index = [_normal([_selection_key(s.model_dump(mode="json"))
                                  for s in c.sku_selections]) for c in expected.collections]
    # Where 022 chose among alternatives, pass its choice as a pick (research R4).
    picks = []
    sources = {s["ref"]: s for s in found.data["services"]}
    detail_order = list((await _detail(ctx)).collections)
    where_index = {c.name: i for i, c in enumerate(detail_order)}
    for ref, service in sources.items():
        if service["status"] == "partial_only":
            picks.append({"source": ref, "candidate": service["candidates"][0]["ref"]})
            continue
        if service["status"] != "choose":
            continue
        wanted = {k[1] for k in expected_by_index[where_index[service["where"]]]}
        match, _choice = ctx.translation.choices[service["default"]]
        for choice in match.choices:
            if choice.lines[0].sku in wanted:
                picks.append({"source": ref, "candidate": choice.ref})
                break
    proposed = await registry.run(ctx, "propose_translation", {
        "provider": provider, "regions": REGIONS[provider], "picks": picks})
    from src.models.orm import AgentProposal

    proposal = await db_session.get(AgentProposal, ctx.proposals[-1].id)
    from src.services.architecture_state import ArchitectureState

    state = ArchitectureState.model_validate(proposal.target_state)
    got_by_index = []
    for collection in state.collections:
        got_by_index.append(sorted(_state_key(s) for s in state.services
                                   if s.collection_id == collection.id))
    assert [_normal(g) for g in got_by_index] == expected_by_index
    # Every figure 022 left out is flagged with 022's reason (no row is silently dropped).
    rows = proposal.translation["rows"]
    left = [r for r in rows if r["match"] is None]
    assert all(r["reason"] for r in left)
    assert proposed.data["rows"]["left_out"] == len(left)


async def _detail(ctx):
    from src.agent.operations import _open_architecture

    return (await _open_architecture(ctx))[1]
