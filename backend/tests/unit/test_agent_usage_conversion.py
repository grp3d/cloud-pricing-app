"""Usage for comparisons (024, research R4): a quantity is carried over only between products
billed in the same kind of unit; stated amounts and defaults become engine quantities by fixed
app factors, never the model's."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.agent.matching.profiles import ProductProfile
from src.agent.matching.usage import (
    Converted,
    Unconvertible,
    convert,
    default_usage,
    stated_quantity,
)


def p(function, unit_kind, **specs) -> ProductProfile:
    return ProductProfile(function, None, unit_kind, specs)


def test_same_unit_kind_carries_the_quantity_unchanged():
    out = convert(p("object_storage", "gb_month"), Decimal(2000), p("object_storage", "gb_month"),
                  target_provider="gcp")
    assert out == Converted(Decimal(2000))


def test_gb_and_gib_billing_count_as_the_same_unit():
    # AWS "GB-Mo" and GCP "GiBy.mo" are both the gb_month kind (022's convention).
    from src.agent.matching.profiles import unit_kind
    assert unit_kind("GB-Mo") == unit_kind("GiBy.mo") == unit_kind("1 GB/Month") == "gb_month"


def test_a_different_unit_kind_is_unconvertible_never_a_number():
    out = convert(p("other", "dpu_hour"), Decimal(20), p("other", "vcpu_hour"),
                  target_provider="gcp")
    assert isinstance(out, Unconvertible)
    assert "billed per vcpu hour, not per dpu hour" in out.reason
    assert isinstance(convert(p("vm", "unknown"), Decimal(1), p("vm", "unknown"),
                              target_provider="aws"), Unconvertible)


def test_gcp_machines_are_sized_to_the_source():
    source = p("vm", "hour", vcpu=4, memory_gib=Decimal("16"), os="linux")
    out = convert(source, Decimal(96), p("vm", "hour", family="E2"), target_provider="gcp",
                  ram_sku="RAM-1")
    assert out.quantity == Decimal(96)
    assert out.options == {"kind": "gcp_machine", "version": 1, "vcpus": 4, "memory_gib": "16",
                           "ram_sku": "RAM-1"}
    assert out.note == "sized to 4 vCPU and 16 GiB"


def test_gcp_machine_needs_the_source_size_and_a_ram_sku():
    no_size = convert(p("vm", "hour"), Decimal(24), p("vm", "hour"), target_provider="gcp",
                      ram_sku="R")
    assert isinstance(no_size, Unconvertible)
    no_ram = convert(p("vm", "hour", vcpu=2, memory_gib=Decimal(8)), Decimal(24),
                     p("vm", "hour"), target_provider="gcp")
    assert isinstance(no_ram, Unconvertible)


def test_azure_vms_carry_the_source_os():
    out = convert(p("vm", "hour", os="windows"), Decimal(24), p("vm", "hour"),
                  target_provider="azure")
    assert out.options == {"kind": "azure_vm", "version": 1, "os": "windows"}
    linux = convert(p("vm", "hour"), Decimal(24), p("vm", "hour"), target_provider="azure")
    assert linux.options["os"] == "linux"


@pytest.mark.parametrize(("kind", "amount", "unit", "quantity", "label"), [
    ("gb_month", 10, "tb", Decimal(10000), "10 TB stored"),
    ("gb_month", 500, "gb", Decimal(500), "500 GB stored"),
    ("gb", 1, "tb", Decimal(1000) / Decimal(31), "1 TB a month"),
    ("hour", 2, "instances", Decimal(48), "2 instance(s) running all day"),
    ("hour", 310, "hours", Decimal(10), "310 hours a month"),
    ("request", 31, "million_requests", Decimal(1_000_000), "31 million requests a month"),
])
def test_stated_amounts_become_engine_quantities(kind, amount, unit, quantity, label):
    out = stated_quantity(kind, Decimal(amount), unit)
    assert out.quantity == quantity
    assert out.note == label


def test_a_stated_unit_that_doesnt_fit_is_refused():
    out = stated_quantity("hour", Decimal(1), "tb")
    assert isinstance(out, Unconvertible)
    assert "use: hours, instances" in out.reason


def test_default_usage_per_function():
    assert default_usage("object_storage").label == "1 TB stored for the month"
    assert (default_usage("vm").amount, default_usage("vm").unit) == (Decimal(1), "instances")
    assert default_usage("db_storage").unit == "gb"
    assert default_usage("data_transfer").unit == "tb"
    assert default_usage("object_requests_read").unit == "million_requests"
    assert default_usage("other") is None


def test_a_stored_quantity_unit_says_its_period():
    from src.agent.matching.usage import quantity_unit

    assert quantity_unit("GB") == "GB a day"  # GB transferred: a daily rate
    assert quantity_unit("Hrs") == "Hrs a day"
    assert quantity_unit("GB-Mo") == "GB-Mo"  # its own period: the amount held
    assert quantity_unit(None) is None


def test_plain_numbers_drop_trailing_zeros():
    from src.agent.matching.usage import plain_number

    assert plain_number("500.0000") == "500"
    assert plain_number("32.2581") == "32.2581"
    assert plain_number(1000) == "1000"


def test_each_providers_units_are_classified_by_its_own_table():
    from src.agent.matching.usage import quantity_unit

    assert quantity_unit("h", "gcp") == "h a day"  # GCP's hour: Hours per day in the Service tab
    assert quantity_unit("GiBy.mo", "gcp") == "GiBy.mo"
    assert quantity_unit("1 Hour", "azure") == "1 Hour a day"
