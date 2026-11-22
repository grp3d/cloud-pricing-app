"""016-canvas-icon-layout, FR-023 (research.md §4): the backend's icon map and the canvas's are
generated together and must say the same thing, so the Admin Issues table and the canvas always
agree on which services fall back to the generic icon."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

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


# --- 027 (FR-015, research R7): the GCP and Azure maps ------------------------------------------

_OVERRIDE = re.compile(
    r'\{\s*match:\s*("(?:[^"\\]|\\.)*"),\s*icon:\s*("(?:[^"\\]|\\.)*"),?\s*\}', re.S
)


def _ts_provider_maps(provider: str, prefix: str) -> tuple[dict, dict]:
    ts = (ROOT / "frontend" / "src" / "lib" / f"{provider}ServiceIcons.generated.ts").read_text()
    by_id = _ts_object(ts, f"{prefix}_SERVICE_ICON_BY_ID")
    body = ts.split(f"export const {prefix}_SERVICE_ICON_OVERRIDES", 1)[1].split("\n};", 1)[0]
    overrides: dict[str, list[dict[str, str]]] = {}
    for block in re.split(r'\n  (?="?[^"\s]+"?: \[)', body)[1:]:
        key = block.split(":", 1)[0].strip().strip('"')
        overrides[key] = [{"match": json.loads(m), "icon": json.loads(i)}
                          for m, i in _OVERRIDE.findall(block)]
    return by_id, overrides


@pytest.mark.parametrize(("provider", "prefix"), [("gcp", "GCP"), ("azure", "AZURE")])
def test_gcp_and_azure_backend_maps_match_the_canvas(provider, prefix):
    backend = json.loads(
        (ROOT / "backend" / "src" / "pricing_data" / f"{provider}_service_icons.json").read_text()
    )
    by_id, overrides = _ts_provider_maps(provider, prefix)
    assert by_id, "parsed no services from the TypeScript map"
    assert backend["by_id"] == by_id
    assert backend["overrides"] == overrides


@pytest.mark.parametrize("provider", ["gcp", "azure"])
def test_every_overridden_service_also_has_its_own_icon(provider):
    """A service has an icon on the canvas exactly when it's in `by_id` (research R7)."""
    backend = json.loads(
        (ROOT / "backend" / "src" / "pricing_data" / f"{provider}_service_icons.json").read_text()
    )
    assert set(backend["overrides"]) <= set(backend["by_id"])
