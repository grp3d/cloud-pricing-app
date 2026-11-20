"""Resolve the four standard architectures to concrete pricing-data SKUs and write the seed
(014-architecture-templates-import-export, research.md §1-§5).

Reads `docs/brief/common_aws_architectures.md` (pure JSON) as the reference for which architectures,
regions, and components exist, applies the explicit per-figure rules in
`scripts/standard_architectures/match_rules.py` against the real pricing dataset, and writes:

- `src/db/seed/standard_architectures.json` — the seed, in the architecture export format;
  inserted once per database by migration `0005_standard_architectures`.
- `src/db/seed/standard_architectures_report.md` — every matched SKU and every figure left out,
  with the reason (spec FR-010).

Neither output is ever hand-edited — change the rules and re-run. Re-running against the same
snapshot produces byte-identical files. Afterwards, rebuild the CI Parquet fixture so it covers
the seeded SKUs (`scripts/build_test_pricing_fixture.py`).

    uv run python scripts/resolve_standard_architectures.py \\
        [--source ../docs/brief/common_aws_architectures.md] [--data-uri file:///…/DATA/pipeline]

018-app-cloud-deployment: the pricing data is read through the pipeline's manifests, exactly as
the app reads it (`--data-uri` defaults to `PRICING_DATA_URI`; pin the AWS date with
`ACTIVE_SNAPSHOT_DATE`; the checked-in AWS seed is from 2026-09-24).

022-gcp-azure-standard-architectures: `--provider gcp|azure` applies
`match_rules_gcp.py` / `match_rules_azure.py` against that provider's latest snapshot and writes
`standard_architectures_<provider>.json` and `standard_architectures_<provider>_report.md`
(contracts/generator.md). The AWS default and its two files are unchanged.

    uv run python scripts/resolve_standard_architectures.py --provider gcp
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from datetime import date
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    # Run as a plain script, Python puts `scripts/` (not `backend/`) on the path.
    sys.path.insert(0, str(BACKEND))

from scripts.standard_architectures.resolver import (  # noqa: E402
    UnrecognizedUnitError,
    render_report,
    resolve,
    to_export_file,
    to_service_mappings,
)
from src.config import settings  # noqa: E402
from src.pricing_data.active_snapshot import select_snapshot  # noqa: E402
from src.pricing_data.snapshot import ActiveSnapshot  # noqa: E402
from src.pricing_data.storage import LocalStore, open_store  # noqa: E402

DEFAULT_SOURCE = BACKEND.parent / "docs" / "brief" / "common_aws_architectures.md"
SEED_DIR = BACKEND / "src" / "db" / "seed"


RULE_MODULES = {
    "aws": "scripts.standard_architectures.match_rules",
    "gcp": "scripts.standard_architectures.match_rules_gcp",
    "azure": "scripts.standard_architectures.match_rules_azure",
}


def _outputs(provider: str) -> tuple[Path, Path]:
    stem = "standard_architectures" if provider == "aws" else f"standard_architectures_{provider}"
    return SEED_DIR / f"{stem}.json", SEED_DIR / f"{stem}_report.md"


def _without_empty_options(seed: dict) -> dict:
    """Drop `provider_options: null` (019) so selections without options serialize exactly as
    before 019 — the AWS seed stays byte-identical (022 FR-009)."""
    for architecture in seed["architectures"]:
        for collection in architecture["collections"]:
            for selection in collection["sku_selections"]:
                if selection.get("provider_options") is None:
                    selection.pop("provider_options", None)
    return seed


def _snapshot(data_uri: str, provider: str, pinned: date | None = None) -> ActiveSnapshot:
    """The snapshot `latest.json` names (or, for AWS, `ACTIVE_SNAPSHOT_DATE`'s; or `pinned`),
    read in place."""
    settings.pricing_data_uri = data_uri
    store = open_store(settings)
    if not isinstance(store, LocalStore):
        raise SystemExit("--data-uri must be a local pipeline storage root")
    if pinned is None:
        pinned = settings.active_snapshot_date if provider == "aws" else None
    selection = select_snapshot(store, provider, pinned, at_startup=True)
    if selection.manifest is None:
        reason = selection.reason or (selection.rejected.reason if selection.rejected else "")
        raise SystemExit(f"no usable pricing snapshot at {data_uri}: {reason}")
    return ActiveSnapshot.from_manifest(selection.manifest, base_dir=store.root, pinned=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--provider", choices=sorted(RULE_MODULES), default="aws")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument(
        "--data-uri",
        default=settings.pricing_data_uri,
        help="local pipeline storage root (default: PRICING_DATA_URI)",
    )
    parser.add_argument(
        "--mappings", action="store_true",
        help="026: write only service_mappings_<provider>.json, from the snapshots the seeds "
             "were made from",
    )
    args = parser.parse_args()
    if not args.data_uri:
        raise SystemExit("set PRICING_DATA_URI or pass --data-uri")
    if args.mappings:
        return write_mappings(args.provider, args.data_uri)

    source = json.loads(args.source.read_text())
    rules = importlib.import_module(RULE_MODULES[args.provider])
    snapshot = _snapshot(args.data_uri, args.provider)
    missing = sorted(set(getattr(rules, "REGIONS", {}).values()) - set(snapshot.locations()))
    if missing:
        raise SystemExit(
            f"the {args.provider} snapshot {snapshot.snapshot_date} has no data for: "
            f"{', '.join(missing)}"
        )

    try:
        resolution = resolve(
            rules.RULES,
            files=snapshot.files,
            snapshot_date=snapshot.snapshot_date,
            provider=args.provider,
        )
    except UnrecognizedUnitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    export = to_export_file(
        resolution, source, provider=args.provider, regions=getattr(rules, "REGIONS", None)
    )
    empty = [
        a.name for a in export.architectures if not any(c.sku_selections for c in a.collections)
    ]
    if empty:
        print(f"error: no priced entries resolved for: {', '.join(empty)}", file=sys.stderr)
        return 1

    SEED_DIR.mkdir(parents=True, exist_ok=True)
    seed_path, report_path = _outputs(args.provider)
    seed = json.dumps(_without_empty_options(export.model_dump(mode="json")), indent=2) + "\n"
    seed_path.write_text(seed)
    report_path.write_text(render_report(resolution, source, provider=args.provider))

    print(
        f"{args.provider} snapshot {snapshot.snapshot_date}: "
        f"{len(resolution.matches)} entries matched, "
        f"{len(resolution.omissions)} figures left out -> {SEED_DIR}"
    )
    return 0


def _report_date(provider: str) -> date:
    """The snapshot date a provider's seed was made from (its report's header)."""
    text = _outputs(provider)[1].read_text()
    found = re.search(r"Pricing snapshot: `(\d{4}-\d{2}-\d{2})`", text)
    if not found:
        raise SystemExit(f"no snapshot date in the {provider} report")
    return date.fromisoformat(found.group(1))


def _resolve_at(provider: str, data_uri: str):
    rules = importlib.import_module(RULE_MODULES[provider])
    snapshot = _snapshot(data_uri, provider, _report_date(provider))
    resolution = resolve(rules.RULES, files=snapshot.files,
                         snapshot_date=snapshot.snapshot_date, provider=provider)
    return snapshot, resolution


def write_mappings(provider: str, data_uri: str) -> int:
    """026 research R4: pair the AWS rules with `provider`'s, at the snapshots both seeds were
    made from (so the mapping names exactly the seeds' SKUs), and write
    `service_mappings_<provider>.json`. The seeds and reports are not touched."""
    from src.pricing_data.providers.registry import get_provider

    if provider == "aws":
        raise SystemExit("--mappings needs --provider gcp or azure")
    aws_snapshot, aws = _resolve_at("aws", data_uri)
    target_snapshot, target = _resolve_at(provider, data_uri)
    snapshots = {"aws": aws_snapshot, provider: target_snapshot}
    cache: dict[tuple[str, str, str, str], str] = {}

    def key_of(code: str, service_code: str, sku: str, region: str) -> str:
        wanted = (code, service_code, sku, region)
        if wanted not in cache:
            adapter = get_provider(code)
            found = adapter.describe(snapshots[code], [(service_code, sku)], region=region)
            if (service_code, sku) not in found:
                raise SystemExit(f"{code} {service_code} {sku} not found in {region}")
            item = found[(service_code, sku)]
            if code == "gcp" and not item.summary:
                raise SystemExit(f"gcp {sku} has no display name")
            cache[wanted] = adapter.product_key(item)
        return cache[wanted]

    mappings = to_service_mappings(aws, target, target_provider=provider, key_of=key_of)
    path = SEED_DIR / f"service_mappings_{provider}.json"
    path.write_text(json.dumps(mappings, indent=2, ensure_ascii=False) + "\n")
    print(f"{provider}: {len(mappings['mappings'])} mapping rows -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
