"""The system prompt (024, T036): versioned, names the comparison operations, and keeps the
rules that the evaluation cases rely on."""

from __future__ import annotations

from src.agent.operations import registry
from src.agent.prompt import PROMPT_VERSION, SYSTEM_PROMPT


def test_version():
    assert PROMPT_VERSION == "024.2"


def test_names_every_comparison_operation_and_they_exist():
    for name in ("find_matches", "price_matches", "search_products", "price_products"):
        assert name in SYSTEM_PROMPT
        assert name in registry.names()


def test_keeps_the_comparison_rules():
    for rule in ("Never recommend a provider", "at most three short questions",
                 "is a guess", "Never name a SKU yourself", "never raise it",
                 "give no figure for it", "shown to the user as a table",
                 "Those amounts came from operation results"):
        assert rule in SYSTEM_PROMPT, rule
