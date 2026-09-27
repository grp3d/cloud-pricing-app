"""Generate the canvas's AWS service -> icon mapping (015-canvas-service-icons, research.md §1/§4).

Approximately matches every service code in the pricing dataset against the file names of the
official AWS Architecture Service Icons (48-size SVG variant), applies the checked-in
`OVERRIDES` / `FAMILY_OVERRIDES` below, and writes:

- `frontend/src/lib/awsServiceIcons.generated.ts` — service code -> icon stem, plus
  (service code, product family) -> icon stem overrides, plus the fallback / data-transfer
  icon stems (data-model.md §2).
- `frontend/src/assets/aws-icons/*.svg` — only the icons those maps reference, plus the
  fallback (AWS Cloud group icon) and data-transfer (General "Data Stream" resource icon)
  light/dark variants.

It also prints a review report (matched / overridden / fallback) — the reviewable half of
spec FR-003. Neither output is ever hand-edited: change the overrides and re-run. Re-running
against the same icon package and snapshot produces byte-identical output.

With `--log-file PATH` (017-structured-json-logging, FR-009) it also writes one JSON log record
per service, family override and copied icon to PATH; the printed report is unchanged.

    uv run python scripts/generate_aws_service_icon_map.py \\
        --icons ../../images-web/aws_architecture_icons [--parquet /path/to/parquet] \\
        [--log-file report.jsonl]
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import sys
from pathlib import Path

import duckdb

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    # Run as a plain script, Python puts `scripts/` (not `backend/`) on the path.
    sys.path.insert(0, str(BACKEND))

from src.config import settings  # noqa: E402
from src.logging_config import configure_logging, get_logger  # noqa: E402

FRONTEND = BACKEND.parent / "frontend"
OUT_TS = FRONTEND / "src" / "lib" / "awsServiceIcons.generated.ts"
OUT_ICONS = FRONTEND / "src" / "assets" / "aws-icons"
# 016-canvas-icon-layout (research.md §4): the backend's copy of the same maps, so its
# icon-coverage analysis and the canvas always agree on which services fall back.
OUT_JSON = BACKEND / "src" / "pricing_data" / "aws_service_icons.json"

# Special icons (research.md §4) — outside the service-icon set, so copied under fixed stems.
FALLBACK_ICON = {"light": "AWS-Cloud-logo", "dark": "AWS-Cloud-logo_Dark"}
DATA_TRANSFER_ICON = {"light": "Data-Stream_Light", "dark": "Data-Stream_Dark"}
DATA_TRANSFER_SERVICE_CODE = "AWSDataTransfer"

# Service-code overrides: always beat the automatic match. Either a wrong fuzzy hit corrected,
# or a miss filled with the closest official icon (a renamed/sub-product/fee-only service).
OVERRIDES: dict[str, str] = {
    "AWSOutposts": "AWS-Outposts-family",
    "AmazonEKS": "Amazon-Elastic-Kubernetes-Service",
    "AmazonDocDB": "Amazon-DocumentDB",
    "ElasticMapReduce": "Amazon-EMR",
    "AmazonKinesisFirehose": "Amazon-Data-Firehose",
    "AmazonKinesisAnalytics": "Amazon-Managed-Service-for-Apache-Flink",
    "AmazonGlacier": "Amazon-Simple-Storage-Service-Glacier",
    "AmazonS3GlacierDeepArchive": "Amazon-Simple-Storage-Service-Glacier",
    "AmazonMCS": "Amazon-Keyspaces",
    "AmazonDAX": "Amazon-DynamoDB",
    "AmazonQuickSight": "Amazon-Quick",
    "AmazonQuickSuite": "Amazon-Quick",
    "AWSIoT": "AWS-IoT-Core",
    "AWSIoT1Click": "AWS-IoT-Core",
    "AWSIoTAnalytics": "AWS-IoT-Core",
    "AWSIoTThingsGraph": "AWS-IoT-Core",
    "AWSEvents": "Amazon-EventBridge",
    "AWSFIS": "AWS-Fault-Injection-Service",
    "AmazonGameLift": "Amazon-GameLift-Servers",
    "AmazonOmics": "AWS-HealthOmics",
    "AuroraDSQL": "Amazon-Aurora",
    "AmazonAppStream": "Amazon-WorkSpaces",
    "AmazonWAM": "Amazon-WorkSpaces",
    "AmazonWorkSpacesInstances": "Amazon-WorkSpaces",
    "AmazonWorkSpacesThinClient": "Amazon-WorkSpaces",
    "AmazonWorkSpacesWeb": "Amazon-WorkSpaces",
    "AmazonChimeBusinessCalling": "Amazon-Chime",
    "AmazonChimeCallMe": "Amazon-Chime",
    "AmazonChimeCallMeAMCS": "Amazon-Chime",
    "AmazonChimeDialInAMCS": "Amazon-Chime",
    "AmazonChimeDialin": "Amazon-Chime",
    "AmazonChimeFeatures": "Amazon-Chime",
    "AmazonChimeServices": "Amazon-Chime",
    "AmazonChimeVoiceConnector": "Amazon-Chime",
    "AmazonConnectCases": "Amazon-Connect",
    "AmazonConnectTalent": "Amazon-Connect",
    "AmazonConnectVoiceID": "Amazon-Connect",
    "ContactCenterTelecomm": "Amazon-Connect",
    "ContactLensAmazonConnect": "Amazon-Connect",
    "CustomerProfiles": "Amazon-Connect",
    "AWSWisdom": "Amazon-Connect",
    "AmazonBedrockFoundationModels": "Amazon-Bedrock",
    "AmazonBedrockMarketplace": "Amazon-Bedrock",
    "AmazonBedrockService": "Amazon-Bedrock",
    "AmazonKnowledgeBase": "Amazon-Bedrock",
    "AWSStorageGatewayDeepArchive": "AWS-Storage-Gateway",
    "IngestionService": "AWS-Snowball",
    "IngestionServiceSnowball": "AWS-Snowball",
    "SnowballExtraDays": "AWS-Snowball",
    "AmazonEC2OCPULicenseFees": "Amazon-EC2",
    "AmazonRDSOCPULicenseFees": "Amazon-RDS",
    "AmazonEVSLicensesIncluded": "Amazon-Elastic-VMware-Service",
    "AWSIAMAccessAnalyzer": "AWS-Identity-and-Access-Management",
    "AmazonLightsail": "Amazon-Lightsail-for-Research",
    "AWSGlueElasticViews": "AWS-Glue",
    "AmazonCognitoSync": "Amazon-Cognito",
    "AmazonETS": "AWS-Elemental-MediaConvert",
    "AmazonIVSChat": "Amazon-Interactive-Video-Service",
    "AmazonML": "Amazon-SageMaker-AI",
    "AWSEndUserMessaging3pFees": "AWS-End-User-Messaging",
    "mobileanalytics": "Amazon-Pinpoint",
    "NovaAct": "Amazon-Nova",
}

# (service code, product family) overrides — checked before the service-code map, so e.g. an
# EC2 NAT Gateway SKU shows the VPC icon rather than EC2's (research.md §1).
_EC2_EBS_FAMILIES = (
    "Storage",
    "Storage Snapshot",
    "EBS direct API Requests",
    "Fast Snapshot Restore",
    "ProvisionedRateVolumeInitialization",
    "Provisioned Throughput",
)
FAMILY_OVERRIDES: dict[str, dict[str, str]] = {
    "AmazonEC2": {
        **{family: "Amazon-Elastic-Block-Store" for family in _EC2_EBS_FAMILIES},
        "NAT Gateway": "Amazon-Virtual-Private-Cloud",
        "Load Balancer": "Elastic-Load-Balancing",
        "Load Balancer-Application": "Elastic-Load-Balancing",
        "Load Balancer-Network": "Elastic-Load-Balancing",
    },
    "AmazonVPC": {"VpcEndpoint": "AWS-PrivateLink"},
    "AmazonRDS": {"Aurora Global Database": "Amazon-Aurora"},
    "AmazonKinesis": {"Kinesis Streams": "Amazon-Kinesis-Data-Streams"},
}

_ICON_STEM = re.compile(r"^Arch_(?P<stem>.+)_48\.svg$")


def _normalize(name: str) -> str:
    lowered = re.sub(r"^(amazon|aws)[ -]?", "", name.lower())
    return re.sub(r"[^a-z0-9]", "", lowered)


def _single_dir(parent: Path, pattern: str) -> Path:
    matches = sorted(p for p in parent.glob(pattern) if p.is_dir())
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one {pattern!r} in {parent}, found {len(matches)}")
    return matches[0]


def _service_icons(icons_root: Path) -> dict[str, Path]:
    service_dir = _single_dir(icons_root, "Architecture-Service-Icons_*")
    icons: dict[str, Path] = {}
    for path in sorted(service_dir.glob("*/48/*.svg")):
        match = _ICON_STEM.match(path.name)
        if match:
            icons.setdefault(match["stem"], path)
    return icons


def _special_icons(icons_root: Path) -> dict[str, Path]:
    group_dir = _single_dir(icons_root, "Architecture-Group-Icons_*")
    general_dir = _single_dir(icons_root, "Resource-Icons_*") / "Res_General-Icons"
    sources = {
        FALLBACK_ICON["light"]: group_dir / "AWS-Cloud-logo_32.svg",
        FALLBACK_ICON["dark"]: group_dir / "AWS-Cloud-logo_32_Dark.svg",
        DATA_TRANSFER_ICON["light"]: general_dir / "Res_48_Light" / "Res_Data-Stream_48_Light.svg",
        DATA_TRANSFER_ICON["dark"]: general_dir / "Res_48_Dark" / "Res_Data-Stream_48_Dark.svg",
    }
    missing = [str(p) for p in sources.values() if not p.is_file()]
    if missing:
        raise SystemExit(f"special icon(s) missing: {missing}")
    return sources


def _latest_snapshot(parquet_dir: Path) -> str:
    dates = None
    for table in ("service_dim", "product_dim"):
        found = {
            p.name.removeprefix("snapshot_date=")
            for p in (parquet_dir / table).iterdir()
            if p.is_dir() and p.name.startswith("snapshot_date=")
        }
        dates = found if dates is None else dates & found
    if not dates:
        raise SystemExit(f"no snapshot common to service_dim and product_dim in {parquet_dir}")
    return max(dates)


def _pricing_services(
    parquet_dir: Path, snapshot: str
) -> tuple[dict[str, str | None], set[tuple[str, str]]]:
    """(service code -> service name, {(service code, product family)}) for one snapshot."""
    con = duckdb.connect(":memory:")
    partition = f"snapshot_date={snapshot}"
    product_glob = str(parquet_dir / "product_dim" / partition / "**" / "*.parquet")
    service_glob = str(parquet_dir / "service_dim" / partition / "**" / "*.parquet")
    families = {
        (code, family)
        for code, family in con.execute(
            "SELECT DISTINCT service_code, product_family FROM read_parquet(?) "
            "WHERE service_code IS NOT NULL AND coalesce(product_family, '') <> ''",
            [product_glob],
        ).fetchall()
    }
    names = dict(
        con.execute(
            "SELECT p.service_code, min(s.service_name) FROM "
            "(SELECT DISTINCT service_code FROM read_parquet(?)) p "
            "LEFT JOIN read_parquet(?) s USING (service_code) "
            "WHERE p.service_code IS NOT NULL GROUP BY 1",
            [product_glob, service_glob],
        ).fetchall()
    )
    return names, families


def _auto_match(
    code: str, name: str | None, by_normalized: dict[str, str]
) -> tuple[str | None, bool]:
    """(icon stem or None, fuzzy?) — exact on code, exact on name, then close match on name."""
    candidates = [_normalize(code)] + ([_normalize(name)] if name else [])
    for candidate in candidates:
        if candidate in by_normalized:
            return by_normalized[candidate], False
    close = difflib.get_close_matches(candidates[-1], sorted(by_normalized), n=1, cutoff=0.8)
    return (by_normalized[close[0]], True) if close else (None, False)


def build_mapping(
    names: dict[str, str | None], families: set[tuple[str, str]], icons: dict[str, Path]
) -> tuple[dict[str, str], dict[str, dict[str, str]], list[str], list[dict[str, str | None]]]:
    """(code -> stem, code -> family -> stem, printed report lines, one structured row per
    service and per family override — the `--log-file` records, 017 FR-009)."""
    by_normalized = {_normalize(stem): stem for stem in sorted(icons)}
    report: list[str] = []
    by_code: dict[str, str] = {}
    rows: dict[str, list[tuple[str, str]]] = {
        section: [] for section in ("matched", "fuzzy", "override", "fallback")
    }
    log_rows: list[dict[str, str | None]] = []

    def log_row(code: str, stem: str | None, match_type: str) -> None:
        log_rows.append(
            {
                "service_code": code,
                "service_name": names[code],
                "icon_file": f"{stem}.svg" if stem else None,
                "match_type": match_type,
            }
        )

    for code in sorted(names):
        if code == DATA_TRANSFER_SERVICE_CODE:
            rows["override"].append((code, "(data-transfer icon)"))
            log_row(code, None, "data_transfer")
            continue
        auto, fuzzy = _auto_match(code, names[code], by_normalized)
        if code in OVERRIDES:
            by_code[code] = OVERRIDES[code]
            rows["override"].append((code, f"{OVERRIDES[code]}  (auto: {auto or '-'})"))
            log_row(code, OVERRIDES[code], "override")
        elif auto:
            by_code[code] = auto
            rows["fuzzy" if fuzzy else "matched"].append((code, auto))
            log_row(code, auto, "fuzzy" if fuzzy else "matched")
        else:
            rows["fallback"].append((code, names[code] or ""))
            log_row(code, None, "fallback")

    by_family: dict[str, dict[str, str]] = {}
    for code, family_map in sorted(FAMILY_OVERRIDES.items()):
        for family, stem in sorted(family_map.items()):
            if (code, family) not in families:
                report.append(f"WARNING: family override ({code}, {family}) not in pricing data")
            by_family.setdefault(code, {})[family] = stem
            log_rows.append(
                {
                    "service_code": code,
                    "product_family": family,
                    "icon_file": f"{stem}.svg",
                    "match_type": "family_override",
                }
            )

    referenced = set(by_code.values()) | {s for m in by_family.values() for s in m.values()}
    unknown = sorted(s for s in referenced if s not in icons)
    if unknown:
        raise SystemExit(f"override(s) reference icon stems not in the package: {unknown}")

    total = len(names)
    mapped = total - len(rows["fallback"])
    for section, entries in rows.items():
        report.append(f"\n## {section} ({len(entries)})")
        report.extend(f"  {code:40} {detail}" for code, detail in entries)
    report.append(f"\nnon-fallback: {mapped}/{total} = {mapped / total:.1%}")
    return by_code, by_family, report, log_rows


def log_mapping(rows: list[dict[str, str | None]], copied_icons: list[str]) -> None:
    """017-structured-json-logging, FR-009: one record per service, family override and copied
    icon, through whatever `configure_logging` set up (the `--log-file` file)."""
    logger = get_logger("cloud_pricing.icon_map")
    for row in rows:
        if row["match_type"] == "family_override":
            logger.info("family icon override", **row)
        else:
            logger.info("service icon matched", **row)
    for icon_file in copied_icons:
        logger.info("icon copied", icon_file=icon_file)


_FAMILY_DOC = (
    "/** AWS service code -> product family -> icon file stem; checked before the map above. */"
)
_FAMILY_DECL = (
    "export const AWS_SERVICE_ICON_BY_CODE_AND_FAMILY: Record<string, Record<string, string>> = {"
)


def _ts_key(key: str) -> str:
    return key if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", key) else f'"{key}"'


def render_ts(
    by_code: dict[str, str], by_family: dict[str, dict[str, str]], package: str, snapshot: str
) -> str:
    lines = [
        "// Generated by backend/scripts/generate_aws_service_icon_map.py — do not edit by hand.",
        f"// Icons: {package} (48-size SVG). Service codes: pricing snapshot {snapshot}.",
        "// 015-canvas-service-icons, data-model.md §2.",
        "",
        "/** AWS service code -> icon file stem in `src/assets/aws-icons/`. */",
        "export const AWS_SERVICE_ICON_BY_CODE: Record<string, string> = {",
        *(f'  {_ts_key(code)}: "{stem}",' for code, stem in sorted(by_code.items())),
        "};",
        "",
        _FAMILY_DOC,
        _FAMILY_DECL,
    ]
    for code, family_map in sorted(by_family.items()):
        lines.append(f"  {_ts_key(code)}: {{")
        lines.extend(
            f'    {_ts_key(family)}: "{stem}",' for family, stem in sorted(family_map.items())
        )
        lines.append("  },")
    lines += [
        "};",
        "",
        "/** Shown for any service with no matched icon (FR-004). */",
        f'export const AWS_FALLBACK_ICON = {{ light: "{FALLBACK_ICON["light"]}", '
        f'dark: "{FALLBACK_ICON["dark"]}" }};',
        "",
        '/** AWSDataTransfer has no service icon; uses the General "Data Stream" resource icon. */',
        f'export const AWS_DATA_TRANSFER_ICON = {{ light: "{DATA_TRANSFER_ICON["light"]}", '
        f'dark: "{DATA_TRANSFER_ICON["dark"]}" }};',
        "",
    ]
    return "\n".join(lines)


def render_json(by_code: dict[str, str], by_family: dict[str, dict[str, str]]) -> str:
    """The backend copy of the maps — sorted keys, trailing newline, byte-stable across runs."""
    document = {
        "by_code": by_code,
        "by_code_and_family": by_family,
        "special_codes": [DATA_TRANSFER_SERVICE_CODE],
    }
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--icons", required=True, type=Path, help="aws_architecture_icons dir")
    parser.add_argument("--parquet", type=Path, default=Path(settings.aws_pricing_parquet_dir))
    parser.add_argument(
        "--log-file",
        type=Path,
        help="also write one JSON log record per service and copied icon to this file",
    )
    args = parser.parse_args()

    icons = _service_icons(args.icons)
    special = _special_icons(args.icons)
    snapshot = _latest_snapshot(args.parquet)
    names, families = _pricing_services(args.parquet, snapshot)
    by_code, by_family, report, rows = build_mapping(names, families, icons)

    package = _single_dir(args.icons, "Architecture-Service-Icons_*").name
    OUT_TS.write_text(render_ts(by_code, by_family, package, snapshot), encoding="utf-8")
    OUT_JSON.write_text(render_json(by_code, by_family), encoding="utf-8")

    if OUT_ICONS.exists():
        shutil.rmtree(OUT_ICONS)
    OUT_ICONS.mkdir(parents=True)
    referenced = set(by_code.values()) | {s for m in by_family.values() for s in m.values()}
    copied: list[str] = []
    for stem in sorted(referenced):
        shutil.copyfile(icons[stem], OUT_ICONS / f"{stem}.svg")
        copied.append(f"{stem}.svg")
    for stem, source in special.items():
        shutil.copyfile(source, OUT_ICONS / f"{stem}.svg")
        copied.append(f"{stem}.svg")

    if args.log_file:
        with args.log_file.open("w", encoding="utf-8") as log_stream:
            configure_logging(level="INFO", fmt="json", stream=log_stream)
            log_mapping(rows, copied)
        configure_logging(settings.log_level, settings.log_format)  # don't keep the closed file

    print("\n".join(report))
    icon_count = len(referenced) + len(special)
    print(f"\nwrote {OUT_TS.relative_to(BACKEND.parent)} and {icon_count} icons")


if __name__ == "__main__":
    main()
