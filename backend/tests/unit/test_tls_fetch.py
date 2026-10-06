"""`ops fetch-tls` (018-app-cloud-deployment, FR-037; research.md R6): write the environment's
TLS root for Caddy, from SSM in the cloud or from `TLS_ROOT_DIR` on a laptop. The key is never
logged or returned."""

from __future__ import annotations

import hashlib
import shutil
import ssl
import stat
import subprocess

import pytest

from src.ops import params, tls


@pytest.fixture
def root_pair(tmp_path):
    if shutil.which("openssl") is None:
        pytest.skip("openssl not on PATH")
    key, cert = tmp_path / "src" / "root.key", tmp_path / "src" / "root.crt"
    key.parent.mkdir()
    subprocess.run(["openssl", "ecparam", "-name", "prime256v1", "-genkey", "-noout",
                    "-out", str(key)], check=True, capture_output=True)
    subprocess.run(["openssl", "req", "-x509", "-new", "-key", str(key), "-sha256",
                    "-days", "30", "-subj", "/CN=test root", "-out", str(cert)],
                   check=True, capture_output=True)
    return key.read_text(), cert.read_text(), tmp_path / "src"


def _expected_fingerprint(cert_pem: str) -> str:
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert_pem)).hexdigest()


def test_fetch_from_ssm_writes_read_only_files(monkeypatch, tmp_path, root_pair):
    key_pem, cert_pem, _ = root_pair
    values = {
        "/cloud-pricing-app/prod/tls/root-key": key_pem,
        "/cloud-pricing-app/prod/tls/root-cert": cert_pem,
    }
    monkeypatch.setattr(params, "get_parameter", lambda name: values[name])
    monkeypatch.setattr(tls.settings, "tls_root_dir", None)
    monkeypatch.setattr(tls.settings, "app_environment", "prod")
    out = tmp_path / "tls"

    result = tls.fetch_tls(out)

    assert (out / "root.key").read_text() == key_pem
    assert (out / "root.crt").read_text() == cert_pem
    for name in ("root.key", "root.crt"):
        assert stat.S_IMODE((out / name).stat().st_mode) == 0o400
    assert result["root_fingerprint_sha256"] == _expected_fingerprint(cert_pem)
    assert result["not_after"].endswith("GMT")
    assert key_pem not in str(result)


def test_fetch_from_local_directory(monkeypatch, tmp_path, root_pair):
    key_pem, cert_pem, src = root_pair
    monkeypatch.setattr(tls.settings, "tls_root_dir", str(src))
    monkeypatch.setattr(params, "get_parameter", lambda name: pytest.fail("no SSM locally"))
    result = tls.fetch_tls(tmp_path / "tls")
    assert (tmp_path / "tls" / "root.key").read_text() == key_pem
    assert result["root_fingerprint_sha256"] == _expected_fingerprint(cert_pem)


def test_refetch_replaces_read_only_files(monkeypatch, tmp_path, root_pair):
    _, _, src = root_pair
    monkeypatch.setattr(tls.settings, "tls_root_dir", str(src))
    tls.fetch_tls(tmp_path / "tls")
    tls.fetch_tls(tmp_path / "tls")  # e.g. tls-init re-run on restart
    assert (tmp_path / "tls" / "root.crt").exists()


def test_missing_root_is_a_precondition_error(monkeypatch, tmp_path):
    from src.ops.db import OpsError

    monkeypatch.setattr(tls.settings, "tls_root_dir", str(tmp_path / "empty"))
    with pytest.raises(OpsError) as excinfo:
        tls.fetch_tls(tmp_path / "tls")
    assert excinfo.value.code == 3
