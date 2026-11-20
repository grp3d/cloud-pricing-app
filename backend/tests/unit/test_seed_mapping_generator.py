"""The seed mapping generator (026, research R4): 022's AWS and provider rules, paired by
(architecture, component, figure), become source-key → target-key mappings."""

from __future__ import annotations

import json
from decimal import Decimal

from scripts.standard_architectures.match_rules import MatchRule
from scripts.standard_architectures.resolver import (
    Match,
    Omission,
    ProviderRule,
    Resolution,
    to_service_mappings,
)


def _aws(arch, comp, fig, sku, quantity):
    rule = MatchRule(arch, comp, fig, "us-east-1", service_codes=("AmazonEC2",),
                     quantity=Decimal(quantity))
    return Match(rule=rule, service_code="AmazonEC2", sku=sku, unit="Hrs", tiered=False)


def _gcp(arch, comp, fig, sku, quantity, *, options=None, note=None, size_note=None):
    rule = ProviderRule(arch, comp, fig, "us-east1", quantity=Decimal(quantity), note=note,
                        size_note=size_note)
    return Match(rule=rule, service_code="SVC", sku=sku, unit="h", tiered=False,
                 provider_options=options)


def _omit(arch, comp, fig, reason):
    return Omission(rule=ProviderRule(arch, comp, fig, "us-east1", omit_reason=reason),
                    reason=reason)


KEYS = {"A-VM": "aws|AmazonEC2|BoxUsage:t4g.xlarge|RunInstances",
        "A-GLUE": "aws|AWSGlue|ETL-DPU-Hour|Jobrun",
        "A-LCU": "aws|AmazonEC2|LCUUsage|LoadBalancing:Application",
        "A-DB": "aws|AmazonRDS|InstanceUsage:db.r6g.xl|CreateDBInstance:0021",
        "G-E2": "gcp|SVC|E2 Instance Core running", "G-RAM": "gcp|SVC|E2 Instance Ram running",
        "G-CPU": "gcp|SVC|vCPU Time Batch", "G-MEM": "gcp|SVC|RAM Time",
        "G-ZONAL": "gcp|SVC|Cloud SQL Zonal vCPU", "G-HA": "gcp|SVC|Cloud SQL Regional vCPU"}


def _key(provider, service_code, sku, region):
    return KEYS[sku]


def _generate(aws_matches, target_matches, target_omissions=()):
    return to_service_mappings(
        Resolution("2026-09-24", list(aws_matches), []),
        Resolution("2026-11-02", list(target_matches), list(target_omissions)),
        target_provider="gcp", key_of=_key)


def test_rules_pair_by_component_and_figure_with_a_factor():
    out = _generate([_aws("web", "ec2", "hours", "A-VM", "96")],
                    [_gcp("web", "ec2", "hours", "G-E2", "96",
                          options={"kind": "gcp_machine", "version": 1, "vcpus": 4,
                                   "memory_gib": "16", "ram_sku": "G-RAM"},
                          size_note="4 × t4g.xlarge 4/16 → 4 × e2-standard-4 4/16")])
    assert out["source_provider"] == "aws" and out["target_provider"] == "gcp"
    assert out["snapshots"] == {"aws": "2026-09-24", "gcp": "2026-11-02"}
    [row] = out["mappings"]
    assert row["source_key"] == KEYS["A-VM"] and row["target_key"] == KEYS["G-E2"]
    assert row["target_sku"] == "G-E2" and row["target_service_code"] == "SVC"
    assert row["alternative"] == 1 and row["part"] == 1
    assert Decimal(row["quantity_factor"]) == 1
    # The RAM SKU is region-specific: the mapping keeps its key instead.
    assert row["target_options"] == {"kind": "gcp_machine", "version": 1, "vcpus": 4,
                                     "memory_gib": "16", "ram_key": KEYS["G-RAM"]}
    assert row["note"] == "4 × t4g.xlarge 4/16 → 4 × e2-standard-4 4/16"


def test_two_target_lines_are_two_parts_with_their_own_factors():
    out = _generate([_aws("lake", "glue", "dpu", "A-GLUE", "20")],
                    [_gcp("lake", "glue", "dpu", "G-CPU", "80"),
                     _gcp("lake", "glue", "dpu", "G-MEM", "320")])
    rows = out["mappings"]
    assert [(r["part"], r["target_key"], Decimal(r["quantity_factor"])) for r in rows] == [
        (1, KEYS["G-CPU"], Decimal(4)), (2, KEYS["G-MEM"], Decimal(16))]
    assert {r["alternative"] for r in rows} == {1}


def test_distinct_targets_for_one_source_become_alternatives_and_duplicates_collapse():
    out = _generate(
        [_aws("web", "db", "inst", "A-DB", "24"), _aws("eks", "db", "inst", "A-DB", "24"),
         _aws("other", "db", "inst", "A-DB", "24")],
        [_gcp("web", "db", "inst", "G-ZONAL", "24", note="zonal"),
         _gcp("eks", "db", "inst", "G-HA", "24", note="regional"),
         _gcp("other", "db", "inst", "G-ZONAL", "24", note="zonal")])
    rows = out["mappings"]
    assert [(r["alternative"], r["target_key"], r["note"]) for r in rows] == [
        (1, KEYS["G-ZONAL"], "zonal"), (2, KEYS["G-HA"], "regional")]


def test_the_same_target_with_another_factor_is_another_alternative():
    out = _generate([_aws("a", "db", "inst", "A-DB", "24"), _aws("b", "db", "inst", "A-DB", "24")],
                    [_gcp("a", "db", "inst", "G-ZONAL", "24"),
                     _gcp("b", "db", "inst", "G-ZONAL", "48")])
    assert [Decimal(r["quantity_factor"]) for r in out["mappings"]] == [1, 2]
    assert [r["alternative"] for r in out["mappings"]] == [1, 2]


def test_an_omitted_figure_is_no_equivalent_with_its_reason():
    out = _generate([_aws("web", "alb", "lcu", "A-LCU", "24")], [],
                    [_omit("web", "alb", "lcu", "GCP load balancers have no LCU-hour unit")])
    [row] = out["mappings"]
    assert row["target_key"] is None and row["quantity_factor"] is None
    assert row["omit_reason"] == "GCP load balancers have no LCU-hour unit"


def test_a_figure_the_aws_version_leaves_out_gives_no_mapping():
    out = _generate([], [], [_omit("web", "cdn", "gb", "left out to match the AWS version")])
    assert out["mappings"] == []


def test_output_is_sorted_and_byte_identical():
    args = ([_aws("web", "ec2", "hours", "A-VM", "96"), _aws("web", "db", "inst", "A-DB", "24")],
            [_gcp("web", "db", "inst", "G-ZONAL", "24"), _gcp("web", "ec2", "hours", "G-E2", "96")])
    first = json.dumps(_generate(*args), indent=2)
    assert first == json.dumps(_generate(*args), indent=2)
    keys = [r["source_key"] for r in json.loads(first)["mappings"]]
    assert keys == sorted(keys)
