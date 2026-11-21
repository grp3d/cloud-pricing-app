"""Product profiles (024, research R2): the few comparable facts about a catalog product.

A profile is built from a `CatalogItem` only, with explicit per-provider tables in the style of
`pricing_data/providers/units.py`. Anything not recognized is left out (a spec is absent, the
unit kind is "unknown", the function is "other"); nothing is guessed. Quality (`quality.py`)
treats a spec one side lacks as a difference, so a missing fact can't make a match look exact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from src.pricing_data.providers.base import CatalogItem

# The functions products are compared by, and the app category each belongs to.
FUNCTION_CATEGORY: dict[str, str] = {
    "vm": "compute",
    "serverless_requests": "compute",
    "serverless_compute": "compute",
    "container_cluster": "compute",
    "managed_db": "database",
    "db_storage": "database",
    "cache": "database",
    "object_storage": "storage",
    "object_requests_write": "storage",
    "object_requests_read": "storage",
    "block_storage": "storage",
    "file_storage": "storage",
    "data_transfer": "networking",
    "load_balancer": "networking",
    "load_balancer_capacity": "networking",
    "dns_queries": "networking",
}

FUNCTION_LABELS: dict[str, str] = {
    "vm": "virtual machine",
    "serverless_requests": "serverless function requests",
    "serverless_compute": "serverless function compute",
    "container_cluster": "container cluster",
    "managed_db": "managed database instance",
    "db_storage": "managed database storage",
    "cache": "in-memory cache",
    "object_storage": "object storage",
    "object_requests_write": "object storage write requests",
    "object_requests_read": "object storage read requests",
    "block_storage": "block storage",
    "file_storage": "file storage",
    "data_transfer": "data transfer",
    "load_balancer": "load balancer",
    "load_balancer_capacity": "load balancer capacity units",
    "dns_queries": "DNS queries",
    "other": "other service",
}


@dataclass
class ProductProfile:
    function: str
    category: str | None
    unit_kind: str
    specs: dict[str, object] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return FUNCTION_LABELS.get(self.function, self.function)


# --- Billing unit kinds -------------------------------------------------------------------------
# Every provider's base unit (after the adapters' block normalisation) → a kind. Same kind means
# the same quantity can be priced on both sides (research R4).

_UNIT_KINDS: dict[str, str] = {}
for kind, units in {
    "hour": ("Hrs", "Hours", "Hour", "hour", "hours", "Hourly", "Instance-hrs", "usagehours",
             "h", "1 Hour", "1/Hour", "/Hour"),
    "gb_month": ("GB-Mo", "GB-Month", "GB/Month", "1 GB/Month", "GiBy.mo", "GBy.mo"),
    "tb_month": ("TB-Mo", "TB/Month", "1 TB/Month", "TiBy.mo"),
    "gb": ("GB", "1 GB", "GiBy", "GBy"),
    "tb": ("TB", "1 TB", "TiBy", "Terabytes"),
    "request": ("Requests", "Request", "API Request", "Queries", "Query", "count", "", "1",
                "10", "100", "10K", "1M", "1K", "100K", "10M"),
    "gb_second": ("GB-Second", "GB-Seconds", "Lambda-GB-Second", "GiBy.s", "1 GB Second"),
    "vcpu_hour": ("vCPU-Hours", "vCPU-Hour", "1 vCPU Hour"),
    "gib_hour": ("GiBy.h", "GB-Hours", "GB-Hour", "GB/Hour"),
    "lcu_hour": ("LCU-Hrs", "LCU-Hours"),
    "dpu_hour": ("DPU-Hour", "DPU-Hours"),
}.items():
    for unit in units:
        _UNIT_KINDS[unit] = kind


def unit_kind(unit: str | None) -> str:
    if unit is None:
        return "unknown"
    return _UNIT_KINDS.get(unit.strip(), "unknown")


# --- Shared parsing ----------------------------------------------------------------------------


def _number(text: str | None) -> Decimal | None:
    if not text:
        return None
    match = re.search(r"\d+(?:\.\d+)?", text.replace(",", ""))
    if not match:
        return None
    try:
        return Decimal(match.group())
    except InvalidOperation:  # pragma: no cover - the regex only admits numbers
        return None


def _engine(text: str) -> str | None:
    lower = text.lower()
    if "postgres" in lower:
        return "postgresql"
    if "mysql" in lower:
        return "mysql"
    if "sql server" in lower or "sqlserver" in lower:
        return "sqlserver"
    if "redis" in lower or "valkey" in lower:
        return "redis"
    if "memcache" in lower:
        return "memcached"
    return None


# Storage access classes, by the words each provider uses for them.
_STORAGE_CLASSES = (
    ("archive instant retrieval", "cold"),
    ("glacier instant", "cold"),
    ("deep archive", "archive"),
    ("glacier", "archive"),
    ("archive", "archive"),
    ("coldline", "cold"),
    ("cold", "cold"),
    ("nearline", "cool"),
    ("infrequent access", "cool"),
    ("cool", "cool"),
    ("general purpose", "hot"),
    ("standard", "hot"),
    ("hot", "hot"),
)


def _storage_class(text: str) -> str | None:
    lower = text.lower()
    for word, klass in _STORAGE_CLASSES:
        if word in lower:
            return klass
    return None


def _redundancy_azure(sku_name: str) -> str | None:
    upper = f" {sku_name.upper()} "
    for code, redundancy in (("RA-GZRS", "geo"), ("GZRS", "geo"), ("RA-GRS", "geo"),
                             ("GRS", "geo"), ("ZRS", "zonal"), ("LRS", "local")):
        if f" {code} " in upper or upper.strip().endswith(code):
            return redundancy
    return None


# --- AWS -------------------------------------------------------------------------------------


def _aws(item: CatalogItem) -> tuple[str, dict]:
    a = item.attributes
    code, family = item.service_code, item.product_family or ""
    specs: dict[str, object] = {}
    instance = a.get("instanceType", "")

    def sizes() -> None:
        if (v := _number(a.get("vcpu"))) is not None:
            specs["vcpu"] = int(v)
        if (m := _number(a.get("memory"))) is not None:
            specs["memory_gib"] = m
        # Graviton: a "g" after the generation digit (t4g, m6g, r6gd, db.r6g, cache.m6g).
        name = instance.split(".", 1)[-1] if instance.startswith(("db.", "cache.")) else instance
        if re.match(r"^[a-z]+\d+[a-z]*g", name.split(".")[0] or ""):
            specs["arch"] = "arm"
        elif instance:
            specs["arch"] = "x86"
        if name:
            specs["burstable"] = name.startswith("t")
        if (purpose := _aws_purpose(a.get("instanceFamily", ""), name)) is not None:
            specs["purpose"] = purpose

    if code == "AmazonEC2" and family == "Compute Instance":
        sizes()
        if a.get("operatingSystem"):
            specs["os"] = "linux" if a["operatingSystem"].lower() == "linux" else (
                a["operatingSystem"].lower())
        return "vm", specs
    if code == "AmazonEC2" and family == "Storage":
        return "block_storage", specs
    if code == "AmazonRDS" and family == "Database Instance":
        sizes()
        if (engine := _engine(a.get("databaseEngine", ""))) is not None:
            specs["engine"] = engine
        specs["ha"] = "multi-az" in a.get("deploymentOption", "").lower()
        return "managed_db", specs
    if code == "AmazonRDS" and family == "Database Storage":
        if (engine := _engine(a.get("databaseEngine", ""))) is not None:
            specs["engine"] = engine
        specs["ha"] = "multi-az" in a.get("deploymentOption", "").lower()
        return "db_storage", specs
    if code == "AmazonElastiCache" and family == "Cache Instance":
        sizes()
        if (engine := _engine(a.get("cacheEngine", ""))) is not None:
            specs["engine"] = engine
        return "cache", specs
    if code == "AmazonS3" and family == "Storage":
        if (klass := _storage_class(a.get("storageClass", ""))) is not None:
            specs["storage_class"] = klass
        specs["redundancy"] = "zonal"  # S3 storage classes other than One Zone span zones
        if "one zone" in a.get("storageClass", "").lower():
            specs["redundancy"] = "local"
        return "object_storage", specs
    if code == "AmazonS3" and family == "API Request":
        group = a.get("group", "")
        usage = a.get("usagetype", "")
        # Plain "Requests-Tier1/2" are S3 Standard's; other classes name theirs (GIR, SIA…).
        specs["storage_class"] = (
            "cold" if "GIR" in usage else "cool" if re.search(r"SIA|ZIA", usage)
            else "archive" if re.search(r"GDA|Glacier", usage) else "hot")
        specs["redundancy"] = "local" if "ZIA" in usage else "zonal"
        if "Tier1" in group:
            return "object_requests_write", specs
        if "Tier2" in group:
            return "object_requests_read", specs
    if code == "AmazonEFS":
        return "file_storage", specs
    if code == "AWSDataTransfer" or family == "Data Transfer":
        usage = a.get("usagetype", "")
        specs["transfer"] = ("inter_region" if re.search(r"AWS-(Out|In)-Bytes", usage)
                             else "internet" if "DataTransfer-Out-Bytes" in usage else "other")
        if specs["transfer"] == "inter_region":
            specs.update(_aws_destination(a.get("toRegionCode")))
        return "data_transfer", specs
    if family.startswith("Load Balancer"):
        usage = a.get("usagetype", "")
        layer = family.removeprefix("Load Balancer").strip("-").lower() or "classic"
        specs["lb_layer"] = layer
        if layer == "application":
            specs["lb_edition"] = "standard"
        return ("load_balancer_capacity" if "LCU" in usage else "load_balancer"), specs
    if code == "AmazonRoute53" and family == "DNS Query":
        specs["visibility"] = "public"
        return "dns_queries", specs
    if code == "AWSLambda":
        group = a.get("group", "")
        return ("serverless_compute" if "Duration" in group else "serverless_requests"), specs
    if code == "AmazonEKS" and "perCluster" in a.get("usagetype", ""):
        return "container_cluster", specs
    return "other", specs


def _aws_purpose(instance_family: str, name: str) -> str | None:
    lower = instance_family.lower()
    for word, purpose in (("general", "general"), ("compute", "compute"), ("memory", "memory"),
                          ("storage", "storage"), ("gpu", "accelerated"),
                          ("accelerat", "accelerated"), ("fpga", "accelerated"),
                          ("machine learning", "accelerated")):
        if word in lower:
            return purpose
    letter = name[:1]
    return {"t": "general", "m": "general", "c": "compute", "r": "memory", "x": "memory",
            "z": "memory", "i": "storage", "d": "storage", "p": "accelerated",
            "g": "accelerated"}.get(letter)


# --- Azure -----------------------------------------------------------------------------------

# Memory per vCPU by VM family letter (Azure's published series ratios). A family that isn't
# here (B, M, N…) has no memory spec, so it can be at most a close match.
_AZURE_MEMORY_PER_VCPU = {"D": Decimal(4), "E": Decimal(8), "F": Decimal(2), "L": Decimal(8)}
_AZURE_SIZE = re.compile(r"^Standard_([A-Z]+)(\d+)([a-z]*)(?:-\d+)?[a-z]*(?:_v(\d+))?", re.I)


def _azure_vm_specs(arm_sku_name: str) -> dict:
    specs: dict[str, object] = {}
    match = _AZURE_SIZE.match(arm_sku_name or "")
    if not match:
        return specs
    family, vcpu, features = match.group(1).upper(), int(match.group(2)), match.group(3)
    specs["vcpu"] = vcpu
    confidential = family.startswith(("DC", "EC"))
    per = None if confidential else _AZURE_MEMORY_PER_VCPU.get(family[0])
    if not confidential and "l" in features:
        per = Decimal(2)  # "l": low memory, 2 GiB per vCPU (Dlsv5, Bplsv2…)
    elif family.startswith("B") and "m" in features:
        per = Decimal(4)
    if per is not None:
        specs["memory_gib"] = per * vcpu
    specs["arch"] = "arm" if "p" in features else "x86"
    specs["burstable"] = family.startswith("B")
    specs["purpose"] = ("confidential" if confidential else
                        {"D": "general", "B": "general", "A": "general", "E": "memory",
                         "M": "memory", "F": "compute", "L": "storage", "N": "accelerated",
                         "H": "hpc"}.get(family[0], "other"))
    return specs


def _azure(item: CatalogItem) -> tuple[str, dict]:
    a = item.attributes
    service = (item.service_name or "").lower()
    product = a.get("product_name", item.product_family or "")
    sku_name = a.get("sku_name", "")
    meter = a.get("meter_name", "")
    specs: dict[str, object] = {}
    if item.kind == "vm":
        specs.update(_azure_vm_specs(a.get("arm_sku_name", sku_name)))
        if "windows" in product.lower():
            specs["os"] = "windows"
        return "vm", specs
    if item.kind == "managed_db" or service.startswith("azure database for"):
        if (engine := _engine(item.service_name or product)) is not None:
            specs["engine"] = engine
        if "storage" in product.lower() and "compute" not in product.lower():
            return "db_storage", specs
        # Flexible Server compute is single-zone; high availability is a separate meter. The
        # series named in the product (Ddsv5, Edsv5…) says the processor (p = Arm).
        specs["ha"] = False
        series = re.search(r"\b[A-Z][a-z]*v\d\b", product)
        if series:
            specs["arch"] = "arm" if "p" in series.group()[1:] else "x86"
        lower = product.lower()
        if "memory optimized" in lower or "mem opt" in lower or "memory opt" in lower:
            per, specs["purpose"] = Decimal(8), "memory"
        elif "general purpose" in lower or "gen purp" in lower:
            per, specs["purpose"] = Decimal(4), "general"
        elif "burstable" in lower:
            per, specs["purpose"], specs["burstable"] = None, "general", True
        else:
            per = None
        if "burstable" not in lower and "purpose" in specs:
            specs["burstable"] = False
        if (vcores := _number(sku_name)) is not None and "vcore" in sku_name.lower():
            specs["vcpu"] = int(vcores)
            if per is not None:
                specs["memory_gib"] = per * int(vcores)
        return "managed_db", specs
    if "redis" in service or "redis" in product.lower():
        specs["engine"] = "redis"
        return "cache", specs
    if item.kind == "object_storage" or (service == "storage" and "block blob" in
                                         product.lower()):
        lower = meter.lower()
        if (klass := _storage_class(sku_name)) is not None:
            specs["storage_class"] = klass
        if (redundancy := _redundancy_azure(sku_name)) is not None:
            specs["redundancy"] = redundancy
        if "write operations" in lower:
            return "object_requests_write", specs
        if "read operations" in lower:
            return "object_requests_read", specs
        if "data stored" not in lower:
            return "other", specs
        return "object_storage", specs
    if item.kind == "block_storage" or "managed disks" in service:
        return "block_storage", specs
    if service == "storage" and "files" in product.lower():
        return "file_storage", specs
    if item.kind == "data_transfer" or service == "bandwidth":
        text = f"{product} {meter}".lower()
        specs["transfer"] = ("inter_region" if re.search(
            r"inter[- ]region|intra continent|inter continent", text)
            else "internet" if ("internet" in text or "data transfer out" in text) else "other")
        return "data_transfer", specs
    if service == "load balancer":
        text = f"{product} {meter}".lower()
        specs["lb_layer"] = ("gateway" if "gateway" in text else "global" if "global" in text
                             else "network")
        return ("load_balancer_capacity" if "data processed" in meter.lower()
                else "load_balancer"), specs
    if service == "application gateway":
        lower_product, lower_meter = product.lower(), meter.lower()
        # Only the v2 gateways: v1 is being retired, "for Containers" is a separate Kubernetes
        # ingress product, and a "Discounted" product is a price offer, not an edition.
        if ("v2" not in lower_product or "for containers" in lower_product
                or "discounted" in lower_product or "captcha" in lower_meter):
            return "other", specs
        specs["lb_layer"] = "application"
        specs["lb_edition"] = ("waf" if "waf" in lower_product else
                               "basic" if "basic" in lower_product else
                               "confidential" if "confidential" in lower_meter else "standard")
        return ("load_balancer_capacity" if "capacity unit" in lower_meter
                or "data processed" in lower_meter else "load_balancer"), specs
    if service == "azure dns" and "queries" in meter.lower():
        specs["visibility"] = "private" if "private" in meter.lower() else "public"
        return "dns_queries", specs
    if "kubernetes service" in service and item.unit and "hour" in item.unit.lower():
        return "container_cluster", specs
    if service == "functions":
        return ("serverless_compute" if "execution time" in meter.lower()
                else "serverless_requests"), specs
    return "other", specs


# --- GCP -------------------------------------------------------------------------------------

_GCP_ARM_FAMILIES = {"T2A", "C4A", "N4A"}
_GCP_PURPOSE = {
    **dict.fromkeys(("E2", "N1", "N2", "N2D", "N4", "N4D", "N4A", "T2D", "T2A", "C4A"),
                    "general"),
    **dict.fromkeys(("C2", "C2D", "C3", "C3D", "C4", "C4D", "H3", "H4D"), "compute"),
    **dict.fromkeys(("M1", "M2", "M3", "M4", "X4"), "memory"),
    **dict.fromkeys(("A2", "A3", "A4", "G2", "G4"), "accelerated"),
    "Z3": "storage",
}


def _gcp(item: CatalogItem) -> tuple[str, dict]:
    taxonomy = item.product_family or ""
    parts = [p.strip() for p in taxonomy.split(">")]
    summary = item.summary or ""
    specs: dict[str, object] = {}
    if item.kind == "vm":
        family = parts[-1] if parts else ""
        specs["family"] = family
        specs["arch"] = "arm" if family.upper() in _GCP_ARM_FAMILIES else "x86"
        specs["os"] = "linux"  # core and RAM prices carry no OS licence
        specs["burstable"] = False
        specs["purpose"] = _GCP_PURPOSE.get(family.upper(), "other")
        return "vm", specs
    if item.kind == "managed_db" or (len(parts) > 1 and parts[0] == "Databases"):
        if (engine := _engine(" ".join(parts) + " " + summary)) is not None:
            specs["engine"] = engine
        if "Persistent Disk" in parts or "Storage" in parts or "storage" in summary.lower():
            if "Cloud SQL" in taxonomy or "Cloud SQL" in summary:
                specs["ha"] = "regional" in summary.lower()
            return "db_storage", specs
        if "vCPU" in summary or "Cores" in " ".join(parts) or "CPU" in " ".join(parts):
            specs["ha"] = "regional" in summary.lower()
            specs["arch"] = "x86"
            return "managed_db", specs
        if "Memorystore" in taxonomy or "Redis" in taxonomy:
            specs.setdefault("engine", "redis")
            return "cache", specs
        return "other", specs
    operations = re.search(r"Class ([AB]) Operations", summary)
    if operations and (item.service_name or "").startswith("Cloud Storage") or (
            operations and "GCS" in taxonomy):
        if (klass := _storage_class(summary)) is not None:
            specs["storage_class"] = klass
        lower = summary.lower()
        specs["redundancy"] = ("geo" if "multi-region" in lower or "dual-region" in lower
                               else "zonal")
        return ("object_requests_write" if operations.group(1) == "A"
                else "object_requests_read"), specs
    if item.kind == "object_storage":
        if (klass := _storage_class(parts[-2] if len(parts) > 1 else summary)) is not None:
            specs["storage_class"] = klass
        last = parts[-1].lower() if parts else ""
        specs["redundancy"] = "geo" if last.startswith("multi") else "zonal"
        return "object_storage", specs
    if item.kind == "block_storage":
        return "block_storage", specs
    if item.kind == "data_transfer" or "Egress" in parts:
        lower = summary.lower()
        specs["transfer"] = ("inter_region" if re.search(r"inter[- ]region", lower)
                             else "internet" if "internet" in lower else "other")
        if specs["transfer"] == "inter_region":
            specs.update(_gcp_destination(summary))
        return "data_transfer", specs
    if "Forwarding Rule" in summary or "Cloud Load Balancing" in taxonomy:
        lower = summary.lower()
        if "application load balancer" in lower:
            specs["lb_layer"] = "application"
        elif "network load balanc" in lower or "passthrough" in lower:
            specs["lb_layer"] = "network"
        return ("load_balancer_capacity" if "Data Processing" in summary
                else "load_balancer"), specs
    if summary.startswith("DNS Query") or "Cloud DNS" in taxonomy:
        specs["visibility"] = "public"
        return "dns_queries", specs
    if re.search(r"kubernetes clusters|cluster management", summary, re.I) and item.unit == "h":
        return "container_cluster", specs
    return "other", specs


_BUILDERS = {"aws": _aws, "azure": _azure, "gcp": _gcp}


def profile(item: CatalogItem, *, unit: str | None = None,
            category: str | None = None) -> ProductProfile:
    """The profile of `item`. `unit` overrides `item.unit` (AWS catalog items carry no unit;
    the caller resolves it per pricing term). `category` is the app's category when the caller
    has one (the `Categorizer`); otherwise it comes from the function."""
    function, specs = _BUILDERS[item.provider](item)
    resolved_unit = unit if unit is not None else item.unit
    return ProductProfile(
        function=function,
        category=FUNCTION_CATEGORY.get(function, category),
        unit_kind=unit_kind(resolved_unit),
        specs=specs,
    )


def product_label(item: CatalogItem) -> str:
    """A readable name for a product in answers, the Results pane and the CSV."""
    a = item.attributes
    if item.provider == "aws":
        name = item.service_name or a.get("servicename") or item.service_code
        detail = a.get("instanceType") or a.get("storageClass") or a.get("usagetype") or ""
        family = item.product_family or ""
        bits = [name]
        if family and family not in name:
            bits.append(family)
        if detail:
            bits.append(detail)
        return " · ".join(bits)
    if item.provider == "azure":
        product = a.get("product_name", item.product_family or "")
        sku = a.get("arm_sku_name") or a.get("sku_name") or ""
        meter = a.get("meter_name", "")
        bits = [product]
        if sku and sku not in product:
            bits.append(sku)
        if meter and meter not in (sku, product) and meter not in product:
            bits.append(meter)
        return " · ".join(b for b in bits if b)
    return item.summary or item.product_family or item.sku


# --- Where a transfer between regions goes -------------------------------------------------------
# A price for transfer between regions is for one destination: a part of the world (GCP's "to
# Americas") or one place (GCP's "to Columbus"; AWS's destination region). `dest_geo` is the
# destination's geography, or a group of them; `dest_place` is the one place, where there is one.

DESTINATION_GROUPS = {
    "americas": ("north_america", "south_america"),
    "north america": ("north_america",),
    "northern america": ("north_america",),
    "south america": ("south_america",),
    "latin america": ("south_america",),
    "europe": ("europe",),
    "emea": ("europe", "middle_east", "africa"),
    "apac": ("asia_pacific",),
    "asia": ("asia_pacific",),
    "asia pacific": ("asia_pacific",),
    "oceania": ("asia_pacific",),
    "middle east": ("middle_east",),
    "africa": ("africa",),
}


def _aws_destination(region_code: str | None) -> dict:
    from src.agent.matching.regions import locations

    where = locations().get("aws", {}).get(region_code or "")
    if where is None:
        return {}
    return {"dest_geo": where["geography"], "dest_place": where["city"]}


def _gcp_destination(summary: str) -> dict:
    match = re.search(r" to (.+?)\s*$", summary)
    if not match:
        return {}
    name = match.group(1).strip()
    if name.lower() in DESTINATION_GROUPS:
        return {"dest_geo": name.lower()}
    return {"dest_place": name}


def destination_covers(target_geo: str, source_geo: str) -> bool:
    """Whether a price for transfer to `target_geo` (a geography or a group) applies to transfer
    to a region in `source_geo`."""
    return source_geo in DESTINATION_GROUPS.get(target_geo, (target_geo,))


def same_place(target: str, source: str) -> bool:
    """Whether two place names are the same place ("Virginia" and "Northern Virginia" are)."""
    a, b = target.lower().strip(), source.lower().strip()
    return a == b or a.endswith(f" {b}") or b.endswith(f" {a}")
