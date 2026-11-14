"""The batch candidate finder (024, clarification 1, FR-009a, research R1).

For many source products at once, find the top few products on each target provider: search the
target's catalog with a fixed search per function (the Azure/GCP `kind` presets, or AWS service
filters), profile every row, label it with the quality rules, carry the usage over where the
rules allow, and rank deterministically (quality, then spec distance, then SKU). Identical
searches are made once per call, and at most `CONCURRENCY` run at a time.

The model only chooses among what this returns (by `C…` reference); the app makes every
candidate, label and quantity.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from decimal import Decimal

from src.agent.matching.book import Candidate, MatchBook, SourceProduct
from src.agent.matching.profiles import ProductProfile, product_label, profile
from src.agent.matching.quality import LABELS, quality
from src.agent.matching.usage import Converted, convert
from src.pricing_data.providers.base import CatalogItem

TOP_N = 5
PAGE = 200
MAX_PAGES = 5  # up to 1,000 rows per search
CONCURRENCY = 4

# The catalog searches for each function on each provider (all are run; rows are then profiled,
# so a broad search is fine). Azure and GCP searches need a `kind` or a `text`.
SEARCHES: dict[str, dict[str, list[dict]]] = {
    "aws": {
        "vm": [{"service_code": "AmazonEC2", "product_family": "Compute Instance"}],
        "block_storage": [{"service_code": "AmazonEC2", "product_family": "Storage"}],
        "managed_db": [{"service_code": "AmazonRDS", "product_family": "Database Instance"}],
        "db_storage": [{"service_code": "AmazonRDS", "product_family": "Database Storage"}],
        "cache": [{"service_code": "AmazonElastiCache", "product_family": "Cache Instance"}],
        "object_storage": [{"service_code": "AmazonS3", "product_family": "Storage"}],
        "object_requests_write": [{"service_code": "AmazonS3", "product_family": "API Request"}],
        "object_requests_read": [{"service_code": "AmazonS3", "product_family": "API Request"}],
        "file_storage": [{"service_code": "AmazonEFS"}],
        "data_transfer": [{"service_code": "AWSDataTransfer"}],
        "load_balancer": [{"service_code": "AWSELB"}],
        "load_balancer_capacity": [{"service_code": "AWSELB"}],
        "dns_queries": [{"service_code": "AmazonRoute53", "product_family": "DNS Query"}],
        "serverless_requests": [{"service_code": "AWSLambda"}],
        "serverless_compute": [{"service_code": "AWSLambda"}],
        "container_cluster": [{"service_code": "AmazonEKS"}],
    },
    "azure": {
        "vm": [{"kind": "vm"}],
        "block_storage": [{"kind": "block_storage"}],
        "managed_db": [{"kind": "managed_db"}],
        "db_storage": [{"kind": "managed_db"}],
        "cache": [{"text": "Redis"}],
        "object_storage": [{"kind": "object_storage"}],
        "object_requests_write": [{"kind": "object_storage"}],
        "object_requests_read": [{"kind": "object_storage"}],
        "file_storage": [{"text": "Files"}],
        "data_transfer": [{"kind": "data_transfer"}],
        "load_balancer": [{"text": "Load Balancer"}],
        "load_balancer_capacity": [{"text": "Load Balancer"}],
        "dns_queries": [{"text": "DNS"}],
        "serverless_requests": [{"text": "Functions"}],
        "serverless_compute": [{"text": "Functions"}],
        "container_cluster": [{"text": "Kubernetes"}],
    },
    "gcp": {
        "vm": [{"kind": "vm"}],
        "block_storage": [{"kind": "block_storage"}],
        "managed_db": [{"kind": "managed_db"}],
        "db_storage": [{"kind": "managed_db"}, {"kind": "block_storage"}],
        "cache": [{"text": "Memorystore"}, {"text": "Redis"}],
        "object_storage": [{"kind": "object_storage"}],
        "object_requests_write": [{"text": "Class A"}],
        "object_requests_read": [{"text": "Class B"}],
        "file_storage": [{"text": "Filestore"}],
        "data_transfer": [{"kind": "data_transfer"}],
        "load_balancer": [{"text": "Load Balancing"}],
        "load_balancer_capacity": [{"text": "Load Balancing"}],
        "dns_queries": [{"text": "DNS"}],
        "serverless_requests": [{"text": "Cloud Run"}],
        "serverless_compute": [{"text": "Cloud Run"}],
        "container_cluster": [{"text": "Kubernetes"}],
    },
}

# Products that are never offered as a match: a term or discount sold as its own SKU (the term
# is chosen separately), interruptible or dedicated capacity, licences, and free, developer or
# replica variants. Matched on the readable name, case-insensitively.
EXCLUDED_WORDS = (
    "commitment", "committed use", "reservation", "reserved", "savings plan", " spot", "spot ", "preemptible",
    "low priority", "cloud services", "dedicated host", "sole tenancy", "free tier", "promotional",
    "read replica", "backup", "developer", "extended support", "licen", "byol", "devtest",
    "dev/test", "autoclass", " hns ", "azure arc", "hyperscale", "private queries",
)

# Variants that are fine matches but less typical; they rank after the plain product.
NICHE_WORDS = ("enterprise plus", "dual-region", "multi-region", "premium", "global", "ultra",
               "gateway", "confidential", "business critical", "internal", "cross regional",
               "cross-region", "additional", "always ready", "intercontinental",
               "hierarchical namespace", " - free", "basic", "custom", "tagging")

# Words that place a product in a part of the world; a product naming another part of the
# world than the target region's ranks after one that doesn't.
GEOGRAPHY_WORDS = {
    "north_america": ("americas", "north america", "virginia", "iowa", "oregon", "carolina",
                      "us ", "canada", "texas", "ohio", "california", "las vegas", "dallas"),
    "south_america": ("south america", "sao paulo", "são paulo", "santiago", "latin america"),
    "europe": ("europe", "emea", "london", "frankfurt", "belgium", "netherlands", "paris",
               "zurich", "milan", "madrid", "warsaw", "finland", "stockholm", "ireland"),
    "asia_pacific": ("asia", "apac", "delhi", "mumbai", "tokyo", "osaka", "seoul", "singapore",
                     "jakarta", "sydney", "melbourne", "australia", "hong kong", "taiwan",
                     "japan", "india", "oceania"),
    "middle_east": ("middle east", "middleeast", "doha", "dammam", "tel aviv", "israel",
                    "qatar", "uae", "dubai"),
    "africa": ("africa", "johannesburg", "cape town"),
}


def geography_penalty(label: str, provider: str, region: str) -> Decimal:
    from src.agent.matching.regions import locations

    home = locations().get(provider, {}).get(region, {}).get("geography")
    if home is None:
        return Decimal(0)
    text = f" {label.lower()} "
    foreign = any(word in text for geo, words in GEOGRAPHY_WORDS.items() if geo != home
                  for word in words)
    return Decimal("0.75") if foreign else Decimal(0)


def excluded(label: str, attributes: dict) -> bool:
    text = f" {label.lower()} "
    if any(word in text for word in EXCLUDED_WORDS):
        return True
    # AWS EC2/RDS variants that aren't the plain product.
    if attributes.get("tenancy") not in (None, "", "Shared"):
        return True
    if attributes.get("preInstalledSw") not in (None, "", "NA"):
        return True
    if attributes.get("capacitystatus") not in (None, "", "Used"):
        return True
    return False


_ENGINE_NAMES = {"postgresql": "PostgreSQL", "mysql": "MySQL", "sqlserver": "SQL Server"}


def targeted_searches(provider: str, source: ProductProfile) -> list[dict]:
    """The searches for one source: the provider's search for its function, narrowed by the
    source's specs where a broad search would return too many rows (Azure lists thousands of
    VMs and databases per region)."""
    base = SEARCHES[provider].get(source.function, [])
    specs = source.specs
    vcpu = specs.get("vcpu")
    engine = _ENGINE_NAMES.get(str(specs.get("engine")))
    if provider == "azure":
        if source.function == "vm" and vcpu:
            return [{"kind": "vm", "text": rf"Standard_[A-Za-z]+{int(vcpu)}[a-z]*(_| |$)"}]
        if source.function == "managed_db" and engine:
            return [{"kind": "managed_db", "text": f"{engine} Flex"}]
        if source.function == "db_storage" and engine:
            return [{"kind": "managed_db", "text": f"{engine} Flex.*Storage"}]
        if source.function == "object_storage":
            return [{"kind": "object_storage", "text": "Block Blob.*Data Stored"}]
        if source.function == "object_requests_write":
            return [{"text": "Block Blob.*Write Operations"}]
        if source.function == "object_requests_read":
            return [{"text": "Block Blob.*Read Operations"}]
        if source.function in ("load_balancer", "load_balancer_capacity"):
            return [{"text": "^Load Balancer "}, {"text": "^Application Gateway "}]
        if source.function == "data_transfer":
            words = {"inter_region": "Inter-Region|Intra Continent",
                     "internet": "Data Transfer Out"}.get(str(specs.get("transfer")))
            return [{"text": f"^Bandwidth .*({words})" if words else "^Bandwidth "}]
        if source.function == "dns_queries":
            return [{"text": "^Azure DNS .*Public Queries"}]
        if source.function == "container_cluster":
            return [{"text": "^Azure Kubernetes Service"}]
    if provider == "gcp":
        if source.function == "managed_db" and engine:
            return [{"kind": "managed_db", "text": f"Cloud SQL for {engine}: .*vCPU|"
                     f"Cloud SQL for {engine}: .*RAM"}]
        if source.function == "db_storage" and engine:
            return [{"kind": "block_storage", "text": f"Cloud SQL for {engine}"},
                    {"kind": "managed_db", "text": f"Cloud SQL for {engine}.*storage"}]
        if source.function == "object_requests_write":
            return [{"text": "Class A Operations"}]
        if source.function == "object_requests_read":
            return [{"text": "Class B Operations"}]
        if source.function in ("load_balancer", "load_balancer_capacity"):
            return [{"text": "Forwarding Rule"}]
        if source.function == "data_transfer":
            words = {"inter_region": "Inter[- ]?Region", "internet": "Internet Data Transfer"
                     }.get(str(specs.get("transfer")))
            return [{"kind": "data_transfer", "text": words}] if words else base
        if source.function == "dns_queries":
            return [{"text": "DNS Query"}]
        if source.function == "container_cluster":
            return [{"text": "Kubernetes Clusters|cluster management"}]
    if provider == "aws":
        if source.function in ("vm", "managed_db", "cache") and vcpu and base:
            return [{**base[0], "text": rf'"vcpu": ?"{int(vcpu)}"'}]
    return base


# GCP machine shapes (research R4, 022 R6): predefined families' GiB per vCPU, and vCPU counts.
_GCP_RATIOS = (Decimal(1), Decimal(4), Decimal(8))
_GCP_VCPUS = (2, 4, 8, 16, 32, 48, 64, 80, 96, 128)


def gcp_predefined_shape(vcpu: int, memory: Decimal) -> tuple[int, Decimal] | None:
    """The smallest predefined shape at least as large (022 R6): the smallest ratio of at least
    the source's GiB per vCPU, and the smallest vCPU count of at least the source's."""
    ratio = Decimal(str(memory)) / vcpu
    ratios = [r for r in _GCP_RATIOS if r >= ratio]
    counts = [c for c in _GCP_VCPUS if c >= vcpu]
    if not ratios or not counts:
        return None
    return counts[0], counts[0] * ratios[0]


def _rank_key(source: ProductProfile, candidate: Candidate) -> tuple:
    distance = Decimal(0)
    s, t = source.specs, candidate.profile.specs
    if "vcpu" in s and "vcpu" in t:
        distance += abs(Decimal(t["vcpu"]) - Decimal(s["vcpu"]))
    if "memory_gib" in s and "memory_gib" in t and s["memory_gib"]:
        distance += abs(Decimal(str(t["memory_gib"])) / Decimal(str(s["memory_gib"])) - 1)
    for key in ("arch", "os", "engine", "storage_class", "redundancy", "ha", "purpose",
                "burstable", "transfer", "visibility", "lb_layer"):
        if key in s and t.get(key) != s[key]:
            distance += Decimal("0.5")
    label = candidate.label.lower()
    distance += Decimal("0.25") * sum(1 for word in NICHE_WORDS if word in label)
    distance += geography_penalty(candidate.label, candidate.provider, candidate.region)
    unconvertible = 1 if candidate.unconvertible else 0
    return (LABELS.index(candidate.quality or "no_equivalent"), unconvertible, distance,
            candidate.label, candidate.sku)


class _Searcher:
    """Runs each distinct (provider, region, filters) search once, at most CONCURRENCY at a
    time, in worker threads (the adapters are synchronous DuckDB code)."""

    def __init__(self) -> None:
        self._semaphore = asyncio.Semaphore(CONCURRENCY)
        self._results: dict[tuple, asyncio.Task] = {}
        self.calls = 0

    def search(self, provider: str, region: str, filters: dict) -> asyncio.Task:
        key = (provider, region, tuple(sorted(filters.items())))
        if key not in self._results:
            self._results[key] = asyncio.ensure_future(self._guarded(provider, region, filters))
        return self._results[key]

    async def _guarded(self, provider: str, region: str, filters: dict) -> list[CatalogItem]:
        async with self._semaphore:
            self.calls += 1
            return await self._run(provider, region, filters)

    async def _run(self, provider: str, region: str, filters: dict) -> list[CatalogItem]:
        from src.pricing_data.active_snapshot import get_active_snapshot
        from src.pricing_data.providers.registry import get_provider

        adapter = get_provider(provider)
        snapshot = get_active_snapshot(adapter.code)

        def pages() -> list[CatalogItem]:
            rows: list[CatalogItem] = []
            for page in range(MAX_PAGES):
                items, total = adapter.search(snapshot, region=region, limit=PAGE,
                                              offset=page * PAGE, **filters)
                rows.extend(items)
                if len(items) < PAGE or len(rows) >= total:
                    break
            return rows

        return await asyncio.to_thread(pages)


def _aws_units(region: str, skus: list[str]) -> dict[str, str | None]:
    from src.pricing_data.active_snapshot import get_active_snapshot
    from src.pricing_data.providers.registry import get_provider

    adapter = get_provider("aws")
    keys = [(sku, "on_demand", "not_applicable") for sku in skus]
    found = adapter.units(get_active_snapshot("aws"), keys, region=region) if keys else {}
    return {sku: found.get((sku, "on_demand", "not_applicable")) for sku in skus}


def _gcp_ram_skus(rows: list[CatalogItem]) -> dict[str, str]:
    """Cloud SQL vCPU SKU → its RAM SKU (same name with "RAM" for "vCPU"); VM cores carry their
    own `ram_sku` attribute."""
    by_summary = {row.summary: row.sku for row in rows}
    pairs: dict[str, str] = {}
    for row in rows:
        if row.attributes.get("ram_sku"):
            pairs[row.sku] = row.attributes["ram_sku"]
        elif " vCPU " in f" {row.summary} ":
            ram = by_summary.get(row.summary.replace("vCPU", "RAM"))
            if ram:
                pairs[row.sku] = ram
    return pairs


async def _candidates_for(source: SourceProduct, provider: str, region: str, rows: list[CatalogItem],
                          units: dict[str, str | None], ram_skus: dict[str, str]) -> list[Candidate]:
    out: list[Candidate] = []
    seen: set[str] = set()
    for row in rows:
        if row.sku in seen:
            continue
        seen.add(row.sku)
        target = profile(row, unit=units.get(row.sku) if provider == "aws" else None)
        if target.function == "other" or target.category != source.profile.category:
            continue
        if excluded(product_label(row), row.attributes):
            continue
        ram_sku = ram_skus.get(row.sku)
        size_note = None
        if provider == "gcp" and target.function == "vm":
            vcpu, memory = source.profile.specs.get("vcpu"), source.profile.specs.get("memory_gib")
            shape = gcp_predefined_shape(int(vcpu), Decimal(str(memory))) if (
                vcpu is not None and memory is not None) else None
            if shape is not None:
                target.specs.update(vcpu=shape[0], memory_gib=shape[1])
                if (shape[0], shape[1]) != (vcpu, memory):
                    size_note = (f"smallest standard size at least as large: {shape[0]} vCPU, "
                                 f"{shape[1].normalize():f} GiB")
        elif provider == "gcp" and target.function == "managed_db":
            for key in ("vcpu", "memory_gib"):
                if key in source.profile.specs:
                    target.specs[key] = source.profile.specs[key]
        label, differences = quality(source.profile, target)
        if label == "no_equivalent":
            continue
        sizing = source.profile
        if provider == "gcp" and target.function == "vm" and "vcpu" in target.specs:
            sizing = ProductProfile(source.profile.function, source.profile.category,
                                    source.profile.unit_kind,
                                    {**source.profile.specs, "vcpu": target.specs["vcpu"],
                                     "memory_gib": target.specs["memory_gib"]})
        converted = convert(sizing, source.usage_quantity, target, target_provider=provider,
                            ram_sku=ram_sku)
        candidate = Candidate(
            source_ref=source.ref, provider=provider, region=region,
            service_code=row.service_code, sku=row.sku, label=product_label(row),
            profile=target, quality=label, differences=differences,
            price_types=tuple(row.price_types), unit=units.get(row.sku) or row.unit,
            ram_sku=ram_sku,
        )
        if isinstance(converted, Converted):
            candidate.quantity = converted.quantity
            candidate.options = converted.options
            if converted.options and converted.options.get("os"):
                target.specs["os"] = converted.options["os"]
                candidate.quality, candidate.differences = quality(source.profile, target)
            candidate.usage_note = size_note or converted.note
        else:
            candidate.unconvertible = converted.reason
            if candidate.quality in ("exact", "close"):
                candidate.quality = "partial"
                candidate.differences = [*differences, f"usage can't be converted: "
                                         f"{converted.reason}"]
        out.append(candidate)
    # Products of the same function first; others only when nothing of the same function
    # exists (the honest closest, labelled partial).
    same = [c for c in out if c.profile.function == source.profile.function]
    out = same or out
    out.sort(key=lambda c: _rank_key(source.profile, c))
    return out[:TOP_N]


async def find_candidates(
    book: MatchBook,
    sources: list[SourceProduct],
    targets: dict[str, str],
    *,
    hints: dict[str, str] | None = None,
    progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, dict[str, list[Candidate]]]:
    """Candidates per source reference and target provider; also stored in `book`. Sources with
    nothing comparable are recorded in `book.unmatched` with the reason."""
    hints = hints or {}
    searcher = _Searcher()
    # Start every search now, so they run while earlier sources are being ranked.
    for source in sources:
        for provider, region in targets.items():
            for filters in targeted_searches(provider, source.profile):
                searcher.search(provider, region, filters)
                if source.ref in hints:
                    searcher.search(provider, region, {**filters, "text": hints[source.ref]})
    units: dict[tuple[str, str], dict[str, str | None]] = {}
    results: dict[str, dict[str, list[Candidate]]] = {}
    for done, source in enumerate(sources, start=1):
        results[source.ref] = {}
        for provider, region in targets.items():
            searches = targeted_searches(provider, source.profile)
            if not searches:
                book.unmatched[(source.ref, provider)] = (
                    "the app has no comparable product type for this service")
                results[source.ref][provider] = []
                continue
            rows: list[CatalogItem] = []
            for filters in searches:
                if source.ref in hints:
                    rows.extend(await searcher.search(
                        provider, region, {**filters, "text": hints[source.ref]}))
                rows.extend(await searcher.search(provider, region, filters))
            row_units: dict[str, str | None] = {}
            if provider == "aws":
                cache = units.setdefault(("aws", region), {})
                missing = sorted({r.sku for r in rows} - set(cache))
                if missing:
                    cache.update(await asyncio.to_thread(_aws_units, region, missing))
                row_units = cache
            found = await _candidates_for(source, provider, region, rows, row_units,
                                          _gcp_ram_skus(rows) if provider == "gcp" else {})
            broad = SEARCHES[provider].get(source.profile.function, [])
            if not found and broad and broad != searches:
                # Nothing in the narrowed search (say, no size with that vCPU count): the
                # closest product from the broad one, labelled by the same rules.
                rows = []
                for filters in broad:
                    rows.extend(await searcher.search(provider, region, filters))
                if provider == "aws":
                    missing = sorted({r.sku for r in rows} - set(row_units))
                    if missing:
                        row_units.update(await asyncio.to_thread(_aws_units, region, missing))
                found = await _candidates_for(source, provider, region, rows, row_units,
                                              _gcp_ram_skus(rows) if provider == "gcp" else {})
            for candidate in found:
                book.add_candidate(candidate)
            if not found:
                book.unmatched[(source.ref, provider)] = "no product in the same category"
            results[source.ref][provider] = found
        if progress is not None:
            progress(done, len(sources), "Matching services")
    return results
