"""The golden conversations with the scripted model (023, FR-025, research R8): the default
test run checks the machinery (operations, permissions, figures, refusals) with no network."""

from __future__ import annotations

import pytest

from src.agent.clients.scripted import ScriptedModelClient, Turn
from src.agent.model import ToolCall
from tests.agent_evals.runner import load_cases, run_case
from tests.helpers.agent import STANDARD_PRICING_ROOT

CASES = load_cases()


def _client(script: list[dict]) -> ScriptedModelClient:
    turns = []
    for i, step in enumerate(script):
        calls = [ToolCall(f"s{i}-{j}", c["name"], c.get("arguments") or {})
                 for j, c in enumerate(step.get("tool_calls") or [])]
        turns.append(Turn(text=step.get("text") or [], tool_calls=calls))
    return ScriptedModelClient(turns)


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_golden_conversation(db_session, case, use_pricing_root):
    providers = {(case.get("architecture") or {}).get("provider")} | {
        a["provider"] for o in case.get("others") or [] for a in o["architectures"]}
    if providers & {"gcp", "azure"}:
        use_pricing_root(STANDARD_PRICING_ROOT)
    result = await run_case(db_session, case, _client(case["script"]))
    failed = [f"{c.name} ({c.detail})" for c in result.checks if not c.passed]
    assert result.error is None, result.error
    assert not failed, f"{failed}\n--- answer ---\n{result.text}"
    assert result.checks, "a case must check something"
