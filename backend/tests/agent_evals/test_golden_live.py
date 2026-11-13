"""Live-model evaluation (023, research R8, SC-005): opt-in, never in the default run.

    AGENT_EVAL_MODELS="ollama:llama3.1,anthropic:claude-haiku-5-5" uv run pytest -m live_model

Runs every golden conversation against each model with the same fixed checks as the scripted
run, and writes `backend/agent-eval-report.md` with pass/fail per case and per check, per model.
A hosted model needs `AGENT_ANTHROPIC_API_KEY`; Ollama is reached at `AGENT_EVAL_OLLAMA_URL`
(default http://localhost:11434).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.agent_evals.runner import CaseResult, load_cases, run_case
from tests.helpers.agent import STANDARD_PRICING_ROOT

pytestmark = pytest.mark.live_model

CASES = load_cases()
REPORT = Path(__file__).resolve().parents[2] / "agent-eval-report.md"
MODELS = [m.strip() for m in os.environ.get("AGENT_EVAL_MODELS", "").split(",") if m.strip()]
_results: dict[str, list[CaseResult]] = {}


def _client(spec: str):
    provider, _, model = spec.partition(":")
    if provider == "ollama":
        from src.agent.clients.ollama import OllamaClient

        return OllamaClient(os.environ.get("AGENT_EVAL_OLLAMA_URL", "http://localhost:11434"),
                            model)
    if provider == "anthropic":
        from src.agent.clients.anthropic import AnthropicClient

        key = os.environ.get("AGENT_ANTHROPIC_API_KEY")
        if not key:
            pytest.skip("AGENT_ANTHROPIC_API_KEY is not set")
        return AnthropicClient(api_key=key, model=model)
    raise ValueError(f"unknown provider in {spec!r} (use ollama:<model> or anthropic:<model>)")


def _write_report() -> None:
    lines = ["# Agent evaluation report", "",
             f"Run {datetime.now(UTC):%Y-%m-%d %H:%M} UTC, {len(CASES)} cases.", ""]
    lines += ["| Model | Passed |", "|---|---|"]
    for model, results in _results.items():
        lines.append(f"| {model} | {sum(r.passed for r in results)} of {len(results)} |")
    for model, results in _results.items():
        lines += ["", f"## {model}", ""]
        for r in results:
            lines.append(f"### {'PASS' if r.passed else 'FAIL'} {r.id}: {r.title}")
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
    if providers & {"gcp", "azure"}:
        use_pricing_root(STANDARD_PRICING_ROOT)
    result = await run_case(db_session, case, _client(model))
    _results.setdefault(model, []).append(result)
    _write_report()
    failed = [c.name for c in result.checks if not c.passed]
    assert result.passed, f"{result.error or ''} {failed}"
