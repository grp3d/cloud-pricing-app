"""Cost control for live evaluations (docs/development.md, "Budget for hosted-model runs").

`Metered` wraps a model client: it counts every call and the tokens the model reports, and once
a run has made `Budget.max_calls` paid calls it refuses the next one, so a run can't spend more
than its cap. Local models (Ollama) are free: counted, never capped.

Prices come from `AGENT_EVAL_PRICES`, in USD per million tokens as the provider lists them:
`AGENT_EVAL_PRICES="claude-sonnet-5-5=IN/OUT,claude-haiku-5-5=IN/OUT"`. Without a price the
report shows tokens and says the cost isn't known.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from src.agent.model import ModelError, Usage

FREE_PROVIDERS = {"ollama", "scripted"}
DEFAULT_MAX_CALLS = 30


class BudgetReached(ModelError):
    """The run's paid-call cap is used up; the call was not made."""

    kind = "failed"


@dataclass
class Budget:
    max_calls: int = DEFAULT_MAX_CALLS
    paid_calls: int = 0

    @property
    def reached(self) -> bool:
        return self.paid_calls >= self.max_calls


@dataclass
class Meter:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    stopped: bool = False

    def add(self, other: Meter) -> None:
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens


@dataclass
class Prices:
    """USD per million tokens, per model."""

    by_model: dict[str, tuple[Decimal, Decimal]] = field(default_factory=dict)

    @classmethod
    def parse(cls, text: str | None) -> Prices:
        prices = {}
        for item in (text or "").split(","):
            if not item.strip():
                continue
            model, _, rates = item.partition("=")
            rate_in, _, rate_out = rates.partition("/")
            prices[model.strip()] = (Decimal(rate_in.strip()), Decimal(rate_out.strip()))
        return cls(prices)

    def cost(self, model: str, meter: Meter) -> Decimal | None:
        if model not in self.by_model:
            return None
        rate_in, rate_out = self.by_model[model]
        return (meter.input_tokens * rate_in + meter.output_tokens * rate_out) / Decimal(1_000_000)


class Metered:
    """A model client that counts its calls and tokens and stops at the run's budget."""

    def __init__(self, inner, budget: Budget):
        self.inner = inner
        self.provider = inner.provider
        self.model = inner.model
        self.budget = budget
        self.paid = inner.provider not in FREE_PROVIDERS
        self.meter = Meter()

    async def stream(self, system, messages, tools):
        if self.paid and self.budget.reached:
            self.meter.stopped = True
            raise BudgetReached(f"the run's cap of {self.budget.max_calls} paid calls is used up")
        if self.paid:
            self.budget.paid_calls += 1
        self.meter.calls += 1
        async for event in self.inner.stream(system, messages, tools):
            if isinstance(event, Usage):
                self.meter.input_tokens += event.input_tokens
                self.meter.output_tokens += event.output_tokens
            yield event


def format_cost(cost: Decimal | None) -> str:
    return "price not set" if cost is None else f"${cost.quantize(Decimal('0.0001'))}"
