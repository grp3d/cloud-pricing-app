"""The ops CLI contract (018-app-cloud-deployment; contracts/ops-cli.md): one JSON result object
on the last stdout line, and the contract's exit codes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def _run(args: list[str], env_extra: dict[str, str]) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "BACKUP_URI"}
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "src.ops", *args],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_backups_list_prints_json_last_line(tmp_path):
    backups = tmp_path / "backups"
    backups.mkdir()
    (backups / "20261005T000000Z-manual-dev.dump").write_bytes(b"x")
    (backups / "20261005T000000Z-manual-dev.json").write_text(
        json.dumps({"id": "20261005T000000Z-manual-dev", "kind": "manual",
                    "created_at": "2026-10-05T00:00:00Z", "verified": True,
                    "app_release": "dev", "row_counts": {"users": 1}})
    )
    result = _run(["backups", "list"], {"BACKUP_URI": f"file://{backups}"})
    assert result.returncode == 0, result.stderr
    last = json.loads(result.stdout.strip().splitlines()[-1])
    assert last == {
        "backups": [
            {"id": "20261005T000000Z-manual-dev", "kind": "manual",
             "created_at": "2026-10-05T00:00:00Z", "verified": True, "app_release": "dev"}
        ]
    }


def test_missing_backup_uri_is_exit_3_with_json_error():
    result = _run(["backups", "list"], {})
    assert result.returncode == 3
    last = json.loads(result.stdout.strip().splitlines()[-1])
    assert last["exit_code"] == 3
    assert "BACKUP_URI" in last["error"]


def test_usage_error_is_exit_2():
    result = _run(["no-such-command"], {})
    assert result.returncode == 2
