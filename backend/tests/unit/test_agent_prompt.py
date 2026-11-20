"""The system prompt (024, T036): versioned, names the comparison operations, and keeps the
rules that the evaluation cases rely on."""

from __future__ import annotations

from src.agent.operations import registry
from src.agent.prompt import PROMPT_VERSION, SYSTEM_PROMPT


def test_version():
    assert PROMPT_VERSION == "026.3"


def test_names_every_comparison_operation_and_they_exist():
    for name in ("find_matches", "price_matches", "search_products", "price_products"):
        assert name in SYSTEM_PROMPT
        assert name in registry.names()


def test_keeps_the_comparison_rules():
    for rule in ("Never recommend a provider", "at most three short questions",
                 "Count every question mark", "by its service and SKU",
                 "a guess, in those words", "Never name a SKU yourself", "never raise it",
                 "give no figure for it", "shown to the user as a table",
                 "Those amounts came from operation results"):
        assert rule in SYSTEM_PROMPT, rule


CHANGE_OPERATIONS = ("find_products", "propose_new_architecture", "propose_changes",
                     "find_region_equivalents", "list_my_architectures", "open_architecture",
                     "propose_import")


def test_names_every_change_operation_and_they_exist():
    """025: each change operation the prompt names is registered."""
    for name in CHANGE_OPERATIONS:
        assert name in SYSTEM_PROMPT, name
        assert name in registry.names(), name


def test_keeps_the_change_rules():
    """025 (FR-001, FR-003, FR-008, FR-010, FR-011, C2): the rules the change cases rely on."""
    for rule in ("Never say you saved", "nothing is saved until the user accepts",
                 "at most three short questions, then offer your defaults",
                 "propose nothing and say what you need", "never invent one",
                 "Copies keep the original's pricing term", "say the term",
                 "say you're opening it", "offer to import a copy first",
                 "won't be saved unless", "your assumptions", "list what you can do"):
        assert rule in SYSTEM_PROMPT, rule


TRANSLATION_OPERATIONS = ("find_translation", "propose_translation", "describe_translation")


def test_names_every_translation_operation_and_keeps_its_rules():
    """026: the translation operations exist, and the rules the golden conversations rely on are
    stated."""
    for name in TRANSLATION_OPERATIONS:
        assert name in SYSTEM_PROMPT, name
        assert name in registry.names(), name
    for rule in ("unless the user chose it", "chosen by you",
                 "difference on the matched services", "reserved terms, say they don't carry",
                 "every caveat", "AWS to GCP or Azure"):
        assert rule in SYSTEM_PROMPT, rule
