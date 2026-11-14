"""Cost control for live evaluations (metering.py), checked with the scripted model: no network,
no spend. The scripted client is treated as paid so the cap applies."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from src.agent.model import Usage
from tests.agent_evals.metering import Budget, Meter, Metered, Prices, format_cost
from tests.agent_evals.runner import load_cases, run_case
from tests.agent_evals.test_golden_scripted import _client
from tests.helpers.agent import combined_pricing_root

GC_11 = next(c for c in load_cases() if c["id"] == "GC-11")  # 2 messages, 4 model calls


def _paid(budget: Budget) -> Metered:
    inner = _client(GC_11["script"])
    inner._turns = [replace(t, usage=Usage(1000, 100)) for t in inner._turns]
    client = Metered(inner, budget)
    client.paid = True
    return client


async def test_counts_calls_and_tokens(db_session, use_pricing_root):
    use_pricing_root(combined_pricing_root())
    budget = Budget(max_calls=30)
    client = _paid(budget)
    result = await run_case(db_session, GC_11, client)
    assert result.error is None
    assert (client.meter.calls, client.meter.input_tokens, client.meter.output_tokens) == (
        4, 4000, 400)
    assert budget.paid_calls == 4 and not client.meter.stopped


async def test_stops_at_the_cap_without_making_the_call(db_session, use_pricing_root):
    use_pricing_root(combined_pricing_root())
    budget = Budget(max_calls=2)
    client = _paid(budget)
    result = await run_case(db_session, GC_11, client)
    assert client.meter.stopped and result.error is not None
    assert client.meter.calls == 2 and budget.paid_calls == 2 and budget.reached


def test_free_models_are_counted_but_never_capped():
    client = Metered(_client(GC_11["script"]), Budget(max_calls=0))
    assert not client.paid


def test_prices_per_million_tokens():
    prices = Prices.parse("model-a=3/15, model-b=1/5")
    meter = Meter(calls=4, input_tokens=200_000, output_tokens=10_000)
    assert prices.cost("model-a", meter) == Decimal("0.75")
    assert prices.cost("unknown", meter) is None
    assert format_cost(None) == "price not set"
    assert format_cost(Decimal("0.75")) == "$0.7500"
