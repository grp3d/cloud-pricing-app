"""Resolve the four standard architectures to concrete pricing-data SKUs and write the seed
(014-architecture-templates-import-export, research.md §1-§5).

Reads `docs/common_aws_architectures.md` (pure JSON) as the reference for which architectures,
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
        [--source ../docs/common_aws_architectures.md] [--data-uri file:///…/DATA/pipeline]

018-app-cloud-deployment: the pricing data is read through the pipeline's manifests, exactly as
the app reads it (`--data-uri` defaults to `PRICING_DATA_URI`; pin a date with
`ACTIVE_SNAPSHOT_DATE`).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    # Run as a plain script, Python puts `scripts/` (not `backend/`) on the path.
    sys.path.insert(0, str(BACKEND))

from scripts.standard_architectures.match_rules import RULES  # noqa: E402
from scripts.standard_architectures.resolver import (  # noqa: E402
    UnrecognizedUnitError,
    render_report,
    resolve,
    to_export_file,
)
from src.config import settings  # noqa: E402
from src.pricing_data.active_snapshot import PROVIDER, select_snapshot  # noqa: E402
from src.pricing_data.snapshot import ActiveSnapshot  # noqa: E402
from src.pricing_data.storage import LocalStore, open_store  # noqa: E402

DEFAULT_SOURCE = BACKEND.parent / "docs" / "common_aws_architectures.md"
SEED_DIR = BACKEND / "src" / "db" / "seed"


def _snapshot(data_uri: str) -> ActiveSnapshot:
    """The snapshot `latest.json` names (or `ACTIVE_SNAPSHOT_DATE`'s), read in place."""
    settings.pricing_data_uri = data_uri
    store = open_store(settings)
    if not isinstance(store, LocalStore):
        raise SystemExit("--data-uri must be a local pipeline storage root")
    selection = select_snapshot(store, PROVIDER, settings.active_snapshot_date, at_startup=True)
    if selection.manifest is None:
        reason = selection.reason or (selection.rejected.reason if selection.rejected else "")
        raise SystemExit(f"no usable pricing snapshot at {data_uri}: {reason}")
    return ActiveSnapshot.from_manifest(selection.manifest, base_dir=store.root, pinned=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument(
        "--data-uri",
        default=settings.pricing_data_uri,
        help="local pipeline storage root (default: PRICING_DATA_URI)",
    )
    args = parser.parse_args()
    if not args.data_uri:
        raise SystemExit("set PRICING_DATA_URI or pass --data-uri")

    source = json.loads(args.source.read_text())
    snapshot = _snapshot(args.data_uri)

    try:
        resolution = resolve(RULES, files=snapshot.files, snapshot_date=snapshot.snapshot_date)
    except UnrecognizedUnitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    export = to_export_file(resolution, source)
    empty = [
        a.name for a in export.architectures if not any(c.sku_selections for c in a.collections)
    ]
    if empty:
        print(f"error: no priced entries resolved for: {', '.join(empty)}", file=sys.stderr)
        return 1

    SEED_DIR.mkdir(parents=True, exist_ok=True)
    seed = json.dumps(export.model_dump(mode="json"), indent=2) + "\n"
    (SEED_DIR / "standard_architectures.json").write_text(seed)
    (SEED_DIR / "standard_architectures_report.md").write_text(render_report(resolution, source))

    print(
        f"snapshot {snapshot.snapshot_date}: {len(resolution.matches)} entries matched, "
        f"{len(resolution.omissions)} figures left out -> {SEED_DIR}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
