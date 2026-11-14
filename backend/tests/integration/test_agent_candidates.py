"""The batch candidate finder (024, clarification 1, FR-009a, research R1) against the provider
fixtures: up to 5 candidates per source, ranked deterministically, unmatched sources recorded,
bounded concurrency, progress per source."""

from __future__ import annotations

import uuid

import pytest

from src.agent import operations as ops
from src.agent.compare import architecture_sources
from src.agent.figures import FigureBook
from src.agent.matching import candidates as finder
from src.agent.matching.book import MatchBook
from src.models.orm import User
from tests.helpers.agent import build_standard, combined_pricing_root

WEB_APP = "Active-Standby Multi-Region Web Application"


@pytest.fixture
async def web_app_sources(db_session, use_pricing_root):
    use_pricing_root(combined_pricing_root())
    user = User(id=uuid.uuid4(), username=f"o-{uuid.uuid4().hex[:6]}")
    db_session.add(user)
    await db_session.commit()
    arch = await build_standard(db_session, user, "aws", WEB_APP)
    ctx = ops.OperationContext(session=db_session, user=user, open_architecture_id=arch.id,
                               figures=FigureBook())
    _architecture, detail = await ops._open_architecture(ctx)
    return await architecture_sources(detail)


async def _find(sources, targets, **kwargs):
    book = MatchBook()
    for source in sources:
        book.add_source(source)
    found = await finder.find_candidates(book, sources, targets, **kwargs)
    return book, found


async def test_sources_follow_the_architecture(web_app_sources):
    labels = [s.label for s in web_app_sources]
    assert len(web_app_sources) == 16
    assert any("t4g.xlarge" in label for label in labels)
    vm = next(s for s in web_app_sources if s.profile.function == "vm")
    assert vm.profile.specs["vcpu"] == 4 and vm.unit == "Hrs"


async def test_candidates_are_ranked_and_capped(web_app_sources):
    book, found = await _find(web_app_sources, {"azure": "eastus", "gcp": "us-east1"})
    for per_target in found.values():
        for candidates in per_target.values():
            assert len(candidates) <= finder.TOP_N
            ranks = [finder._rank_key(book.sources[c.source_ref].profile, c) for c in candidates]
            assert ranks == sorted(ranks)
    vm = next(s for s in web_app_sources if s.profile.function == "vm")
    azure_vm = found[vm.ref]["azure"][0]
    assert "Standard_D4s_v5" in azure_vm.label
    # Graviton and burstable (t4g) against a steady x86 D-series: close, with both differences.
    assert (azure_vm.quality, azure_vm.differences) == (
        "close", ["x86 vs arm", "steady CPU vs burstable CPU"])
    assert azure_vm.options == {"kind": "azure_vm", "version": 1, "os": "linux"}
    gcp_vm = found[vm.ref]["gcp"][0]
    assert gcp_vm.options["kind"] == "gcp_machine" and gcp_vm.options["vcpus"] == 4
    storage = next(s for s in web_app_sources if s.profile.function == "object_storage"
                   and s.profile.specs.get("storage_class") == "hot")
    assert found[storage.ref]["gcp"][0].quality in ("exact", "close")


async def test_the_same_input_gives_the_same_output(web_app_sources):
    def shape(found):
        return {ref: {p: [(c.sku, c.quality) for c in cs] for p, cs in per.items()}
                for ref, per in found.items()}

    _book, first = await _find(web_app_sources, {"azure": "eastus"})
    _book, second = await _find(web_app_sources, {"azure": "eastus"})
    assert shape(first) == shape(second)


async def test_sources_without_a_comparable_product_are_unmatched(web_app_sources):
    book, found = await _find(web_app_sources, {"azure": "eastus"})
    dns = next(s for s in web_app_sources if s.profile.function == "dns_queries")
    if not found[dns.ref]["azure"]:
        assert (dns.ref, "azure") in book.unmatched
    other = [s for s in web_app_sources if s.profile.function == "other"]
    for source in other:
        assert found[source.ref]["azure"] == []
        assert "no comparable product type" in book.unmatched[(source.ref, "azure")]


async def test_searches_run_at_most_four_at_a_time_and_each_once(web_app_sources, monkeypatch):
    running = peak = 0
    calls: list[tuple] = []
    real = finder._Searcher._run

    async def spy(self, provider, region, filters):
        nonlocal running, peak
        calls.append((provider, region, tuple(sorted(filters.items()))))
        running += 1
        peak = max(peak, running)
        try:
            return await real(self, provider, region, filters)
        finally:
            running -= 1

    monkeypatch.setattr(finder._Searcher, "_run", spy)
    await _find(web_app_sources, {"azure": "eastus", "gcp": "us-east1"})
    assert peak <= finder.CONCURRENCY
    assert len(calls) == len(set(calls))


async def test_progress_is_reported_per_source(web_app_sources):
    seen = []
    await _find(web_app_sources, {"azure": "eastus"},
                progress=lambda done, total, label: seen.append((done, total, label)))
    assert seen == [(i, 16, "Matching services") for i in range(1, 17)]


async def test_a_hint_searches_again_for_that_source(web_app_sources):
    storage = next(s for s in web_app_sources if s.profile.function == "object_storage")
    _book, found = await _find(web_app_sources, {"azure": "eastus"},
                               hints={storage.ref: "Hot LRS"})
    assert found[storage.ref]["azure"]


async def test_with_no_size_of_that_vcpu_count_the_closest_size_is_offered(web_app_sources):
    """The narrowed Azure VM search finds no 2-vCPU size in the fixture (only D4s_v5): the
    broad search still offers it, labelled partial (8 vCPU vs 4 would be partial too)."""
    from dataclasses import replace

    vm = next(s for s in web_app_sources if s.profile.function == "vm")
    two = replace(vm, profile=replace(vm.profile, specs={**vm.profile.specs, "vcpu": 2,
                                                         "memory_gib": 8}))
    _book, found = await _find([two], {"azure": "eastus"})
    candidates = found[two.ref]["azure"]
    assert candidates and candidates[0].quality == "partial"
    assert "4 vCPU vs 2 vCPU" in candidates[0].differences
