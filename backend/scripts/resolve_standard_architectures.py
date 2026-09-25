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
        [--source ../docs/common_aws_architectures.md] [--parquet /path/to/parquet] \\
        [--snapshot-date YYYY-MM-DD]
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

DEFAULT_SOURCE = BACKEND.parent / "docs" / "common_aws_architectures.md"
SEED_DIR = BACKEND / "src" / "db" / "seed"


def _latest_snapshot(parquet_dir: Path) -> str:
    dates = None
    for table in ("product_dim", "price_fact"):
        found = {
            p.name.removeprefix("snapshot_date=")
            for p in (parquet_dir / table).iterdir()
            if p.is_dir() and p.name.startswith("snapshot_date=")
        }
        dates = found if dates is None else dates & found
    if not dates:
        raise SystemExit(f"no snapshot common to product_dim and price_fact in {parquet_dir}")
    return max(dates)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--parquet", type=Path, default=Path(settings.aws_pricing_parquet_dir))
    parser.add_argument("--snapshot-date", default=None)
    args = parser.parse_args()

    source = json.loads(args.source.read_text())
    snapshot_date = args.snapshot_date or _latest_snapshot(args.parquet)

    try:
        resolution = resolve(RULES, parquet_dir=args.parquet, snapshot_date=snapshot_date)
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
        f"snapshot {snapshot_date}: {len(resolution.matches)} entries matched, "
        f"{len(resolution.omissions)} figures left out -> {SEED_DIR}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
