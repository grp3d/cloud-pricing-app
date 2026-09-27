"""016-canvas-icon-layout, FR-023 (research.md §4): the backend's icon map and the canvas's are
generated together and must say the same thing, so the Admin Issues table and the canvas always
agree on which services fall back to the generic icon."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND_JSON = ROOT / "backend" / "src" / "pricing_data" / "aws_service_icons.json"
FRONTEND_TS = ROOT / "frontend" / "src" / "lib" / "awsServiceIcons.generated.ts"

_ENTRY = re.compile(r'^\s*"?([^":]+?)"?:\s*"([^"]+)",$')


def _ts_object(ts: str, name: str) -> dict:
    """Parse one exported object literal from the generated TS (flat or one level nested)."""
    body = ts.split(f"export const {name}", 1)[1].split("\n};", 1)[0].split("\n", 1)[1]
    result: dict = {}
    current: dict | None = None
    for line in body.splitlines():
        if line.rstrip().endswith("{"):
            key = line.strip().removesuffix(": {").strip('"')
            current = result.setdefault(key, {})
        elif line.strip() == "},":
            current = None
        elif match := _ENTRY.match(line):
            (current if current is not None else result)[match[1]] = match[2]
    return result


def test_backend_and_frontend_icon_maps_match():
    backend = json.loads(BACKEND_JSON.read_text())
    ts = FRONTEND_TS.read_text()
    assert backend["by_code"] == _ts_object(ts, "AWS_SERVICE_ICON_BY_CODE")
    assert backend["by_code_and_family"] == _ts_object(ts, "AWS_SERVICE_ICON_BY_CODE_AND_FAMILY")
    assert backend["special_codes"] == ["AWSDataTransfer"]
