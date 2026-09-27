"""The icon-map generator's structured records (017-structured-json-logging, FR-009;
contracts/log-format.md §4): `build_mapping` yields one row per service and family override,
the printed report is unchanged, and `--log-file` writes those rows as JSON records."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

from src.config import settings
from src.logging_config import configure_logging

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "generate_aws_service_icon_map.py"

NAMES = {
    "AmazonZZWidget": "Amazon ZZ Widget",  # exact match
    "ZZGadgetz": "Amazon ZZ Gadgetz",  # fuzzy match
    "ZZOverride": "Override Svc",  # in OVERRIDES
    "AWSDataTransfer": "AWS Data Transfer",  # the data-transfer service
    "ZZQqqq": "Qqqq Xyzzy",  # no icon: falls back
}
FAMILIES = {("AmazonZZWidget", "Fam A")}
STEMS = ["Amazon-ZZ-Widget", "Amazon-ZZ-Gadgets", "Amazon-ZZ-Override", "Amazon-ZZ-FamA",
         "Amazon-ZZ-FamB"]  # fmt: skip

# Captured from build_mapping before 017 changed it: the printed report must stay identical.
EXPECTED_REPORT = [
    "WARNING: family override (AmazonZZWidget, Fam B) not in pricing data",
    "\n## matched (1)",
    "  AmazonZZWidget                           Amazon-ZZ-Widget",
    "\n## fuzzy (1)",
    "  ZZGadgetz                                Amazon-ZZ-Gadgets",
    "\n## override (2)",
    "  AWSDataTransfer                          (data-transfer icon)",
    "  ZZOverride                               Amazon-ZZ-Override  (auto: Amazon-ZZ-Override)",
    "\n## fallback (1)",
    "  ZZQqqq                                   Qqqq Xyzzy",
    "\nnon-fallback: 4/5 = 80.0%",
]


@pytest.fixture
def gen(monkeypatch):
    spec = importlib.util.spec_from_file_location("generate_aws_service_icon_map", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "OVERRIDES", {"ZZOverride": "Amazon-ZZ-Override"})
    monkeypatch.setattr(
        module,
        "FAMILY_OVERRIDES",
        {"AmazonZZWidget": {"Fam A": "Amazon-ZZ-FamA", "Fam B": "Amazon-ZZ-FamB"}},
    )
    yield module
    configure_logging(settings.log_level, settings.log_format)


@pytest.fixture
def icons(tmp_path) -> dict[str, Path]:
    icon_dir = tmp_path / "icons" / "Architecture-Service-Icons_01" / "Cat" / "48"
    icon_dir.mkdir(parents=True)
    paths = {stem: icon_dir / f"Arch_{stem}_48.svg" for stem in STEMS}
    for path in paths.values():
        path.write_text("<svg/>", encoding="utf-8")
    return paths


def test_build_mapping_returns_one_row_per_service_and_family_override(gen, icons):
    *_, report, rows = gen.build_mapping(NAMES, FAMILIES, icons)

    by_code = {r["service_code"]: r for r in rows if r["match_type"] != "family_override"}
    assert {code: r["match_type"] for code, r in by_code.items()} == {
        "AmazonZZWidget": "matched",
        "ZZGadgetz": "fuzzy",
        "ZZOverride": "override",
        "AWSDataTransfer": "data_transfer",
        "ZZQqqq": "fallback",
    }
    assert by_code["AmazonZZWidget"]["icon_file"] == "Amazon-ZZ-Widget.svg"
    assert by_code["ZZGadgetz"]["icon_file"] == "Amazon-ZZ-Gadgets.svg"
    assert by_code["ZZOverride"]["icon_file"] == "Amazon-ZZ-Override.svg"
    assert by_code["AWSDataTransfer"]["icon_file"] is None
    assert by_code["ZZQqqq"]["icon_file"] is None
    assert all(r["service_name"] == NAMES[code] for code, r in by_code.items())

    family_rows = [r for r in rows if r["match_type"] == "family_override"]
    assert family_rows == [
        {"service_code": "AmazonZZWidget", "product_family": "Fam A",
         "icon_file": "Amazon-ZZ-FamA.svg", "match_type": "family_override"},
        {"service_code": "AmazonZZWidget", "product_family": "Fam B",
         "icon_file": "Amazon-ZZ-FamB.svg", "match_type": "family_override"},
    ]  # fmt: skip


def test_printed_report_is_unchanged(gen, icons):
    *_, report, _rows = gen.build_mapping(NAMES, FAMILIES, icons)
    assert report == EXPECTED_REPORT


def test_log_mapping_writes_one_record_per_row_and_copied_icon(gen, icons):
    *_, rows = gen.build_mapping(NAMES, FAMILIES, icons)
    stream = io.StringIO()
    configure_logging(level="INFO", fmt="json", stream=stream)

    gen.log_mapping(rows, ["Amazon-ZZ-Widget.svg", "AWS-Cloud-logo.svg"])

    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert all({"timestamp", "level", "message"} <= r.keys() for r in records)
    services = [r for r in records if r["message"] == "service icon matched"]
    assert [(r["service_code"], r["service_name"], r["icon_file"], r["match_type"])
            for r in services] == [
        (r["service_code"], r["service_name"], r["icon_file"], r["match_type"])
        for r in rows if r["match_type"] != "family_override"
    ]  # fmt: skip
    families = [r for r in records if r["message"] == "family icon override"]
    assert [(r["product_family"], r["match_type"]) for r in families] == [
        ("Fam A", "family_override"),
        ("Fam B", "family_override"),
    ]
    copied = [r["icon_file"] for r in records if r["message"] == "icon copied"]
    assert copied == ["Amazon-ZZ-Widget.svg", "AWS-Cloud-logo.svg"]


@pytest.fixture
def run_main(gen, icons, tmp_path, monkeypatch, capsys):
    """Run the script's `main()` against the fake icons, writing its outputs under tmp_path."""
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.setattr(gen, "BACKEND", tmp_path / "backend")
    monkeypatch.setattr(gen, "OUT_TS", out / "icons.generated.ts")
    monkeypatch.setattr(gen, "OUT_JSON", out / "icons.json")
    monkeypatch.setattr(gen, "OUT_ICONS", out / "svg")
    monkeypatch.setattr(gen, "_service_icons", lambda _root: icons)
    monkeypatch.setattr(gen, "_special_icons", lambda _root: {})
    monkeypatch.setattr(gen, "_latest_snapshot", lambda _dir: "2026-09-26")
    monkeypatch.setattr(gen, "_pricing_services", lambda _dir, _snap: (NAMES, FAMILIES))

    def run(*extra: str) -> str:
        argv = ["generate", "--icons", str(tmp_path / "icons"), "--parquet", str(tmp_path), *extra]
        monkeypatch.setattr(sys, "argv", argv)
        gen.main()
        return capsys.readouterr().out

    return run


def test_without_log_file_only_the_report_is_written(run_main, tmp_path):
    printed = run_main()

    assert "\n".join(EXPECTED_REPORT) in printed
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == [
        "icons.generated.ts",
        "icons.json",
        "svg",
    ]
    assert not list(tmp_path.glob("*.jsonl"))


def test_log_file_holds_one_json_record_per_row_and_icon(run_main, tmp_path):
    log_file = tmp_path / "report.jsonl"
    printed = run_main("--log-file", str(log_file))

    assert "\n".join(EXPECTED_REPORT) in printed
    records = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
    messages = [r["message"] for r in records]
    assert messages.count("service icon matched") == len(NAMES)
    assert messages.count("family icon override") == 2
    copied = sorted(r["icon_file"] for r in records if r["message"] == "icon copied")
    assert copied == sorted(p.name for p in (tmp_path / "out" / "svg").iterdir())
