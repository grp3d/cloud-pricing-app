"""The provider registry and the AWS adapter's price shapes (019, T023, research R3)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.pricing_data.active_snapshot import get_active_snapshot
from src.pricing_data.providers.registry import get_provider


def test_missing_code_means_aws():
    assert get_provider(None).code == "aws"
    assert get_provider("aws").code == "aws"


def test_unknown_provider_is_a_value_error():
    with pytest.raises(ValueError):
        get_provider("oracle")


def test_aws_on_demand_quote_has_every_tier():
    quote = get_provider("aws").price(
        get_active_snapshot(), item="5M4327XEUKBBTWAT", pricing_term="on_demand",
        purchase_option="not_applicable", region="us-west-2",
    )
    assert [t.rate for t in quote.tiers] == [
        Decimal("0.09"), Decimal("0.085"), Decimal("0.07"), Decimal("0.05")
    ]


def test_aws_reserved_quote_wraps_lookup_reserved_price():
    quote = get_provider("aws").price(
        get_active_snapshot(), item="QZ9R39S2Y8MCC9Y8", pricing_term="reserved_1yr",
        purchase_option="no_upfront", region="us-east-1",
    )
    assert quote is not None and quote.recurring_rate is not None and quote.tiers == []


def test_aws_unpublished_price_is_none():
    assert get_provider("aws").price(
        get_active_snapshot(), item="NOSUCHSKU", pricing_term="on_demand",
        purchase_option="not_applicable", region="us-east-1",
    ) is None
