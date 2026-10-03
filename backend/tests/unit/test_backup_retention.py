"""Backup retention (018-app-cloud-deployment, FR-026; data-model.md §6).

`select_deletions` is pure: it decides, it never deletes. It keeps the newest `keep` verified
backups, never deletes the newest verified one, and removes incomplete backups only once they
are more than 24 hours old (one may still be uploading).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.ops.backup import BackupRecord, select_deletions

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def _record(hours_ago: float, *, verified: bool = True) -> BackupRecord:
    created = NOW - timedelta(hours=hours_ago)
    return BackupRecord(
        id=f"{created:%Y%m%dT%H%M%SZ}-scheduled-v1.0.0", created_at=created, verified=verified
    )


def test_keeps_newest_verified_up_to_keep():
    backups = [_record(h) for h in (1, 7, 13, 19, 25)]
    assert select_deletions(backups, keep=3, now=NOW) == [backups[3].id, backups[4].id]


def test_nothing_deleted_within_keep():
    backups = [_record(h) for h in (1, 7)]
    assert select_deletions(backups, keep=14, now=NOW) == []


def test_never_deletes_the_newest_verified_even_with_a_newer_unverified_one():
    newest_verified = _record(5)
    unverified_newer = _record(1, verified=False)
    older = _record(30)
    deletions = select_deletions([unverified_newer, newest_verified, older], keep=1, now=NOW)
    assert newest_verified.id not in deletions
    assert unverified_newer.id not in deletions  # incomplete but younger than 24 h
    assert deletions == [older.id]


def test_incomplete_backups_deleted_only_after_24_hours():
    young = _record(23, verified=False)
    old = _record(25, verified=False)
    verified = _record(2)
    assert select_deletions([verified, young, old], keep=5, now=NOW) == [old.id]


def test_only_backup_is_never_deleted():
    only = _record(500)
    assert select_deletions([only], keep=1, now=NOW) == []


def test_input_order_does_not_matter():
    backups = [_record(h) for h in (25, 1, 13, 7, 19)]
    by_age = sorted(backups, key=lambda b: b.created_at, reverse=True)
    assert select_deletions(backups, keep=2, now=NOW) == [b.id for b in by_age[2:]]
