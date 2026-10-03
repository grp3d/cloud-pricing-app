"""No request fails or mixes data while the active snapshot switches (018-app-cloud-deployment,
SC-007, Story 5 AS1). The switch replaces one immutable value, and every lookup reads the
snapshot it took at its start.
"""

from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path

from src.pricing_data import active_snapshot
from src.pricing_data.pricing import lookup_price

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "pricing_parquet"
KNOWN_SKU = "NN4EGUUQRWVYP98C"


def test_prices_stay_consistent_through_twenty_switches(tmp_path, use_pricing_root):
    root = tmp_path / "pipeline"
    shutil.copytree(FIXTURE, root)
    use_pricing_root(root)
    expected = lookup_price(sku=KNOWN_SKU, pricing_term="on_demand",
                            purchase_option="not_applicable", region="us-east-1")
    assert expected is not None

    manifest_path = root / "aws/manifests/2026-09-24/manifest.json"
    latest_path = root / "aws/manifests/latest.json"
    results: list[float | None] = []
    errors: list[BaseException] = []
    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            try:
                results.append(lookup_price(sku=KNOWN_SKU, pricing_term="on_demand",
                                            purchase_option="not_applicable", region="us-east-1"))
            except BaseException as exc:  # noqa: BLE001 — collected for the assertion
                errors.append(exc)

    thread = threading.Thread(target=reader)
    thread.start()
    try:
        for revision in range(2, 22):
            for path in (manifest_path, latest_path):
                document = json.loads(path.read_text())
                document["revision"] = revision
                path.write_text(json.dumps(document))
            result = active_snapshot.run_check()
            assert result.switched, f"revision {revision} did not switch"
    finally:
        stop.set()
        thread.join()

    assert active_snapshot.get_active_snapshot().revision == 21
    assert errors == []
    assert results and all(r == expected for r in results)
