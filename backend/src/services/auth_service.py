"""Password hashing (012-user-accounts-sharing, research.md §2).

Stdlib `hashlib.pbkdf2_hmac` — a real, salted, iterated one-way hash — deliberately chosen over
adding `passlib`/`bcrypt` as a new dependency: the spec frames this as a temporary v1 ("in later
versions we will introduce better security via a system like Supabase"), so the stdlib already
satisfies "a standard one-way hash" (spec Assumptions) without a new dependency (Principle VI).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    """Hash `password`, returning `"pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>"`."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"{_ALGORITHM}${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Check `password` against a hash produced by `hash_password`."""
    try:
        algorithm, iterations_str, salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    if algorithm != _ALGORITHM:
        return False
    salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations_str))
    return hmac.compare_digest(digest.hex(), hash_hex)
