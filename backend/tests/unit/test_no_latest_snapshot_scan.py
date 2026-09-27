"""016-canvas-icon-layout, FR-014: no pricing lookup may pick its own snapshot date — every one
goes through the active snapshot. The old per-call "newest folder" scan must be gone."""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"


def test_no_module_scans_for_the_latest_snapshot_itself():
    offenders = [
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if "resolve_latest_snapshot_date" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
