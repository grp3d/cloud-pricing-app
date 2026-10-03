"""Storage adapters for the pricing data source (018-app-cloud-deployment, FR-001–FR-003,
FR-008, FR-009; data-model.md §1, research.md R7).

Both sources use the pipeline's storage layout and the same operations. A missing key — which S3
reports as `AccessDenied` under the pipeline's read-only policy — is `None`, never an error.
"""

from __future__ import annotations

import hashlib

import pytest
from botocore.exceptions import ClientError

from src.pricing_data.storage import (
    LocalStore,
    ObjectMissingError,
    S3Store,
    VerificationError,
)
from tests.helpers.fake_s3 import FakeS3Client, _error

BUCKET = "cloud-pricing-data-test"


# --- LocalStore -------------------------------------------------------------------------------


def test_local_get_returns_bytes_or_none(tmp_path):
    (tmp_path / "aws" / "manifests").mkdir(parents=True)
    (tmp_path / "aws" / "manifests" / "latest.json").write_bytes(b"{}")
    store = LocalStore(tmp_path)
    assert store.get("aws/manifests/latest.json") == b"{}"
    assert store.get("aws/manifests/missing.json") is None
    assert store.exists("aws/manifests/latest.json")
    assert not store.exists("aws/manifests/missing.json")


def test_local_list_manifest_dates_sorted_and_filtered(tmp_path):
    manifests = tmp_path / "aws" / "manifests"
    for name in ("2026-10-05", "2026-09-30", "not-a-date", "2026-10-01"):
        (manifests / name).mkdir(parents=True)
    (manifests / "latest.json").write_text("{}")
    assert LocalStore(tmp_path).list_manifest_dates("aws") == [
        "2026-09-30",
        "2026-10-01",
        "2026-10-05",
    ]


def test_local_list_manifest_dates_without_folder_is_empty(tmp_path):
    assert LocalStore(tmp_path).list_manifest_dates("aws") == []


def test_local_file_path_stays_inside_root(tmp_path):
    store = LocalStore(tmp_path)
    assert store.file_path("aws/parquet/x.parquet") == tmp_path / "aws/parquet/x.parquet"
    for bad in ("../outside.parquet", "aws/../../outside", "/etc/passwd"):
        with pytest.raises(ValueError, match="outside"):
            store.file_path(bad)


# --- S3Store ----------------------------------------------------------------------------------


def _s3(client: FakeS3Client, prefix: str = "") -> S3Store:
    return S3Store(BUCKET, prefix, client=client)


def test_s3_get_returns_bytes():
    client = FakeS3Client()
    client.put(BUCKET, "aws/manifests/latest.json", b'{"a": 1}')
    assert _s3(client).get("aws/manifests/latest.json") == b'{"a": 1}'


def test_s3_prefix_is_prepended():
    client = FakeS3Client()
    client.put(BUCKET, "data/aws/manifests/latest.json", b"{}")
    store = _s3(client, "data")
    assert store.get("aws/manifests/latest.json") == b"{}"
    assert store.exists("aws/manifests/latest.json")


@pytest.mark.parametrize("deny_missing", [False, True])
def test_s3_missing_key_is_none_including_access_denied(deny_missing):
    store = _s3(FakeS3Client(deny_missing=deny_missing))
    assert store.get("aws/manifests/latest.json") is None
    assert store.exists("aws/manifests/latest.json") is False


def test_s3_404_client_error_is_none():
    client = FakeS3Client()

    def fail(operation, key):
        raise _error("404", 404, operation)

    client.before_call = fail
    assert _s3(client).get("aws/manifests/latest.json") is None


def test_s3_other_errors_are_raised():
    client = FakeS3Client()

    def fail(operation, key):
        raise _error("SlowDown", 503, operation)

    client.before_call = fail
    with pytest.raises(ClientError):
        _s3(client).get("aws/manifests/latest.json")


def test_s3_list_manifest_dates():
    client = FakeS3Client()
    for key in (
        "aws/manifests/latest.json",
        "aws/manifests/2026-10-05/manifest.json",
        "aws/manifests/2026-10-05/revisions/0001.json",
        "aws/manifests/2026-09-30/manifest.json",
        "aws/manifests/junk/manifest.json",
        "aws/parquet/price_fact/x.parquet",
    ):
        client.put(BUCKET, key, b"{}")
    assert _s3(client).list_manifest_dates("aws") == ["2026-09-30", "2026-10-05"]


def test_s3_download_verifies_size_and_sha(tmp_path):
    body = b"parquet bytes" * 1000
    client = FakeS3Client()
    client.put(BUCKET, "aws/parquet/f.parquet", body)
    dest = tmp_path / "sub" / "f.parquet"
    _s3(client).download(
        "aws/parquet/f.parquet", dest, len(body), hashlib.sha256(body).hexdigest()
    )
    assert dest.read_bytes() == body


@pytest.mark.parametrize("which", ["size", "sha"])
def test_s3_download_fails_on_mismatch(tmp_path, which):
    body = b"parquet bytes"
    client = FakeS3Client()
    client.put(BUCKET, "aws/parquet/f.parquet", body)
    size = len(body) + (1 if which == "size" else 0)
    sha = hashlib.sha256(body).hexdigest() if which == "size" else "0" * 64
    with pytest.raises(VerificationError, match="f.parquet"):
        _s3(client).download("aws/parquet/f.parquet", tmp_path / "f.parquet", size, sha)


def test_s3_download_of_missing_object_raises_object_missing(tmp_path):
    with pytest.raises(ObjectMissingError):
        _s3(FakeS3Client(deny_missing=True)).download(
            "aws/parquet/gone.parquet", tmp_path / "gone.parquet", 1, "0" * 64
        )
