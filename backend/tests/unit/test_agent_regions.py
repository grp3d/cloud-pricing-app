"""Region guesses (024, research R6, FR-007): from a reviewed location table, the same metro
area first, then the nearest region in the same geography with pricing data; always flagged as
a guess. A named region is used as given."""

from __future__ import annotations

import pytest

from src.agent.matching.regions import known, locations, region_guess, resolve_region
from src.agent.operations import ToolError
from src.pricing_data import active_snapshot
from src.pricing_data.providers.registry import get_provider
from tests.helpers.agent import combined_pricing_root

ALL = {provider: set(regions) for provider, regions in locations().items()}
FIXTURE = {"aws": {"us-east-1", "us-west-2", "eu-west-1"},
           "azure": {"eastus", "westus2", "westeurope"},
           "gcp": {"us-east1", "us-west1", "europe-west1"}}


def test_every_region_with_pricing_data_in_the_fixtures_is_in_the_table(use_pricing_root):
    use_pricing_root(combined_pricing_root())
    for provider in ("aws", "azure", "gcp"):
        adapter = get_provider(provider)
        listed = set(adapter.locations(active_snapshot.get_active_snapshot(provider)))
        missing = sorted(r for r in listed if not known(provider, r))
        assert not missing, f"add {provider} regions to region_locations.json: {missing}"


def test_every_aws_region_has_a_guess_or_none_on_the_other_providers():
    for region in ALL["aws"]:
        for target in ("azure", "gcp"):
            guess = region_guess("aws", region, target, ALL[target])
            if guess is not None:
                assert locations()[target][guess]["geography"] == (
                    locations()["aws"][region]["geography"])


@pytest.mark.parametrize(("source", "target", "expected"), [
    (("aws", "us-east-1"), "azure", "eastus"),
    (("aws", "us-east-1"), "gcp", "us-east1"),
    (("aws", "us-west-2"), "gcp", "us-west1"),
    (("aws", "us-west-2"), "azure", "westus2"),
    (("aws", "eu-west-1"), "gcp", "europe-west1"),
    (("aws", "eu-west-1"), "azure", "westeurope"),
    (("azure", "eastus"), "aws", "us-east-1"),
])
def test_guesses_among_the_fixture_regions(source, target, expected):
    assert region_guess(*source, target, FIXTURE[target]) == expected


def test_the_same_metro_area_wins_when_it_has_data():
    assert region_guess("aws", "us-east-1", "gcp", ALL["gcp"]) == "us-east4"  # both Ashburn
    assert region_guess("aws", "eu-central-1", "azure", ALL["azure"]) == "germanywestcentral"


def test_no_guess_outside_the_geography():
    assert region_guess("aws", "sa-east-1", "gcp", FIXTURE["gcp"]) is None


def test_resolve_a_named_region():
    choice = resolve_region("azure", "westeurope", available=FIXTURE["azure"])
    assert (choice.region, choice.guessed, choice.available) == ("westeurope", False, True)


def test_a_real_region_without_pricing_data_is_unavailable_not_an_error():
    choice = resolve_region("gcp", "asia-east1", available=FIXTURE["gcp"])
    assert (choice.region, choice.available) == ("asia-east1", False)
    assert "no GCP pricing data for asia-east1" in choice.reason


def test_a_region_that_doesnt_exist_is_a_tool_error_with_close_names():
    with pytest.raises(ToolError, match="isn't a GCP region. Closest names: europe-west1"):
        resolve_region("gcp", "europe-west-1", available=FIXTURE["gcp"])


def test_resolve_by_guess_is_flagged():
    choice = resolve_region("gcp", None, available=FIXTURE["gcp"], near=("aws", "us-east-1"))
    assert (choice.region, choice.guessed, choice.available) == ("us-east1", True, True)
    none = resolve_region("gcp", None, available=FIXTURE["gcp"], near=("aws", "sa-east-1"))
    assert (none.region, none.available) == (None, False)
    with pytest.raises(ToolError, match="Name a region"):
        resolve_region("gcp", None, available=FIXTURE["gcp"])
