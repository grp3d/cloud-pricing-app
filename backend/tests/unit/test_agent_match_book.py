"""Match references (024, research R7): sources and candidates are numbered per message; an
unknown or earlier-message reference is a tool error."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.agent.matching.book import Candidate, MatchBook, SourceProduct
from src.agent.matching.profiles import ProductProfile
from src.agent.operations import ToolError

PROFILE = ProductProfile("vm", "compute", "hour", {})


def source() -> SourceProduct:
    return SourceProduct("aws", "us-east-1", "AmazonEC2", "SKU", "EC2", "VPC", Decimal(24),
                         "Hrs", "on_demand", "not_applicable", PROFILE)


def candidate() -> Candidate:
    return Candidate("S1", "azure", "eastus", "VM", "A/B", "D4s v5", PROFILE)


def test_references_are_numbered_in_order():
    book = MatchBook()
    assert [book.add_source(source()), book.add_source(source())] == ["S1", "S2"]
    assert [book.add_candidate(candidate()), book.add_candidate(candidate())] == ["C1", "C2"]
    assert book.source("S2").ref == "S2"
    assert book.candidate("C1").sku == "A/B"


def test_unknown_references_are_tool_errors():
    book = MatchBook()
    book.add_source(source())
    with pytest.raises(ToolError, match="unknown source 'S9'"):
        book.source("S9")
    with pytest.raises(ToolError, match="unknown candidate 'C1'"):
        book.candidate("C1")


def test_a_new_book_doesnt_know_an_earlier_messages_references():
    first = MatchBook()
    first.add_candidate(candidate())
    with pytest.raises(ToolError):
        MatchBook().candidate("C1")
