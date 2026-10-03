"""`python -m src.ops <command>` — the in-image operations CLI (018-app-cloud-deployment;
contracts/ops-cli.md).

Every command logs JSON (feature 017) and prints exactly one JSON result object as the **last
line of stdout**, which `deploy/app` parses. Exit codes: 0 success, 1 unexpected, 3 a
precondition isn't met, 4 verification failed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from src.config import settings
from src.logging_config import configure_logging, get_logger
from src.ops.db import OpsError

logger = get_logger("cloud_pricing.ops")

DB_INIT_RESULT = Path("/run/app/db-init.json")


def _backup_store():
    from src.ops.backup_store import open_backup_store

    if not settings.backup_uri:
        raise OpsError(3, "BACKUP_URI is not set")
    return open_backup_store(settings.backup_uri)


def _db_init(args: argparse.Namespace) -> dict:
    from src.ops.backup_store import open_backup_store
    from src.ops.db_init import run_db_init

    store = open_backup_store(settings.backup_uri) if settings.backup_uri else None
    return run_db_init(
        database_url=settings.database_url,
        store=store,
        backup_id=args.backup,
        owner_password_parameter=settings.owner_password_parameter,
        allow_default_admin_password=args.allow_default_admin_password,
        result_path=args.result_file,
    )


def _backup(args: argparse.Namespace) -> dict:
    from src.ops.backup import run_backup

    return run_backup(
        args.kind,
        database_url=settings.database_url,
        store=_backup_store(),
        keep=settings.backup_keep,
        release=settings.app_release,
        environment=settings.app_environment,
    )


def _backups_list(_args: argparse.Namespace) -> dict:
    return {
        "backups": [
            {k: m.get(k) for k in ("id", "kind", "created_at", "verified", "app_release")}
            for m in _backup_store().list_backups()
        ]
    }


def _notify(args: argparse.Namespace) -> dict:
    from src.ops import alerts

    return {"published": alerts.notify(args.message, subject=args.subject)}


def _fetch_tls(args: argparse.Namespace) -> dict:
    from src.ops.tls import fetch_tls

    return fetch_tls(args.out)


def _health(args: argparse.Namespace) -> dict:
    from src.ops.health import run_health

    return run_health(wait_seconds=args.wait, db_init_result=args.result_file)


def _uptime_alert(_args: argparse.Namespace) -> dict:
    from src.ops.uptime import run_uptime_alert

    return run_uptime_alert()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m src.ops", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    db_init = commands.add_parser("db-init", help="restore or initialize, then migrate")
    db_init.add_argument("--backup", help="restore this backup id instead of the newest")
    db_init.add_argument("--allow-default-admin-password", action="store_true",
                         help="local only: keep the default Admin password on a fresh database")
    db_init.add_argument("--result-file", type=Path, default=DB_INIT_RESULT)
    db_init.set_defaults(func=_db_init)

    backup = commands.add_parser("backup", help="take and verify a backup")
    backup.add_argument("--kind", required=True,
                        choices=["scheduled", "teardown", "redeploy", "manual"])
    backup.set_defaults(func=_backup)

    backups = commands.add_parser("backups", help="backup listing")
    backups_commands = backups.add_subparsers(dest="backups_command", required=True)
    backups_commands.add_parser("list", help="newest first").set_defaults(func=_backups_list)

    notify = commands.add_parser("notify", help="publish to the alert topic")
    notify.add_argument("--message", required=True)
    notify.add_argument("--subject")
    notify.set_defaults(func=_notify)

    fetch_tls = commands.add_parser("fetch-tls", help="write the TLS root for Caddy")
    fetch_tls.add_argument("--out", type=Path, required=True)
    fetch_tls.set_defaults(func=_fetch_tls)

    health = commands.add_parser("health", help="report whether the app is healthy")
    health.add_argument("--wait", type=int, default=0, metavar="SECONDS")
    health.add_argument("--result-file", type=Path, default=DB_INIT_RESULT)
    health.set_defaults(func=_health)

    commands.add_parser("uptime-alert", help="alert on a forgotten instance").set_defaults(
        func=_uptime_alert
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging(settings.log_level, settings.log_format)
    args = build_parser().parse_args(argv)
    func: Callable[[argparse.Namespace], dict] = args.func
    try:
        result = func(args)
        code = 0
    except OpsError as exc:
        result, code = {"error": str(exc), "exit_code": exc.code}, exc.code
    except Exception as exc:  # noqa: BLE001 — the contract's "unexpected" exit
        logger.exception("ops command failed", command=args.command)
        result, code = {"error": str(exc), "exit_code": 1}, 1
    sys.stdout.flush()
    print(json.dumps(result, default=str), flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
