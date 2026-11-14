"""Live-model evaluation (023, research R8, SC-005): opt-in, never in the default run.

    AGENT_EVAL_MODELS="ollama:llama3.1,anthropic:claude-sonnet-5-5" uv run pytest -m live_model

Runs every golden conversation against each model with the same fixed checks as the scripted
run, and writes `backend/agent-eval-report.md` with pass/fail per case and per check, per model.
A hosted model needs `AGENT_ANTHROPIC_API_KEY`; Ollama is reached at `AGENT_EVAL_OLLAMA_URL`
(default http://localhost:11434).

Cost control (`metering.py`): the report gives calls, tokens and cost per case and per model.
A run makes at most `AGENT_EVAL_MAX_CALLS` paid calls (default 30); the cases after that are
skipped. Prices: `AGENT_EVAL_PRICES="<model>=<in>/<out>,..."`, USD per million tokens.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.agent_evals.metering import (
    DEFAULT_MAX_CALLS,
    FREE_PROVIDERS,
    Budget,
    Meter,
    Metered,
    Prices,
    format_cost,
)
from tests.agent_evals.runner import CaseResult, load_cases, run_case
from tests.helpers.agent import STANDARD_PRICING_ROOT, combined_pricing_root

pytestmark = pytest.mark.live_model

CASES = load_cases()
REPORT = Path(__file__).resolve().parents[2] / "agent-eval-report.md"
MODELS = [m.strip() for m in os.environ.get("AGENT_EVAL_MODELS", "").split(",") if m.strip()]
_results: dict[str, list[CaseResult]] = {}
_meters: dict[tuple[str, str], Meter] = {}
BUDGET = Budget(int(os.environ.get("AGENT_EVAL_MAX_CALLS", DEFAULT_MAX_CALLS)))
PRICES = Prices.parse(os.environ.get("AGENT_EVAL_PRICES"))


def anthropic_key() -> str | None:
    """024 (T066): the key the way the app finds it: the process environment first, then the
    app settings, which load `backend/.env`. Never printed or logged."""
    key = os.environ.get("AGENT_ANTHROPIC_API_KEY")
    if key:
        return key
    from src.config import Settings

    secret = Settings().agent_anthropic_api_key
    return secret.get_secret_value() if secret is not None else None


def _client(spec: str):
    provider, _, model = spec.partition(":")
    if provider == "ollama":
        from src.agent.clients.ollama import OllamaClient

        return OllamaClient(os.environ.get("AGENT_EVAL_OLLAMA_URL", "http://localhost:11434"),
                            model)
    if provider == "anthropic":
        from src.agent.clients.anthropic import AnthropicClient

        key = anthropic_key()
        if not key:
            pytest.skip("AGENT_ANTHROPIC_API_KEY is not set (environment or backend/.env)")
        return AnthropicClient(api_key=key, model=model)
    raise ValueError(f"unknown provider in {spec!r} (use ollama:<model> or anthropic:<model>)")


def _cost(model: str, meter: Meter) -> str:
    provider, _, name = model.partition(":")
    return "free" if provider in FREE_PROVIDERS else format_cost(PRICES.cost(name, meter))


def _write_report() -> None:
    lines = ["# Agent evaluation report", "",
             f"Run {datetime.now(UTC):%Y-%m-%d %H:%M} UTC. Case runs: {len(_meters)}. Paid calls: "
             f"{BUDGET.paid_calls} of the cap of {BUDGET.max_calls}.", ""]
    lines += ["| Model | Passed | Calls | Input tokens | Output tokens | Cost | Cost per case |",
              "|---|---|---|---|---|---|---|"]
    for model, results in _results.items():
        total = Meter()
        for r in results:
            total.add(_meters[(model, r.id)])
        cost = PRICES.cost(model.partition(":")[2], total)
        per_case = None if cost is None or not results else cost / len(results)
        free = model.partition(":")[0] in FREE_PROVIDERS
        lines.append(f"| {model} | {sum(r.passed for r in results)} of {len(results)} | "
                     f"{total.calls} | {total.input_tokens:,} | {total.output_tokens:,} | "
                     f"{'free' if free else format_cost(cost)} | "
                     f"{'free' if free else format_cost(per_case)} |")
    for model, results in _results.items():
        lines += ["", f"## {model}", ""]
        for r in results:
            lines.append(f"### {'PASS' if r.passed else 'FAIL'} {r.id}: {r.title}")
            meter = _meters[(model, r.id)]
            lines.append(f"- {meter.calls} calls, {meter.input_tokens:,} input and "
                         f"{meter.output_tokens:,} output tokens, "
                         f"{_cost(model, meter)}")
            if r.error:
                lines.append(f"- error: {r.error}")
            lines += [f"- {'pass' if c.passed else 'FAIL'}: {c.name}"
                      + (f" ({c.detail})" if c.detail else "") for c in r.checks]
            lines += ["", "<details><summary>Answer</summary>", "", r.text.strip() or "(none)",
                      "", "</details>", ""]
    REPORT.write_text("\n".join(lines))


@pytest.mark.skipif(not MODELS, reason="set AGENT_EVAL_MODELS to run live evaluations")
@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_live_golden_conversation(db_session, use_pricing_root, model, case):
    providers = {(case.get("architecture") or {}).get("provider")} | {
        a["provider"] for o in case.get("others") or [] for a in o["architectures"]}
    if case.get("pricing") == "combined":
        use_pricing_root(combined_pricing_root())
    elif providers & {"gcp", "azure"}:
        use_pricing_root(STANDARD_PRICING_ROOT)
    client = Metered(_client(model), BUDGET)
    if client.paid and BUDGET.reached:
        pytest.skip(f"the run's cap of {BUDGET.max_calls} paid calls is used up "
                    "(AGENT_EVAL_MAX_CALLS)")
    result = await run_case(db_session, case, client)
    _meters[(model, case["id"])] = client.meter
    _results.setdefault(model, []).append(result)
    _write_report()
    if client.meter.stopped:
        pytest.fail(f"stopped: the run's cap of {BUDGET.max_calls} paid calls is used up "
                    "(AGENT_EVAL_MAX_CALLS); this case didn't finish")
    failed = [c.name for c in result.checks if not c.passed]
    assert result.passed, f"{result.error or ''} {failed}"
