"""025 (research R5, data-model §2–§3): building, validating and pricing proposals, without a
database: change items over a state, the edit rules, and figures equal to the engine's."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import pytest

from src.agent.proposals import (
    Draft,
    ServiceSpec,
    apply_items,
    cost_summary,
    price_state,
    validate,
)
from src.models.schemas import CalculationDuration
from src.services.architecture_rules import RuleError
from src.services.architecture_state import (
    ArchitectureState,
    CollectionState,
    ServiceState,
    fingerprint,
    to_transient,
)
from src.services.price_calculation import calculate_architecture_price
from tests.helpers.agent import seed_definition

WEB_APP = "Active-Standby Multi-Region Web Application"
CLOCK = datetime(2026, 11, 15, 12, 0, 0)


def _base() -> ArchitectureState:
    definition = seed_definition("aws", WEB_APP)
    collections, services = [], []
    ids = {c.ref: uuid.uuid4() for c in definition.collections}
    for c in definition.collections:
        collections.append(CollectionState(
            id=ids[c.ref], type=c.type.value, name=c.name, region=c.region,
            parent_id=ids.get(c.parent_ref) if c.parent_ref else None, created_at=CLOCK))
        for s in c.sku_selections:
            services.append(ServiceState(
                id=uuid.uuid4(), collection_id=ids[c.ref], service_code=s.service_code,
                sku=s.sku, pricing_term=s.pricing_term.value,
                purchase_option=s.purchase_option.value, usage_quantity=s.usage_quantity,
                provider_options=None, created_at=CLOCK))
    return ArchitectureState(name="Prod Web", provider="aws", collections=collections,
                             services=services)


def _engine_total(state: ArchitectureState, duration="1_month") -> Decimal:
    result = calculate_architecture_price(to_transient(state),
                                          duration=CalculationDuration(duration))
    return Decimal(result.total_price)


def _spec_like(service: ServiceState, **changes) -> ServiceSpec:
    data = {"service_code": service.service_code, "sku": service.sku,
            "pricing_term": service.pricing_term, "purchase_option": service.purchase_option,
            "usage_quantity": service.usage_quantity, "provider_options": None, "label": "Copy"}
    return ServiceSpec(**{**data, **changes})


def _replication_draft(base: ArchitectureState) -> Draft:
    """A standby collection in us-west-2 with a copy of one primary service, a resize, a removal
    and a rename, in two groups."""
    draft = Draft(base, CLOCK)
    primary = base.collections[0]
    copy_of = next(s for s in base.services if s.collection_id == base.collections[1].id)
    standby = draft.add_collection("new1", type="vpc", name="Standby", region="us-west-2",
                                   parent_id=None, group="standby")
    draft.add_service(_spec_like(copy_of), collection_id=standby, group="standby",
                      where="Standby")
    first = next(s for s in base.services if s.collection_id == primary.id)
    draft.change("service", first.id, {"usage_quantity": str(first.usage_quantity / 2)},
                 label="Half the first service", group="resize")
    last = [s for s in base.services if s.collection_id == primary.id][-1]
    draft.remove("service", last.id, label="Drop the last service", group="resize")
    draft.rename("Prod Web DR", group="resize")
    return draft


def test_items_build_the_target_state():
    base = _base()
    draft = _replication_draft(base)
    target = draft.state
    assert [i.ref for i in draft.items] == ["P1", "P2", "P3", "P4", "P5"]
    assert [i.op for i in draft.items] == ["add", "add", "change", "remove", "change"]
    assert target.name == "Prod Web DR"
    assert len(target.collections) == len(base.collections) + 1
    assert len(target.services) == len(base.services)  # one added, one removed
    standby = next(c for c in target.collections if c.name == "Standby")
    assert any(s.collection_id == standby.id for s in target.services)
    assert fingerprint(base) == fingerprint(_base_like(base))  # the base is untouched


def _base_like(base: ArchitectureState) -> ArchitectureState:
    return base.model_copy(deep=True)


def test_removing_a_collection_removes_its_services_and_unnests():
    base = _base()
    draft = Draft(base, CLOCK)
    vpc = base.collections[0]
    app = draft.add_collection("new1", type="application_component", name="App",
                               region=vpc.region, parent_id=vpc.id, group=None)
    draft.remove("collection", vpc.id, label="Primary", group=None)
    target = draft.state
    assert target.collection(vpc.id) is None
    assert not [s for s in target.services if s.collection_id == vpc.id]
    assert target.collection(app).parent_id is None


def test_items_round_trip_as_json():
    from src.agent.proposals import ChangeItem

    base = _base()
    draft = _replication_draft(base)
    again = [ChangeItem.from_json(i.to_json()) for i in draft.items]
    assert fingerprint(apply_items(base, again)) == fingerprint(draft.state)


def test_validation_names_the_item_and_the_rule():
    base = _base()
    draft = Draft(base, CLOCK)
    parent = draft.add_collection("new1", type="application_component", name="Not a VPC",
                                  region="us-east-1", parent_id=None, group=None)
    draft.add_collection("new2", type="application_component", name="Child",
                         region="us-east-1", parent_id=parent, group=None)
    with pytest.raises(RuleError) as caught:
        validate(base, draft.state, draft.items)
    assert caught.value.ref == "P2"
    assert "VPC" in caught.value.message

    draft = Draft(base, CLOCK)
    service = base.services[0]
    draft.change("service", service.id, {"pricing_term": "spot"}, label="x", group=None)
    with pytest.raises(RuleError) as caught:
        validate(base, draft.state, draft.items)
    assert caught.value.ref == "P1" and caught.value.field == "pricing_term"

    draft = Draft(base, CLOCK)
    draft.add_collection("new1", type="vpc", name="Mars", region="mars-1", parent_id=None,
                         group=None)
    with pytest.raises(RuleError) as caught:
        validate(base, draft.state, draft.items)
    assert caught.value.ref == "P1" and "mars-1" in caught.value.message


def test_more_than_100_items_is_refused():
    base = _base()
    draft = Draft(base, CLOCK)
    for n in range(101):
        draft.add_collection(f"new{n}", type="vpc", name=f"V{n}", region="us-east-1",
                             parent_id=None, group=None)
    with pytest.raises(RuleError) as caught:
        validate(base, draft.state, draft.items)
    assert "at most 100" in caught.value.message


def test_a_valid_proposal_passes():
    base = _base()
    draft = _replication_draft(base)
    validate(base, draft.state, draft.items)


def test_cost_equals_the_engine_before_and_after():
    base = _base()
    draft = _replication_draft(base)
    target = draft.state
    cost = cost_summary(base, draft.items, target, "1_month")
    before, after = _engine_total(base), _engine_total(target)
    assert Decimal(cost["before"]["total"]) == before
    assert Decimal(cost["after"]["total"]) == after
    assert Decimal(cost["difference"]) == after - before
    assert Decimal(cost["percent"]) == (after - before) / before * 100
    assert cost["snapshot"]["provider"] == "aws"


def test_by_service_and_by_region_add_up():
    base = _base()
    draft = _replication_draft(base)
    cost = cost_summary(base, draft.items, draft.state, "1_month")
    after = sum(Decimal(r["after"]) for r in cost["by_service"] if r["after"] is not None)
    assert after == Decimal(cost["after"]["total"])
    regions = {r["label"] for r in cost["by_region"]}
    assert {"us-east-1", "us-west-2"} <= regions
    assert sum(Decimal(r["after"]) for r in cost["by_region"]) == Decimal(cost["after"]["total"])
    removed = next(r for r in cost["by_service"] if r["after"] is None)
    assert removed["before"] is not None


def test_contributions_add_up_to_the_difference_in_group_order():
    base = _base()
    draft = _replication_draft(base)
    cost = cost_summary(base, draft.items, draft.state, "1_month")
    assert [c["group"] for c in cost["contributions"]] == ["standby", "resize"]
    total = sum(Decimal(c["difference"]) for c in cost["contributions"])
    assert total == Decimal(cost["difference"])


def test_an_unpriceable_service_makes_the_total_partial():
    base = _base()
    draft = Draft(base, CLOCK)
    draft.add_service(_spec_like(base.services[0], sku="NOSUCHSKU", label="Mystery"),
                      collection_id=base.collections[0].id, group=None, where="Primary")
    cost = cost_summary(base, draft.items, draft.state, "1_month")
    assert cost["after"]["partial"] is True
    assert len(cost["unpriceable"]) == 1
    label = cost["unpriceable"][0]["label"]
    assert "NOSUCHSKU" in label and base.collections[0].name in label


def test_a_new_architecture_has_no_before_figures():
    base = _base()
    empty = ArchitectureState(name="New", provider="aws")
    draft = Draft(empty, CLOCK)
    vpc = draft.add_collection("new1", type="vpc", name="Web", region="us-east-1",
                               parent_id=None, group=None)
    draft.add_service(_spec_like(base.services[0]), collection_id=vpc, group=None, where="Web")
    cost = cost_summary(None, draft.items, draft.state, "1_month")
    assert "before" not in cost and "difference" not in cost
    assert Decimal(cost["after"]["total"]) == price_state(draft.state, "1_month").total
