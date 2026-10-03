"""The pipeline's `latest.json` pointer and snapshot manifests, and the checks that decide whether
a manifest is usable (018-app-cloud-deployment, FR-004, FR-006, FR-007; data-model.md §2–3).

The models mirror the pipeline's published contract (`tests/fixtures/contracts/`, vendored),
keeping the fields the app uses and ignoring unknown ones, which a 1.x minor version may add.
`validate_manifest` is pure: it reads nothing and fetches nothing, so a bad manifest is refused
before any data file is touched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from src.pricing_data.snapshot import TABLES

SUPPORTED_MANIFEST_MAJOR = 1
SUPPORTED_SCHEMA_VERSIONS: dict[str, set[int]] = {table: {1} for table in TABLES}

_RUN_ID = r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{6}"


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class LatestPointer(_Model):
    manifest_version: str
    provider: str
    snapshot_date: str
    revision: int
    run_id: str
    manifest_path: str
    updated_at: str


class FailedRegion(_Model):
    region: str
    reason: str
    attempts: int


class Regions(_Model):
    requested: list[str]
    succeeded: list[str]
    failed: list[FailedRegion]


class PipelineVersion(_Model):
    git_sha: str
    image_tag: str


class Run(_Model):
    trigger: str
    mode: str
    host: str
    started_at: str
    ended_at: str
    pipeline_version: PipelineVersion


class DataFile(_Model):
    path: str
    bytes: int
    sha256: str
    row_count: int


class RegionFiles(_Model):
    written_by_run: str
    row_count: int
    files: list[DataFile]


class Table(_Model):
    schema_version: int
    row_count: int
    regions: dict[str, RegionFiles]


class Manifest(_Model):
    manifest_version: str
    provider: str
    snapshot_date: str
    run_id: str
    revision: int
    previous_revision: int | None = None
    created_at: str
    origin: str
    status: Literal["succeeded", "partial", "failed", "purged"]
    regions: Regions
    run: Run
    tables: dict[str, Table]
    purged: dict | None = None

    def files(self) -> list[DataFile]:
        return [
            f for table in self.tables.values() for region in table.regions.values()
            for f in region.files
        ]

    @property
    def total_bytes(self) -> int:
        return sum(f.bytes for f in self.files())


@dataclass(frozen=True)
class RejectedManifest:
    """A manifest the app refused, and why (shown in the Admin tab)."""

    snapshot_date: str | None
    revision: int | None
    reason: str


def _major(version: str) -> int | None:
    match = re.match(r"^(\d+)\.\d+$", version)
    return int(match.group(1)) if match else None


def manifest_key(provider: str, snapshot_date: str) -> str:
    return f"{provider}/manifests/{snapshot_date}/manifest.json"


def parse_manifest(raw: bytes, *, snapshot_date: str | None) -> Manifest | RejectedManifest:
    try:
        return Manifest.model_validate_json(raw)
    except ValidationError as exc:
        reason = f"manifest is not readable: {exc.errors()[0]['msg']}"
        return RejectedManifest(snapshot_date, None, reason)


def parse_pointer(raw: bytes) -> LatestPointer | RejectedManifest:
    try:
        pointer = LatestPointer.model_validate_json(raw)
    except ValidationError as exc:
        reason = f"latest.json is not readable: {exc.errors()[0]['msg']}"
        return RejectedManifest(None, None, reason)
    if _major(pointer.manifest_version) != SUPPORTED_MANIFEST_MAJOR:
        return RejectedManifest(
            pointer.snapshot_date, pointer.revision,
            f"latest.json contract version {pointer.manifest_version} is not supported",
        )
    if pointer.manifest_path != manifest_key(pointer.provider, pointer.snapshot_date):
        return RejectedManifest(
            pointer.snapshot_date, pointer.revision,
            f"latest.json names an unexpected manifest path {pointer.manifest_path!r}",
        )
    return pointer


def _bad_path(path: str, provider: str, table: str, snapshot_date: str, region: str) -> bool:
    if path.startswith("/") or "\\" in path or ".." in path.split("/"):
        return True
    pattern = (
        rf"^{re.escape(provider)}/parquet/{re.escape(table)}/"
        rf"snapshot_date={re.escape(snapshot_date)}/region={re.escape(region)}/"
        rf"part-{_RUN_ID}(-[0-9]+)?\.parquet$"
    )
    return re.match(pattern, path) is None


def validate_manifest(
    manifest: Manifest, provider: str, *, pointer: LatestPointer | None = None
) -> Manifest | RejectedManifest:
    """The manifest itself if it is usable, otherwise a `RejectedManifest` with the reason."""

    def reject(reason: str) -> RejectedManifest:
        return RejectedManifest(manifest.snapshot_date, manifest.revision, reason)

    if _major(manifest.manifest_version) != SUPPORTED_MANIFEST_MAJOR:
        return reject(f"contract version {manifest.manifest_version} is not supported")
    if manifest.provider != provider:
        return reject(f"manifest is for provider {manifest.provider}, not {provider}")
    if manifest.status != "succeeded" or manifest.purged is not None:
        return reject(f"status is {manifest.status}")
    for table in TABLES:
        if table not in manifest.tables:
            return reject(f"table {table} is missing")
        version = manifest.tables[table].schema_version
        if version not in SUPPORTED_SCHEMA_VERSIONS[table]:
            return reject(f"table {table} schema version {version} is not supported")
    for table, entry in manifest.tables.items():
        for region, files in entry.regions.items():
            for data_file in files.files:
                if _bad_path(data_file.path, provider, table, manifest.snapshot_date, region):
                    return reject(
                        f"file path {data_file.path!r} does not match the contract layout"
                    )
    if pointer is not None:
        if manifest.snapshot_date != pointer.snapshot_date:
            return reject(
                f"date {manifest.snapshot_date} differs from latest.json's {pointer.snapshot_date}"
            )
        if manifest.revision < pointer.revision:
            return reject(
                f"revision {manifest.revision} is lower than latest.json's {pointer.revision}"
            )
    return manifest
