"""Where database backups live: a `file://` directory or an `s3://` prefix
(018-app-cloud-deployment, FR-025, FR-026; data-model.md §6).

A backup is two objects, `<id>.dump` (pg_dump custom format) and `<id>.json` (metadata), written
in that order so the metadata's presence marks the dump complete. Ids start with the UTC time,
so sorting ids sorts backups by age.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

_CHUNK = 1024 * 1024


def make_backup_id(kind: str, release: str, now: datetime) -> str:
    """`<yyyymmddThhmmssZ>-<kind>-<release>`, e.g. `20261005T140309Z-teardown-v1.4.0`."""
    return f"{now:%Y%m%dT%H%M%SZ}-{kind}-{release}"


class BackupStore:
    """Shared logic; subclasses provide raw object reads and writes by name."""

    location: str

    # --- raw object access (subclass) ---------------------------------------------------------

    def _write(self, name: str, data: bytes) -> None:
        raise NotImplementedError

    def _read(self, name: str) -> bytes | None:
        raise NotImplementedError

    def _names(self) -> list[str]:
        raise NotImplementedError

    def _remove(self, name: str) -> None:
        raise NotImplementedError

    def stat_dump(self, backup_id: str) -> tuple[int, str]:
        """(bytes, sha256 hex) of the stored `.dump`, re-read from the store itself."""
        raise NotImplementedError

    def fetch_dump(self, backup_id: str, dest: Path) -> None:
        raise NotImplementedError

    # --- backups ------------------------------------------------------------------------------

    def put_backup(self, backup_id: str, dump_path: Path, metadata: dict) -> None:
        """Upload the dump, then its metadata (which marks it complete)."""
        self._write(f"{backup_id}.dump", dump_path.read_bytes())
        self.write_metadata(backup_id, metadata)

    def write_metadata(self, backup_id: str, metadata: dict) -> None:
        self._write(f"{backup_id}.json", json.dumps(metadata, indent=2).encode())

    def get(self, backup_id: str) -> dict | None:
        raw = self._read(f"{backup_id}.json")
        return json.loads(raw) if raw is not None else None

    def list_backups(self) -> list[dict]:
        """Every complete backup's metadata, newest first."""
        ids = sorted((n[:-5] for n in self._names() if n.endswith(".json")), reverse=True)
        return [m for m in (self.get(i) for i in ids) if m is not None]

    def list_orphan_dumps(self) -> list[str]:
        """Ids of dumps with no metadata (an upload that never finished)."""
        names = set(self._names())
        return sorted(
            n[:-5] for n in names if n.endswith(".dump") and f"{n[:-5]}.json" not in names
        )

    def newest_verified(self) -> dict | None:
        return next((m for m in self.list_backups() if m.get("verified") is True), None)

    def delete(self, backup_id: str) -> None:
        """Remove the metadata first, so a half-deleted backup is never offered for restore."""
        self._remove(f"{backup_id}.json")
        self._remove(f"{backup_id}.dump")


class FileBackupStore(BackupStore):
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.location = f"file://{directory}"

    def _write(self, name: str, data: bytes) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        tmp = self.directory / f".{name}.partial"
        tmp.write_bytes(data)
        tmp.replace(self.directory / name)

    def _read(self, name: str) -> bytes | None:
        try:
            return (self.directory / name).read_bytes()
        except FileNotFoundError:
            return None

    def _names(self) -> list[str]:
        if not self.directory.is_dir():
            return []
        return [p.name for p in self.directory.iterdir() if p.is_file() and p.name[0] != "."]

    def _remove(self, name: str) -> None:
        (self.directory / name).unlink(missing_ok=True)

    def stat_dump(self, backup_id: str) -> tuple[int, str]:
        path = self.directory / f"{backup_id}.dump"
        digest = hashlib.sha256()
        with path.open("rb") as f:
            while chunk := f.read(_CHUNK):
                digest.update(chunk)
        return path.stat().st_size, digest.hexdigest()

    def fetch_dump(self, backup_id: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((self.directory / f"{backup_id}.dump").read_bytes())


class S3BackupStore(BackupStore):
    """Objects under `s3://<bucket>/<prefix>`. Uploads ask S3 to compute SHA-256, which
    `stat_dump` reads back, so verification uses S3's own view of the stored object."""

    def __init__(self, bucket: str, prefix: str, client: object | None = None) -> None:
        self.bucket = bucket
        self.prefix = f"{prefix.strip('/')}/" if prefix.strip("/") else ""
        self.location = f"s3://{bucket}/{self.prefix}"
        self._client = client

    @property
    def client(self):
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client("s3", config=Config(retries={"mode": "standard"}))
        return self._client

    def _write(self, name: str, data: bytes) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=f"{self.prefix}{name}",
            Body=data,
            ChecksumAlgorithm="SHA256",
        )

    def _read(self, name: str) -> bytes | None:
        from src.pricing_data.storage import _is_missing

        try:
            response = self.client.get_object(Bucket=self.bucket, Key=f"{self.prefix}{name}")
        except Exception as exc:
            if _is_missing(exc):
                return None
            raise
        return response["Body"].read()

    def _names(self) -> list[str]:
        names: list[str] = []
        token: str | None = None
        while True:
            kwargs = {"Bucket": self.bucket, "Prefix": self.prefix, "Delimiter": "/"}
            if token:
                kwargs["ContinuationToken"] = token
            response = self.client.list_objects_v2(**kwargs)
            names += [o["Key"][len(self.prefix):] for o in response.get("Contents", [])]
            if not response.get("IsTruncated"):
                return names
            token = response.get("NextContinuationToken")

    def _remove(self, name: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=f"{self.prefix}{name}")

    def stat_dump(self, backup_id: str) -> tuple[int, str]:
        head = self.client.head_object(
            Bucket=self.bucket, Key=f"{self.prefix}{backup_id}.dump", ChecksumMode="ENABLED"
        )
        sha_hex = base64.b64decode(head["ChecksumSHA256"]).hex()
        return head["ContentLength"], sha_hex

    def fetch_dump(self, backup_id: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as f:
            self.client.download_fileobj(self.bucket, f"{self.prefix}{backup_id}.dump", f)


def open_backup_store(uri: str, client: object | None = None) -> BackupStore:
    """The store for `BACKUP_URI` (`file:///abs/dir` or `s3://bucket/prefix/`)."""
    parsed = urlparse(uri)
    if parsed.scheme == "file" and parsed.path.startswith("/"):
        return FileBackupStore(Path(parsed.path))
    if parsed.scheme == "s3" and parsed.netloc:
        return S3BackupStore(parsed.netloc, parsed.path, client=client)
    raise ValueError(f"BACKUP_URI must be file:///dir or s3://bucket/prefix/, got {uri!r}")
