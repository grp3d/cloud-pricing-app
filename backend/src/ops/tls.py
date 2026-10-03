"""`ops fetch-tls`: write the environment's TLS root for Caddy (018-app-cloud-deployment,
FR-037; research.md R6).

In the cloud the root's key (SecureString) and certificate live in SSM under
`/cloud-pricing-app/<env>/tls/`; `deploy/app up` creates them once. On a laptop, `TLS_ROOT_DIR`
names a directory holding `root.crt` and `root.key` (made by `deploy/app cert local --create`).
The key is written mode 0400 to an in-memory volume and never logged or returned.
"""

from __future__ import annotations

import hashlib
import ssl
import tempfile
from pathlib import Path

from src.config import settings
from src.logging_config import get_logger
from src.ops import params
from src.ops.db import OpsError

logger = get_logger("cloud_pricing.ops.tls")


def _read_root() -> tuple[str, str]:
    if settings.tls_root_dir:
        directory = Path(settings.tls_root_dir)
        try:
            return (directory / "root.key").read_text(), (directory / "root.crt").read_text()
        except FileNotFoundError as exc:
            raise OpsError(
                3, f"no TLS root in {directory} (run: deploy/app cert local --create)"
            ) from exc
    prefix = f"/cloud-pricing-app/{settings.app_environment}/tls"
    try:
        return params.get_parameter(f"{prefix}/root-key"), params.get_parameter(
            f"{prefix}/root-cert"
        )
    except Exception as exc:
        raise OpsError(3, f"TLS root not readable from SSM {prefix}/: {exc}") from exc


def _write_read_only(path: Path, content: str) -> None:
    path.unlink(missing_ok=True)
    path.write_text(content)
    path.chmod(0o400)


def _not_after(cert_pem: str) -> str | None:
    # The standard library can decode a certificate only from a file.
    with tempfile.NamedTemporaryFile("w", suffix=".pem") as f:
        f.write(cert_pem)
        f.flush()
        try:
            return ssl._ssl._test_decode_cert(f.name)["notAfter"]  # noqa: SLF001
        except Exception:  # noqa: BLE001 — informational only
            return None


def fetch_tls(out: Path) -> dict:
    key_pem, cert_pem = _read_root()
    try:
        fingerprint = hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert_pem)).hexdigest()
    except ValueError as exc:
        raise OpsError(3, "the stored TLS root certificate is not a PEM certificate") from exc
    out.mkdir(parents=True, exist_ok=True)
    _write_read_only(out / "root.key", key_pem)
    _write_read_only(out / "root.crt", cert_pem)
    not_after = _not_after(cert_pem)
    logger.info("tls root written", root_fingerprint_sha256=fingerprint, not_after=not_after)
    return {"root_fingerprint_sha256": fingerprint, "not_after": not_after}
