"""025 (research R1, data-model "Validation rules"): the edit rules shared by the edit routes and
agent proposals. Each test pins the status and message the routes return today, so the refactor
can't change them."""

from __future__ import annotations

import pytest

from src.services import architecture_rules as rules
from src.services.architecture_rules import RuleError


def _fails(fn, *args, **kwargs) -> RuleError:
    with pytest.raises(RuleError) as caught:
        fn(*args, **kwargs)
    return caught.value


def test_provider_must_have_an_adapter():
    error = _fails(rules.check_provider, "oracle")
    assert (error.status, error.detail) == (400, "Provider not supported: oracle")
    rules.check_provider("aws")


def test_region_must_be_available():
    error = _fails(rules.check_region_available, "aws", "mars-north-1")
    assert (error.status, error.detail) == (400, "region 'mars-north-1' is not currently available")
    rules.check_region_available("aws", "us-east-1")


def test_region_is_required():
    assert _fails(rules.check_region_given, None).detail == (
        "region is required when parent_collection_id is not given")
    assert _fails(rules.check_region_given, "", creating=False).detail == "region is required"


def test_only_an_application_can_have_a_parent():
    error = _fails(rules.check_nesting, "vpc", "us-east-1", None, creating=True)
    assert (error.status, error.detail) == (
        400, "Only an Application Component can be created with a parent_collection_id")
    error = _fails(rules.check_nesting, "vpc", "us-east-1", None, creating=False)
    assert error.detail == "Only an Application Component can be nested inside a VPC"


def test_parent_must_be_a_live_vpc_of_the_architecture():
    error = _fails(rules.check_nesting, "application_component", "us-east-1", None)
    assert (error.status, error.detail) == (
        400, "parent_collection_id must reference an existing, non-deleted VPC Collection in "
        "the same Architecture")
    app = rules.CollectionFacts(type="application_component", region="us-east-1")
    assert _fails(rules.check_nesting, "application_component", "us-east-1", app).status == 400


def test_nesting_needs_the_same_region():
    vpc = rules.CollectionFacts(type="vpc", region="us-west-2")
    error = _fails(rules.check_nesting, "application_component", "us-east-1", vpc)
    assert error.status == 409
    assert error.detail == {"error": "region_mismatch", "application_region": "us-east-1",
                            "vpc_region": "us-west-2"}
    rules.check_nesting("application_component", "us-west-2", vpc)


def test_a_collection_with_content_keeps_its_region():
    error = _fails(rules.check_region_change, locked=True)
    assert (error.status, error.detail) == (
        409, "This collection's region is locked because it already has content")
    rules.check_region_change(locked=False)


def test_connector_ends():
    error = _fails(rules.check_connector_ends, "a", "a", {"a", "b"})
    assert (error.status, error.detail) == (400, "A connector cannot link a Collection to itself")
    error = _fails(rules.check_connector_ends, "a", "z", {"a", "b"})
    assert (error.status, error.detail) == (400, "Both collections must belong to this Architecture")
    rules.check_connector_ends("a", "b", {"a", "b"})


def test_selection_price_type_and_purchase_option():
    error = _fails(rules.check_selection, "aws", service_code="AmazonEC2", sku="X",
                   pricing_term="spot", purchase_option="no_upfront", provider_options=None,
                   region="us-east-1")
    assert error.status == 422 and error.field == "pricing_term"
    assert error.detail == [{"loc": ["body", "pricing_term"],
                             "msg": "aws does not publish the price type 'spot'",
                             "type": "value_error"}]
    error = _fails(rules.check_selection, "gcp", service_code="x", sku="y",
                   pricing_term="on_demand", purchase_option="all_upfront",
                   provider_options=None, region="us-east1")
    assert error.field == "purchase_option"
    assert "gcp prices have no purchase option 'all_upfront'" in error.message


def test_selection_provider_options_must_belong_to_the_provider():
    error = _fails(rules.check_selection, "aws", service_code="AmazonEC2", sku="X",
                   pricing_term="on_demand", purchase_option="not_applicable",
                   provider_options={"kind": "gcp_machine"}, region="us-east-1")
    assert error.field == "provider_options"
    assert error.message == "'gcp_machine' options don't apply to a aws architecture"


def test_at_most_100_change_items():
    error = _fails(rules.check_item_count, 101)
    assert error.status == 422
    assert error.detail == "A proposal can hold at most 100 changes; build it in parts."
    rules.check_item_count(100)


def test_rule_error_becomes_the_same_http_error():
    error = RuleError(400, "region is required")
    http = error.to_http()
    assert (http.status_code, http.detail) == (400, "region is required")
