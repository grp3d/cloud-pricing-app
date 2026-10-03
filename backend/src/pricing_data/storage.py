"""Read-only access to the pipeline's storage root, local or S3 (018-app-cloud-deployment,
FR-001–FR-003, FR-008, FR-009; data-model.md §1, research.md R7).

Both stores take keys relative to the root (`aws/manifests/latest.json`, a manifest's file
paths) and offer the same reads, so the snapshot logic never cares which one it has. A missing
key is `None` — including S3's `AccessDenied`, which the pipeline's read-only policy returns for
a key that doesn't exist (storage-layout.md, consumer rule 8).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Protocol

from src.config import Settings

_DATE_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MISSING_CODES = {"NoSuchKey", "AccessDenied", "404", "NotFound"}
_CHUNK = 1024 * 1024


class ObjectMissingError(FileNotFoundError):
    """A key a manifest lists is gone (e.g. deleted after the pipeline's grace period)."""


class VerificationError(RuntimeError):
    """A downloaded file's size or sha256 doesn't match its manifest entry."""


class Store(Protocol):
    def get(self, key: str) -> bytes | None: ...
    def exists(self, key: str) -> bool: ...
    def list_manifest_dates(self, provider: str) -> list[str]: ...


def _is_missing(exc: Exception) -> bool:
    from botocore.exceptions import ClientError

    if not isinstance(exc, ClientError):
        return False
    error = exc.response.get("Error", {})
    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return error.get("Code") in _MISSING_CODES or status == 404


class LocalStore:
    """A local directory in the pipeline's layout. Files are read in place (FR-002)."""

    kind = "local"

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def __repr__(self) -> str:
        return f"LocalStore({self.root})"

    @property
    def location(self) -> str:
        return str(self.root)

    def file_path(self, key: str) -> Path:
        """The absolute path of `key`, refusing anything that would leave the root."""
        root = self.root.resolve()
        path = (root / key).resolve()
        if key.startswith("/") or not path.is_relative_to(root):
            raise ValueError(f"{key!r} is outside the data root")
        return path

    def get(self, key: str) -> bytes | None:
        try:
            return self.file_path(key).read_bytes()
        except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
            return None

    def exists(self, key: str) -> bool:
        return self.file_path(key).is_file()

    def list_manifest_dates(self, provider: str) -> list[str]:
        manifests = self.root / provider / "manifests"
        if not manifests.is_dir():
            return []
        return sorted(e.name for e in manifests.iterdir() if e.is_dir() and _DATE_DIR.match(e.name))


class S3Store:
    """The pipeline's bucket, optionally under a prefix. Credentials come from the standard
    chain (the instance role in the cloud, a profile on a laptop); no setting names them."""

    kind = "s3"

    def __init__(self, bucket: str, prefix: str = "", client: object | None = None) -> None:
        self.bucket = bucket
        self.prefix = f"{prefix.strip('/')}/" if prefix.strip("/") else ""
        self._client = client

    def __repr__(self) -> str:
        return f"S3Store(s3://{self.bucket}/{self.prefix})"

    @property
    def location(self) -> str:
        return f"s3://{self.bucket}/{self.prefix}".rstrip("/")

    @property
    def client(self):
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client("s3", config=Config(retries={"mode": "standard"}))
        return self._client

    def _key(self, key: str) -> str:
        return f"{self.prefix}{key}"

    def get(self, key: str) -> bytes | None:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self._key(key))
        except Exception as exc:
            if _is_missing(exc):
                return None
            raise
        return response["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(key))
        except Exception as exc:
            if _is_missing(exc):
                return False
            raise
        return True

    def list_manifest_dates(self, provider: str) -> list[str]:
        prefix = self._key(f"{provider}/manifests/")
        dates: set[str] = set()
        token: str | None = None
        while True:
            kwargs = {"Bucket": self.bucket, "Prefix": prefix, "Delimiter": "/"}
            if token:
                kwargs["ContinuationToken"] = token
            response = self.client.list_objects_v2(**kwargs)
            for common in response.get("CommonPrefixes", []):
                name = common["Prefix"][len(prefix):].rstrip("/")
                if _DATE_DIR.match(name):
                    dates.add(name)
            if not response.get("IsTruncated"):
                return sorted(dates)
            token = response.get("NextContinuationToken")

    def download(self, key: str, dest: Path, expected_bytes: int, expected_sha256: str) -> None:
        """Stream `key` to `dest`, hashing as it goes. Raises `ObjectMissingError` if the key is
        gone and `VerificationError` (leaving no file) on a size or checksum mismatch."""
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self._key(key))
        except Exception as exc:
            if _is_missing(exc):
                raise ObjectMissingError(key) from exc
            raise
        dest.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        body = response["Body"]
        with dest.open("wb") as out:
            while chunk := body.read(_CHUNK):
                digest.update(chunk)
                size += len(chunk)
                out.write(chunk)
        if size != expected_bytes or digest.hexdigest() != expected_sha256:
            dest.unlink(missing_ok=True)
            raise VerificationError(
                f"{key}: expected {expected_bytes} bytes sha256 {expected_sha256}, "
                f"got {size} bytes sha256 {digest.hexdigest()}"
            )


def open_store(settings: Settings) -> LocalStore | S3Store:
    """The store for `PRICING_DATA_URI` (raises `ConfigurationError` when it's unset)."""
    source = settings.pricing_data_source
    if source.kind == "local":
        return LocalStore(source.root)
    bucket, _, prefix = source.root.partition("/")
    return S3Store(bucket, prefix)
