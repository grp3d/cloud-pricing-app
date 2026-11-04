"""The on-disk layout of one provider's price history (019, data-model §7).

    PRICING_HISTORY_DIR/<provider>/
        prices/<date>-r<rev>.parquet        newest comparable price list only
        pairs/<from_date>_<to_date>/
            changes.parquet                 one row per item whose price changed
            counts.parquet                  one row per (location, service_key)
            pair.json                       provenance: both snapshots, built_at, builder version
        state.json                          weeks, gaps, backfill progress, last error

Everything here is derived and rebuildable from the snapshots; it is not in Postgres and not
backed up. Every write is atomic (a temporary name, then a rename), so an interrupted build never
leaves a half-written file that looks complete: a pair counts only once its `pair.json` exists.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
from pathlib import Path
from typing import Any

STATE_FILE = "state.json"
PAIR_FILE = "pair.json"


class HistoryStore:
    def __init__(self, root: Path | str, provider: str) -> None:
        self.provider = provider
        self.dir = Path(root) / provider
        self.prices_dir = self.dir / "prices"
        self.pairs_dir = self.dir / "pairs"

    # --- state ---------------------------------------------------------------------------

    def state(self) -> dict[str, Any]:
        try:
            return json.loads((self.dir / STATE_FILE).read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_state(self, state: dict[str, Any]) -> None:
        write_json(self.dir / STATE_FILE, state)

    def update_state(self, **changes: Any) -> dict[str, Any]:
        state = self.state()
        state.update(changes)
        self.save_state(state)
        return state

    # --- price lists -----------------------------------------------------------------------

    def prices_path(self, snapshot_date: str, revision: int) -> Path:
        return self.prices_dir / f"{snapshot_date}-r{revision}.parquet"

    def keep_only_prices(self, *keep: Path | None) -> None:
        """Remove every price list except `keep` (only the newest is kept, R10)."""
        if not self.prices_dir.is_dir():
            return
        kept = {k for k in keep if k is not None}
        for path in self.prices_dir.glob("*.parquet"):
            if path not in kept:
                path.unlink(missing_ok=True)

    # --- pairs -----------------------------------------------------------------------------

    def pair_dir(self, from_date: str, to_date: str) -> Path:
        return self.pairs_dir / f"{from_date}_{to_date}"

    def pair_meta(self, from_date: str, to_date: str) -> dict[str, Any] | None:
        try:
            return json.loads((self.pair_dir(from_date, to_date) / PAIR_FILE).read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def pairs(self) -> list[tuple[Path, dict[str, Any]]]:
        """Every complete pair (its `pair.json` exists), oldest first."""
        if not self.pairs_dir.is_dir():
            return []
        found = []
        for path in sorted(self.pairs_dir.iterdir()):
            if not path.is_dir() or path.name.startswith("."):
                continue
            try:
                found.append((path, json.loads((path / PAIR_FILE).read_text())))
            except (FileNotFoundError, json.JSONDecodeError):
                continue
        return found

    def new_pair_tmp(self) -> Path:
        tmp = self.pairs_dir / f".tmp-{secrets.token_hex(4)}"
        tmp.mkdir(parents=True)
        return tmp

    def publish_pair(self, tmp: Path, from_date: str, to_date: str) -> Path:
        """Move a fully written pair into place, replacing an older build of it."""
        final = self.pair_dir(from_date, to_date)
        if final.exists():
            old = self.pairs_dir / f".old-{secrets.token_hex(4)}"
            final.rename(old)
            shutil.rmtree(old, ignore_errors=True)
        tmp.rename(final)
        return final

    def remove_pair(self, path: Path) -> None:
        shutil.rmtree(path, ignore_errors=True)

    def clear(self) -> None:
        """Remove every pair and price list (a builder version change rebuilds all)."""
        shutil.rmtree(self.pairs_dir, ignore_errors=True)
        shutil.rmtree(self.prices_dir, ignore_errors=True)

    def clean_temporaries(self) -> None:
        shutil.rmtree(self.dir / ".duckdb-tmp", ignore_errors=True)
        shutil.rmtree(self.prices_dir / ".duckdb-tmp", ignore_errors=True)
        if self.pairs_dir.is_dir():
            for path in self.pairs_dir.iterdir():
                if path.name.startswith((".tmp-", ".old-")):
                    shutil.rmtree(path, ignore_errors=True)
        if self.prices_dir.is_dir():
            for path in self.prices_dir.glob("*.tmp-*"):
                path.unlink(missing_ok=True)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{secrets.token_hex(4)}")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    os.replace(tmp, path)
