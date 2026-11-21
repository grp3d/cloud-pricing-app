"""Match quality (024, clarification 3, FR-009b, research R3): fixed app rules; the agent may
lower a label with a reason, never raise it."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.agent.matching.profiles import ProductProfile
from src.agent.matching.quality import lower, quality
from src.agent.operations import ToolError


def vm(**specs) -> ProductProfile:
    base = {"vcpu": 4, "memory_gib": Decimal(16), "arch": "x86", "os": "linux"}
    return ProductProfile("vm", "compute", "hour", {**base, **specs})


def blob(**specs) -> ProductProfile:
    base = {"storage_class": "hot", "redundancy": "local"}
    return ProductProfile("object_storage", "storage", "gb_month", {**base, **specs})


def test_exact_when_function_unit_and_every_shared_spec_match():
    assert quality(vm(), vm()) == ("exact", [])


def test_close_when_memory_is_larger_up_to_twice():
    label, differences = quality(vm(), vm(memory_gib=Decimal(32)))
    assert label == "close"
    assert differences == ["memory 32 GiB vs 16 GiB"]


def test_close_when_only_the_architecture_differs():
    assert quality(vm(arch="arm"), vm()) == ("close", ["x86 vs arm"])


def test_close_when_only_redundancy_differs():
    assert quality(blob(redundancy="zonal"), blob()) == (
        "close", ["redundancy local vs zonal"])


def test_close_when_the_target_lacks_a_spec_the_source_has():
    target = ProductProfile("vm", "compute", "hour", {"vcpu": 4, "arch": "x86", "os": "linux"})
    assert quality(vm(), target) == ("close", ["memory not published for this product"])


@pytest.mark.parametrize(("target", "difference"), [
    (vm(vcpu=8, memory_gib=Decimal(32)), "8 vCPU vs 4 vCPU"),
    (vm(memory_gib=Decimal(8)), "memory 8 GiB vs 16 GiB"),
    (vm(memory_gib=Decimal(64)), "memory 64 GiB vs 16 GiB"),
    (vm(os="windows"), "windows vs linux"),
])
def test_partial_on_a_major_spec_difference(target, difference):
    label, differences = quality(vm(), target)
    assert label == "partial"
    assert difference in differences


def test_partial_on_a_different_storage_class():
    label, differences = quality(blob(), blob(storage_class="cool"))
    assert (label, differences) == ("partial", ["access tier cool vs hot"])


def test_partial_on_a_different_function_in_the_same_category():
    source = ProductProfile("block_storage", "storage", "gb_month", {})
    label, differences = quality(source, blob())
    assert label == "partial"
    assert differences == ["object storage, not block storage"]


def test_partial_on_a_different_billing_unit():
    source = ProductProfile("load_balancer_capacity", "networking", "lcu_hour", {})
    target = ProductProfile("load_balancer_capacity", "networking", "gb", {})
    assert quality(source, target) == (
        "partial", ["billed per gb, not per lcu hour; usage can't be converted"])


def test_no_equivalent_without_a_candidate_or_in_another_category():
    assert quality(vm(), None) == ("no_equivalent", ["no product in the same category"])
    assert quality(vm(), blob())[0] == "no_equivalent"


def test_the_agent_may_lower_a_label_with_a_reason_but_never_raise_it():
    assert lower("close", "partial", "different performance tier") == "partial"
    assert lower("close", "close", None) == "close"
    assert lower("close", None, None) == "close"
    with pytest.raises(ToolError, match="higher"):
        lower("partial", "exact", "looks the same")
    with pytest.raises(ToolError, match="reason"):
        lower("exact", "close", None)


def lb(**specs) -> ProductProfile:
    return ProductProfile("load_balancer", "networking", "hour", specs)


def test_application_gateway_editions_for_an_application_load_balancer():
    alb = lb(lb_layer="application", lb_edition="standard")
    assert quality(alb, lb(lb_layer="application", lb_edition="standard")) == ("exact", [])
    assert quality(alb, lb(lb_layer="application", lb_edition="waf")) == (
        "close", ["with a web application firewall"])
    assert quality(alb, lb(lb_layer="application", lb_edition="basic"))[0] == "close"
    # A product with no edition (a GCP forwarding rule) isn't marked down for it.
    assert quality(alb, lb(lb_layer="application")) == ("exact", [])
    assert quality(alb, lb(lb_layer="network")) == (
        "partial", ["network load balancer vs application"])


def transfer(**specs) -> ProductProfile:
    return ProductProfile("data_transfer", "networking", "gb", {"transfer": "inter_region",
                                                                **specs})


def test_a_transfer_price_must_be_for_the_destination():
    # us-east-1 to us-west-2 (Oregon), against GCP prices from Virginia.
    source = transfer(dest_geo="north_america", dest_place="Oregon")
    assert quality(source, transfer(dest_geo="americas")) == ("exact", [])
    assert quality(source, transfer(dest_place="Oregon")) == ("exact", [])
    assert quality(source, transfer(dest_place="Columbus")) == (
        "partial", ["priced only for transfer to Columbus"])
    assert quality(source, transfer(dest_geo="emea")) == (
        "partial", ["priced only for transfer to EMEA"])
    # A place may be named more or less fully; a price with no destination isn't marked down.
    assert quality(transfer(dest_place="Northern Virginia"),
                   transfer(dest_place="Virginia"))[0] == "exact"
    assert quality(source, transfer()) == ("exact", [])
