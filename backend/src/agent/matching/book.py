"""Match references (024, research R7): the products one agent message works with.

Operations hand the model sources as `S1, S2…` and candidates as `C1, C2…`; the model picks by
reference only, so it can't name a SKU the app didn't offer (Principle VII). A book lives for one
agent message, beside the `FigureBook`: a reference from an earlier message is unknown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from src.agent.matching.profiles import ProductProfile


@dataclass
class SourceProduct:
    provider: str
    region: str
    service_code: str
    sku: str
    label: str
    where: str | None
    usage_quantity: Decimal
    unit: str | None
    pricing_term: str
    purchase_option: str
    profile: ProductProfile
    provider_options: dict | None = None
    ref: str = ""


@dataclass
class Candidate:
    source_ref: str | None
    provider: str
    region: str
    service_code: str
    sku: str
    label: str
    profile: ProductProfile
    quality: str | None = None
    differences: list[str] = field(default_factory=list)
    quantity: Decimal | None = None  # the engine quantity, when converted
    unconvertible: str | None = None
    usage_note: str | None = None
    options: dict | None = None
    price_types: tuple[str, ...] = ()
    unit: str | None = None
    ram_sku: str | None = None
    # 025: a region equivalent keeps its original's term unless the agent sets one.
    keep_term: tuple[str, str] | None = None  # (pricing_term, purchase_option)
    ref: str = ""


@dataclass
class MatchBook:
    sources: dict[str, SourceProduct] = field(default_factory=dict)
    candidates: dict[str, Candidate] = field(default_factory=dict)
    unmatched: dict[tuple[str, str], str] = field(default_factory=dict)  # (S…, provider) -> why
    # What the latest `find_matches` covered, so `price_matches` prices exactly that: its
    # sources (a later call adds a fresh set), target providers with the region chosen per
    # source region, and the category it was limited to.
    latest_sources: list[str] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)
    region_choices: dict = field(default_factory=dict)  # provider -> {source region: choice}
    category: str | None = None

    def add_source(self, source: SourceProduct) -> str:
        source.ref = f"S{len(self.sources) + 1}"
        self.sources[source.ref] = source
        return source.ref

    def add_candidate(self, candidate: Candidate) -> str:
        candidate.ref = f"C{len(self.candidates) + 1}"
        self.candidates[candidate.ref] = candidate
        return candidate.ref

    def source(self, ref: str) -> SourceProduct:
        from src.agent.operations import ToolError

        if ref not in self.sources:
            raise ToolError(f"unknown source {ref!r}: use a reference from this message's "
                            "find_matches result")
        return self.sources[ref]

    def candidate(self, ref: str) -> Candidate:
        from src.agent.operations import ToolError

        if ref not in self.candidates:
            raise ToolError(f"unknown candidate {ref!r}: pick one returned in this message")
        return self.candidates[ref]
