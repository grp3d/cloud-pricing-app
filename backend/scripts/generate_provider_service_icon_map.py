"""Generate the canvas's GCP or Azure service -> icon maps (020, research R4/R5, data-model §5).

Matches every service in the provider's newest pricing snapshot against the file names of the
provider's official architecture icons, applies the checked-in `OVERRIDES` and
`FAMILY_OVERRIDES` below, and writes:

- `frontend/src/lib/{gcp,azure}ServiceIcons.generated.ts`: service id -> icon stem
  (`<P>_SERVICE_ICON_BY_ID`), plus per service an ordered list of more specific icons
  (`<P>_SERVICE_ICON_OVERRIDES`, first match wins). GCP matches a taxonomy prefix of the
  selection's product family; Azure a case-insensitive product-name pattern.
- `frontend/src/assets/{gcp,azure}-icons/*.svg`: only the icons those maps reference, copied
  unmodified (FR-014). Other `.svg` files there are removed; `README.md` is kept.

It also prints a review report: matched, overridden, fallback, and every service the category
rules (`src/db/seed/service_categories.json`) put in compute, storage, database or networking
that still has no icon. That last list must be empty (SC-003). Neither output is ever
hand-edited: change the overrides and re-run. Re-running against the same icon package and
snapshot produces byte-identical output (FR-010).

Matching is exact on a normalized name, never fuzzy: with ~1,700 GCP services, nearly all of
them marketplace software, fuzzy matching would put first-party icons on third-party products
(research R5). Marketplace-only GCP services are never matched automatically.

The AWS script (`generate_aws_service_icon_map.py`) and its outputs are separate and untouched
(FR-012).

    uv run python scripts/generate_provider_service_icon_map.py --provider gcp \\
        --icons ../../images-web/gcp_architecture_icons [--data-uri file:///…/_DATA-PIPELINE] \\
        [--log-file report.jsonl]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    # Run as a plain script, Python puts `scripts/` (not `backend/`) on the path.
    sys.path.insert(0, str(BACKEND))

from src.config import settings  # noqa: E402
from src.logging_config import configure_logging, get_logger  # noqa: E402
from src.pricing_data.active_snapshot import select_snapshot  # noqa: E402
from src.pricing_data.snapshot import ActiveSnapshot  # noqa: E402
from src.pricing_data.snapshot_cache import ensure_cached  # noqa: E402
from src.pricing_data.storage import LocalStore, open_store  # noqa: E402

FRONTEND = BACKEND.parent / "frontend"
CATEGORY_RULES = BACKEND / "src" / "db" / "seed" / "service_categories.json"
CATEGORIES = frozenset({"compute", "storage", "database", "networking"})
PROVIDERS = ("gcp", "azure")

# --- Checked-in, reviewed overrides (T019, T020) ---------------------------------------------
#
# OVERRIDES: service id -> icon stem (or None to force the fallback tile).
# FAMILY_OVERRIDES: service id -> ordered [(match, icon stem)]. GCP: a prefix of the taxonomy
# path (the selection's product family, e.g. "Compute > Persistent Disk > SSD"). Azure: a
# case-insensitive regular expression searched in the product name.
#
# Azure stems are the icon's name (`NNNNN-icon-service-<Name>.svg` -> `<Name>`, with anything
# but letters and digits collapsed to single '-'); `<Name>@NNNNN` names one of several same-named files.

_GCP_COMPUTE_ENGINE = "6F81-5844-456A"
_GCP_NETWORKING = "E505-1604-58F8"
_AZURE_STORAGE = "DZH317F1HKN0"
_AZURE_VIRTUAL_NETWORK = "DZH314HC0WV9"

OVERRIDES: dict[str, dict[str, str | None]] = {
    "gcp": {
        # Categorized services whose names don't match an icon (SC-003): the closest product.
        "116A-ED39-D1F0": "Database-Migration-Service",  # Database Migration
        "1C58-CF90-9614": "Firestore",  # Firebase Realtime Database
        "253F-1ADF-B066": "Cloud-Load-Balancing",  # MultiClusterIngress
        "2662-232A-AC11": "Cloud-CDN",  # Firebase Hosting
        "274C-338F-BD68": "Cloud-Storage",  # Cloud FTP
        "29E7-DA93-CA13": "Cloud-Functions",  # Cloud Run Functions
        "2E81-DB3E-82E2": "Google-Kubernetes-Engine",  # Fleets
        "3450-1C42-A427": "Filestore",  # Parallelstore
        "3A1B-66C4-2BAE": "PubSub",  # Pub/Sub Lite
        "3C58-66D1-EF70": "Cloud-SQL",  # Firebase Data Connect (PostgreSQL)
        "3DAD-299B-0D94": "Cloud-Storage",  # Backup and DR Service
        "46C7-B8CB-DDAA": "Filestore",  # Elastifile Cloud File System
        "4A40-16E8-DE2D": "Cloud-Storage",  # Actifio GO (backup)
        "5AF5-2C11-D467": "Memorystore",  # Cloud Memorystore for Redis
        "5E18-9A83-2867": "GCE-Systems-Management",  # VM Manager
        "7929-AEC3-626F": "Cloud-Storage",  # Backup for GKE
        "7C52-19D8-71EE": "Cloud-Healthcare-API",  # Cloud Healthcare
        "874A-0461-8D2D": "GCE-Systems-Management",  # Workload Manager
        "9544-7B1C-811D": "PubSub",  # Managed Service for Apache Kafka
        "9C2E-5AAC-D058": "Memorystore",  # Cloud Memorystore for Memcached
        "9C87-5BCE-65DD": "Cloud-Storage",  # Storage Insights
        "B384-1FDE-A709": "Filestore",  # Managed Lustre
        "C49F-B7F2-7416": "Cloud-SQL",  # AlloyDB
        "CAE2-A537-4A95": "Cloud-Code",  # Source Repository
        "D961-88BE-4D2D": "Transfer",  # Transfer Service
        "DCC9-8DB9-673F": "BigQuery",  # BigQuery Storage API
        "DE5F-D84C-F733": "Cloud-Build",  # Remote Build Execution
        _GCP_NETWORKING: "Virtual-Private-Cloud",  # Networking
        "FC86-5113-7C81": "Filestore",  # NetApp Volumes
        "FD92-362A-08B1": "Cloud-Network",  # Spectrum SAS
        # Other first-party services with an unambiguous icon.
        "02DA-B362-D983": "Text-To-Speech",  # Cloud Text-to-Speech API
        "04C4-B046-D8B2": "Cloud-Natural-Language-API",  # Cloud Natural Language
        "1C2D-8C78-EC58": "Apigee-API-Platform",  # Apigee
        "1DB1-3CD3-35A3": "Cloud-Translation-API",  # Translate
        "63DE-82AB-F564": "Speech-To-Text",  # Cloud Speech API
        "9186-F79E-3871": "Anthos",  # GKE Enterprise / GDC
        "D870-408D-92A6": "Document-AI",  # Cloud Document AI API
        "EE2F-D110-890C": "Key-Management-Service",  # Cloud Key Management Service (KMS)
        "FBC0-AA4A-C89A": "Dialogflow",  # Cloud Dialogflow API
    },
    "azure": {
        # Categorized services whose names don't match an icon (SC-003).
        "DZH31484J1FJ": "AKS-Network-Policy",  # Advanced Container Networking Services
        "DZH314G8RPTT": "Azure-SQL-Edge",  # SQL DB Edge
        "DZH314LP4PZS": "Cache-Redis",  # Redis Cache
        "DZH314N4QX7B": "CDN-Profiles",  # Content Delivery Network
        "DZH314W50487": "Virtual-Network-Gateways",  # VPN Gateway
        "DZH3155G7B5D": "Recovery-Services-Vaults",  # Backup
        "DZH3156C3V0M": "Arc-Data-services",  # Azure Arc Enabled Databases
        "DZH315LFVPHW": "Function-Apps",  # Durable Task Scheduler
        "DZH315TKSTVK": "Service-Fabric-Clusters",  # Service Fabric Mesh
        "DZH315ZLLZJN": "NAT",  # NAT Gateway
        "DZH3161MVRHW": "Virtual-Router",  # Azure Route Server
        "DZH31671GG75": "Cloud-Services-extended-support",  # Cloud Services
        "DZH316FV2P6G": "Mobile-Networks",  # Private Mobile Network
        "DZH316H7C4LW": "Web-Application-Firewall-Policies-WAF",  # Azure Adaptive Virtual Patching
        "DZH316MBDNZN": "Azure-HPC-Workbenches",  # Specialized Compute
        "DZH3179L81S9": "Service-Fabric-Clusters",  # Service Fabric
        _AZURE_STORAGE: "Storage-Accounts",  # Storage
        "DZH317NR0P99": "Azure-Database-MySQL-Server",  # Azure Database for MySQL
        "DZH317NW2D37": "Managed-Instance-Apache-Cassandra",  # Managed Instance for Cassandra
        "DZH317WPTGV0": "Virtual-Machine",  # Virtual Machines Licenses
        "DZH318FHKQ5W": "Azure-Data-Transfer",  # Bandwidth
        "DZH318G5GS89": "Traffic-Manager-Profiles",  # Traffic Manager
        "DZH318VJKJ1B": "Front-Door-and-CDN-Profiles",  # Azure Front Door Service
        "DZH318Z695ZG": "DNS-Zones",  # Azure DNS
        "DZH31974T4H6": "Azure-Database-MariaDB-Server",  # Azure Database for MariaDB
        "DZH3199QPQTD": "Azure-Database-PostgreSQL-Server",  # Azure Database for PostgreSQL
        "DZH319F2869N": "ExpressRoute-Circuits",  # ExpressRoute
        "DZH319F70F09": "Container-Apps-Environments",  # Azure Container Apps
        "DZH319H1QMCH": "DDoS-Protection-Plans",  # Azure DDOS Protection
        "DZH319HJX2WX": "Function-Apps",  # Functions
        "DZH319HNCXC7": "Image-Templates",  # Azure VM Image Builder
        "DZH319P5C274": "StorSimple-Device-Managers",  # StorSimple
        "DZH319PSD84L": "Azure-HCP-Cache",  # HPC Cache
        # Other first-party services with an unambiguous icon.
        "DZH3140GXVMF": "Log-Analytics-Workspaces",  # Log Analytics
        "DZH314238G9D": "IoT-Central-Applications",  # IoT Central
        "DZH314H0T4NQ": "Data-Lake-Store-Gen1",  # Data Lake Store
        "DZH314KKHZC9": "Azure-Spring-Apps",  # Azure Spring Cloud
        "DZH315B3SJD3": "Azure-Maps-Accounts",  # Azure Maps
        "DZH315F9L8DM": "Container-Registries",  # Container Registry
        "DZH315GS6SRD": "Automation-Accounts",  # Automation
        "DZH315NX4WLD": "Event-Grid-Topics",  # Event Grid
        "DZH316FDRQQJ": "Stream-Analytics-Jobs",  # Stream Analytics
        "DZH3174MS2N2": "Recovery-Services-Vaults",  # Azure Site Recovery
        "DZH317L7SKHR": "Azure-Data-Explorer-Clusters",  # Azure Data Explorer
        "DZH317LJ9WLP": "Azure-Virtual-Desktop",  # Windows Virtual Desktop
        "DZH318FZ20SD": "API-Management-Services",  # API Management
    },
}

FAMILY_OVERRIDES: dict[str, dict[str, list[tuple[str, str]]]] = {
    "gcp": {
        _GCP_COMPUTE_ENGINE: [
            ("Compute > Persistent Disk", "Persistent-Disk"),  # disks and their snapshots
            ("Compute > Hyperdisk", "Persistent-Disk"),
            ("Compute > Local SSD", "Local-SSD"),
            ("Compute > GPUs", "Cloud-GPU"),
            ("Compute > Cloud TPU", "Cloud-TPU"),
            ("Compute > GCE > Network Other", "Cloud-External-IP-Addresses"),
            ("Network > Cloud VPN > IP Address", "Cloud-External-IP-Addresses"),
            ("Network > Cloud VPN", "Cloud-VPN"),
            ("Network > Cloud CDN", "Cloud-CDN"),
            ("Network > Interconnect", "Cloud-Interconnect"),
            ("Network > Fixed Price Interconnect", "Cloud-Interconnect"),
            ("Network > Cloud Armor", "Cloud-Armor"),
            ("Databases > Cloud SQL", "Cloud-SQL"),
        ],
        _GCP_NETWORKING: [
            ("Network > Network Other > NAT Gateway > Public NAT IP", "Cloud-External-IP-Addresses"),
            ("Network > Network Other > NAT Gateway", "Cloud-NAT"),
            ("Network > Cloud LB", "Cloud-Load-Balancing"),
            ("Network > GlobalFrontEnd", "Cloud-Load-Balancing"),
            ("Network > Cloud Armor", "Cloud-Armor"),
            ("Network > Cloud CDN", "Cloud-CDN"),
            ("Network > Cloud Media Edge", "Cloud-Media-Edge"),
            ("Network > Cloud DNS", "Cloud-DNS"),
            ("Network > Cloud Firewall", "Cloud-Firewall-Rules"),
            ("Network > Cloud VPN", "Cloud-VPN"),
            ("Network > Network Connectivity Center", "Network-Connectivity-Center"),
            ("Network > Network Intelligence Center", "Network-Intelligence-Center"),
            ("Network > Private Service Connect", "Private-Service-Connect"),
        ],
    },
    "azure": {
        _AZURE_STORAGE: [
            ("Managed Disks|Ultra Disks|Premium SSD v2|Disk Reservation", "Disks"),
            ("Data Lake Storage|ADLS", "Data-Lake-Storage-Gen1"),
            ("File Sync", "Storage-Sync-Services"),
            ("Files", "Azure-Fileshares"),
            ("Queues", "Storage-Queue"),
            ("Tables", "Table"),
            ("Elastic SAN", "Elastic-SAN"),
            ("Container Storage", "Azure-Container-Storage"),
        ],
        _AZURE_VIRTUAL_NETWORK: [
            ("IP Addresses", "Public-IP-Addresses"),
            ("Public IP Prefix", "Public-IP-Prefixes"),
            ("Private Link", "Private-Link"),
            ("Virtual Network Manager", "Network-Managers"),
        ],
    },
}

# GCP top-level taxonomy groups that hold only third-party products.
_GCP_THIRD_PARTY = frozenset({"Marketplace Services", "Third Party Services"})

# Words dropped before comparing names: the icon sets and the price lists disagree on them.
_STOP_WORDS = {
    "gcp": {"cloud", "google", "gcp"},
    "azure": {"azure", "microsoft"},
}

_AZURE_ICON = re.compile(r"^(?P<number>\d+)-icon-service-(?P<name>.+)\.svg$")


@dataclass(frozen=True)
class Service:
    service_id: str
    name: str
    # GCP: taxonomy paths (" > "-joined, without "GCP"); Azure: product names.
    families: tuple[str, ...] = ()
    categorized: bool = False
    first_party: bool = True


@dataclass
class Mapping:
    by_id: dict[str, str] = field(default_factory=dict)
    family_by_id: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    matched: list[str] = field(default_factory=list)
    overridden: list[str] = field(default_factory=list)
    fallback: list[str] = field(default_factory=list)
    uncovered: list[str] = field(default_factory=list)
    used_stems: list[str] = field(default_factory=list)
    report: list[str] = field(default_factory=list)
    rows: list[dict[str, str | None]] = field(default_factory=list)


# --- Names and icons ---------------------------------------------------------------------------


def normalize(name: str, provider: str) -> str:
    """Lower case, punctuation and the provider's stop words dropped, simple plurals folded
    ("Virtual Machines" and "Virtual-Machine" both give "virtualmachine")."""
    words = re.findall(r"[a-z0-9]+", name.lower())
    kept = [w for w in words if w not in _STOP_WORDS[provider]]
    folded = [w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w
              for w in kept]
    return "".join(folded)


def _azure_stem(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]*-[^A-Za-z0-9]*|[^A-Za-z0-9]+", "-", name).strip("-")


def index_icons(provider: str, icons_root: Path) -> dict[str, Path]:
    """Icon stem -> SVG file. GCP: `svg/<Stem>.svg`. Azure: every
    `NNNNN-icon-service-<Name>.svg`; one name in several files is `<Name>` for the
    lowest-numbered file and `<Name>@NNNNN` for each file."""
    if provider == "gcp":
        svg_dir = icons_root / "svg"
        if not svg_dir.is_dir():
            raise SystemExit(f"no svg/ folder in {icons_root}")
        return {p.stem: p for p in sorted(svg_dir.glob("*.svg"))}

    by_name: dict[str, list[tuple[int, str, Path]]] = {}
    for path in sorted(icons_root.rglob("*.svg")):
        match = _AZURE_ICON.match(path.name)
        if match:
            stem = _azure_stem(match["name"])
            by_name.setdefault(stem, []).append((int(match["number"]), str(path), path))
    if not by_name:
        raise SystemExit(f"no NNNNN-icon-service-*.svg files under {icons_root}")
    icons: dict[str, Path] = {}
    for stem, files in sorted(by_name.items()):
        files.sort()
        icons[stem] = files[0][2]
        for number, _key, path in files:
            icons.setdefault(f"{stem}@{number:05d}", path)
    return icons


def _family_matches(provider: str, pattern: str, family: str) -> bool:
    if provider == "gcp":
        return family == pattern or family.startswith(pattern + " > ")
    return re.search(pattern, family, re.IGNORECASE) is not None


def resolve(provider: str, mapping: Mapping, service_id: str, family: str | None) -> str | None:
    """The icon a selection gets — the same order the frontend uses (data-model §5)."""
    for entry in mapping.family_by_id.get(service_id, []):
        if family and _family_matches(provider, entry["match"], family):
            return entry["icon"]
    return mapping.by_id.get(service_id)


def build_mapping(
    provider: str,
    services: list[Service],
    icons: dict[str, Path],
    overrides: dict[str, str | None],
    family_overrides: dict[str, list[tuple[str, str]]],
) -> Mapping:
    def check(stem: str, where: str) -> None:
        if stem not in icons:
            raise SystemExit(f"{where}: icon {stem!r} is not in the icon package")

    by_normalized: dict[str, str] = {}
    for stem in sorted(icons):
        if "@" not in stem:
            by_normalized.setdefault(normalize(stem, provider), stem)

    mapping = Mapping()
    report = mapping.report
    names = {s.service_id: s for s in services}
    for service_id, entries in sorted(family_overrides.items()):
        for pattern, stem in entries:
            check(stem, f"family override ({service_id}, {pattern!r})")
    for service_id, stem in sorted(overrides.items()):
        if stem is not None:
            check(stem, f"override {service_id}")
        if service_id not in names:
            report.append(f"WARNING: override {service_id} is not in the pricing data")

    for service in sorted(services, key=lambda s: s.service_id):
        sid = service.service_id
        auto = by_normalized.get(normalize(service.name, provider)) if service.first_party else None
        if sid in overrides:
            stem = overrides[sid]
            mapping.overridden.append(sid)
            status = "override"
        elif auto:
            stem = auto
            mapping.matched.append(sid)
            status = "matched"
        else:
            stem = None
            status = "fallback"
        if stem is None:
            if status == "override":
                status = "override-fallback"
            mapping.fallback.append(sid)
        else:
            mapping.by_id[sid] = stem
        if service.categorized and stem is None:
            mapping.uncovered.append(sid)
        mapping.rows.append({"service_id": sid, "service_name": service.name, "status": status,
                             "icon": stem, "auto": auto})

    for service_id, entries in sorted(family_overrides.items()):
        service = names.get(service_id)
        if service is None:
            report.append(f"WARNING: family overrides for {service_id} — not in the pricing data")
            continue
        mapping.family_by_id[service_id] = [{"match": m, "icon": i} for m, i in entries]
        for pattern, stem in entries:
            hits = [f for f in service.families if _family_matches(provider, pattern, f)]
            if not hits:
                report.append(f"WARNING: family override ({service_id}, {pattern!r}) "
                              "matches no product")
            mapping.rows.append({"service_id": service_id, "service_name": service.name,
                                 "status": "family", "icon": stem, "auto": pattern})

    used = set(mapping.by_id.values())
    for entries in mapping.family_by_id.values():
        used.update(e["icon"] for e in entries)
    mapping.used_stems = sorted(used)

    def section(title: str, ids: list[str], detail) -> None:
        report.append(f"\n## {title} ({len(ids)})")
        report.extend(f"  {sid:<42} {detail(sid)}" for sid in ids)

    section("matched", mapping.matched, lambda sid: f"{mapping.by_id[sid]}  ({names[sid].name})")
    section("override", mapping.overridden,
            lambda sid: f"{mapping.by_id.get(sid) or '(fallback)'}  ({names[sid].name})")
    report.append(f"\n## family overrides ({sum(map(len, mapping.family_by_id.values()))})")
    for sid, entries in sorted(mapping.family_by_id.items()):
        for e in entries:
            report.append(f"  {sid:<42} {e['match']!r} -> {e['icon']}")
    first_party_fallback = [sid for sid in mapping.fallback if names[sid].first_party]
    section("fallback, first-party", first_party_fallback, lambda sid: names[sid].name)
    report.append(f"\n## fallback, marketplace ({len(mapping.fallback) - len(first_party_fallback)})")
    section("categorized services without an icon", mapping.uncovered,
            lambda sid: names[sid].name)
    total = len(services)
    with_icon = total - len(mapping.fallback)
    share = f"{100 * with_icon / total:.1f}%" if total else "n/a"
    report.append(f"\nwith an icon: {with_icon}/{total} = {share}; "
                  f"icons shipped: {len(mapping.used_stems)}")
    return mapping


# --- Outputs -------------------------------------------------------------------------------------

_PREFIX = {"gcp": "GCP", "azure": "AZURE"}
_MATCH_DOC = {
    "gcp": "`match` is a taxonomy prefix of the selection's product family",
    "azure": "`match` is a case-insensitive pattern searched in the selection's product name",
}


_IDENTIFIER = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
_PRINT_WIDTH = 100  # frontend/.prettierrc: the output is prettier-clean as written


def _ts_key(key: str) -> str:
    """An object key as prettier writes it (`quoteProps: "as-needed"`)."""
    return key if _IDENTIFIER.match(key) else json.dumps(key)


def _ts_entry(match: str, icon: str) -> list[str]:
    one_line = f"    {{ match: {json.dumps(match)}, icon: {json.dumps(icon)} }},"
    if len(one_line) <= _PRINT_WIDTH:
        return [one_line]
    return ["    {", f"      match: {json.dumps(match)},", f"      icon: {json.dumps(icon)},",
            "    },"]


def render_ts(provider: str, mapping: Mapping) -> str:
    prefix = _PREFIX[provider]
    lines = [
        "// Generated by backend/scripts/generate_provider_service_icon_map.py "
        f"--provider {provider} (020).",
        "// Do not edit by hand: change the script's overrides and re-run it.",
        "",
        "/** Service id -> icon stem (a file in `../assets/"
        f"{provider}-icons/`). */",
        f"export const {prefix}_SERVICE_ICON_BY_ID: Record<string, string> = {{",
    ]
    lines += [f"  {_ts_key(sid)}: {json.dumps(stem)},"
              for sid, stem in sorted(mapping.by_id.items())]
    lines += [
        "};",
        "",
        f"/** Service id -> more specific icons, in order; the first match wins. "
        f"{_MATCH_DOC[provider]}. */",
        f"export const {prefix}_SERVICE_ICON_OVERRIDES: Record<",
        "  string,",
        "  ReadonlyArray<{ match: string; icon: string }>",
        "> = {",
    ]
    for sid, entries in sorted(mapping.family_by_id.items()):
        lines.append(f"  {_ts_key(sid)}: [")
        for e in entries:
            lines += _ts_entry(e["match"], e["icon"])
        lines.append("  ],")
    lines += ["};", ""]
    return "\n".join(lines)


def copy_icons(icons: dict[str, Path], stems: list[str], out_dir: Path) -> None:
    """Copy exactly `stems` into `out_dir` as `<stem>.svg`, unmodified; drop any other SVG."""
    out_dir.mkdir(parents=True, exist_ok=True)
    wanted = {f"{stem}.svg" for stem in stems}
    for existing in out_dir.glob("*.svg"):
        if existing.name not in wanted:
            existing.unlink()
    for stem in stems:
        target = out_dir / f"{stem}.svg"
        source = icons[stem]
        if not target.exists() or target.read_bytes() != source.read_bytes():
            shutil.copyfile(source, target)


# --- Categories (the seed rules, applied as the app does) --------------------------------------


def load_category_rules(path: Path = CATEGORY_RULES) -> list[dict]:
    rules = json.loads(path.read_text())["rules"]
    return [r for r in rules if r["category"] in CATEGORIES]


def gcp_categorized(taxonomy: list[str], rules: list[dict]) -> bool:
    """`taxonomy` without its leading "GCP"; level 1 and level 2 rules."""
    levels = {"taxonomy_1": taxonomy[0] if taxonomy else None,
              "taxonomy_2": taxonomy[1] if len(taxonomy) > 1 else None}
    return any(r["provider"] == "gcp" and levels.get(r["match_field"]) == r["match_value"]
               for r in rules)


def azure_categorized(service_family: str, service_name: str, rules: list[dict]) -> bool:
    values = {"service_family": service_family, "service_name": service_name}
    return any(r["provider"] == "azure" and values.get(r["match_field"]) == r["match_value"]
               for r in rules)


# --- Reading the pricing data ------------------------------------------------------------------


def _latest_snapshot(provider: str, data_uri: str) -> ActiveSnapshot:
    settings.pricing_data_uri = data_uri
    store = open_store(settings)
    selection = select_snapshot(store, provider, None, at_startup=True)
    if selection.manifest is None:
        reason = selection.reason or (selection.rejected.reason if selection.rejected else "")
        raise SystemExit(f"no usable {provider} pricing snapshot at {data_uri}: {reason}")
    if isinstance(store, LocalStore):
        return ActiveSnapshot.from_manifest(selection.manifest, base_dir=store.root, pinned=False)
    cached = ensure_cached(store, selection.manifest, Path(settings.pricing_cache_dir),
                           settings.pricing_cache_max_bytes)
    return ActiveSnapshot.from_manifest(cached.manifest, base_dir=cached.path, pinned=False)


def _files(snapshot: ActiveSnapshot, table: str) -> list[str]:
    return [f for region in sorted(snapshot.regions(table)) for f in snapshot.files(table, region)]


def read_services(provider: str, snapshot: ActiveSnapshot, rules: list[dict]) -> list[Service]:
    con = duckdb.connect(":memory:")
    try:
        if provider == "gcp":
            rows = con.execute(
                "SELECT k.service_id, any_value(s.display_name), "
                "list(DISTINCT array_to_string(k.product_taxonomy[2:], ' > ')), "
                "list(DISTINCT k.product_taxonomy[2:3]) "
                "FROM read_parquet(?) k LEFT JOIN read_parquet(?) s USING (service_id) "
                "GROUP BY 1",
                [_files(snapshot, "sku"), _files(snapshot, "service")],
            ).fetchall()
            return [
                Service(
                    service_id=sid,
                    name=name or sid,
                    families=tuple(sorted(f for f in paths if f)),
                    categorized=any(gcp_categorized(list(levels or []), rules)
                                    for levels in level_lists),
                    first_party=any((levels or [None])[0] not in _GCP_THIRD_PARTY
                                    for levels in level_lists),
                )
                for sid, name, paths, level_lists in rows
            ]
        rows = con.execute(
            "SELECT service_id, any_value(service_name), list(DISTINCT product_name), "
            "list(DISTINCT [service_family, service_name]) "
            "FROM read_parquet(?, union_by_name = true) GROUP BY 1",
            [_files(snapshot, "price_item")],
        ).fetchall()
        return [
            Service(
                service_id=sid,
                name=name or sid,
                families=tuple(sorted(p for p in products if p)),
                categorized=any(azure_categorized(fam or "", svc or "", rules)
                                for fam, svc in pairs),
            )
            for sid, name, products, pairs in rows
        ]
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--provider", required=True, choices=PROVIDERS)
    parser.add_argument("--icons", required=True, type=Path,
                        help="gcp_architecture_icons or azure_architecture_icons folder")
    parser.add_argument("--data-uri", default=settings.pricing_data_uri,
                        help="pricing data root (default: PRICING_DATA_URI)")
    parser.add_argument("--log-file", type=Path,
                        help="also write one JSON log record per service and override")
    args = parser.parse_args()
    provider = args.provider

    snapshot = _latest_snapshot(provider, args.data_uri)
    services = read_services(provider, snapshot, load_category_rules())
    icons = index_icons(provider, args.icons)
    mapping = build_mapping(provider, services, icons, OVERRIDES[provider],
                            FAMILY_OVERRIDES[provider])

    out_ts = FRONTEND / "src" / "lib" / f"{provider}ServiceIcons.generated.ts"
    out_ts.write_text(render_ts(provider, mapping))
    copy_icons(icons, mapping.used_stems, FRONTEND / "src" / "assets" / f"{provider}-icons")

    print(f"{provider} snapshot {snapshot.snapshot_date} r{snapshot.revision}: "
          f"{len(services)} services")
    print("\n".join(mapping.report))
    if args.log_file:
        with args.log_file.open("w", encoding="utf-8") as log_stream:
            configure_logging(level="INFO", fmt="json", stream=log_stream)
            log = get_logger("icon_map")
            for row in mapping.rows:
                log.info("service icon", provider=provider, **row)
            for stem in mapping.used_stems:
                log.info("icon copied", provider=provider, icon=f"{stem}.svg")
        configure_logging(settings.log_level, settings.log_format)  # don't keep the closed file
    print(f"\nwrote {out_ts.relative_to(BACKEND.parent)} and {len(mapping.used_stems)} icons")


if __name__ == "__main__":
    main()
