"""Cost control for live evaluations (docs/development.md, "Budget for hosted-model runs").

`Metered` wraps a model client: it counts every call and the tokens the model reports. A paid
run is held to the estimate the user approved: before each paid call it stops if the run has made
`Budget.max_calls` paid calls, or if what it has spent plus the average cost of a call so far
would go over `Budget.max_usd`. Local models (Ollama) are free: counted, never capped.

Prices come from `AGENT_EVAL_PRICES`, in USD per million tokens as the provider lists them:
`AGENT_EVAL_PRICES="claude-sonnet-5-5=IN/OUT,claude-haiku-5-5=IN/OUT"`. A paid model needs a
price, so its spend can be tracked against the approved amount.
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
    """The approved estimate for a run: at most `max_calls` paid calls and `max_usd` dollars."""

    max_calls: int = DEFAULT_MAX_CALLS
    max_usd: Decimal | None = None
    paid_calls: int = 0
    spent_usd: Decimal = Decimal(0)

    def over(self) -> str | None:
        """Why the next paid call would go past the approved estimate, or None."""
        if self.paid_calls >= self.max_calls:
            return f"the approved {self.max_calls} paid calls are used up"
        if self.max_usd is not None and self.paid_calls:
            next_total = self.spent_usd + self.spent_usd / self.paid_calls
            if next_total > self.max_usd:
                return (f"the next call would take the run past the approved "
                        f"{format_cost(self.max_usd)} ({format_cost(self.spent_usd)} spent)")
        return None

    @property
    def reached(self) -> bool:
        return self.over() is not None


@dataclass
class Meter:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    stopped: bool = False
    stop_reason: str = ""

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

    def __init__(self, inner, budget: Budget, prices: Prices | None = None):
        self.inner = inner
        self.provider = inner.provider
        self.model = inner.model
        self.budget = budget
        self.prices = prices or Prices()
        self.paid = inner.provider not in FREE_PROVIDERS
        self.meter = Meter()

    async def stream(self, system, messages, tools):
        if self.paid and (reason := self.budget.over()):
            self.meter.stopped = True
            self.meter.stop_reason = reason
            raise BudgetReached(reason)
        if self.paid:
            self.budget.paid_calls += 1
        self.meter.calls += 1
        async for event in self.inner.stream(system, messages, tools):
            if isinstance(event, Usage):
                self.meter.input_tokens += event.input_tokens
                self.meter.output_tokens += event.output_tokens
                if self.paid:
                    cost = self.prices.cost(self.model, Meter(1, event.input_tokens,
                                                              event.output_tokens))
                    self.budget.spent_usd += cost or Decimal(0)
            yield event


def format_cost(cost: Decimal | None) -> str:
    return "price not set" if cost is None else f"${cost.quantize(Decimal('0.0001'))}"
