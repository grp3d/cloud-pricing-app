"""Unit tests for password hashing (012-user-accounts-sharing, research.md §2).

Uses the stdlib `hashlib.pbkdf2_hmac`-based hash/verify pair — no new dependency (Constitution
Principle VI). Never asserts on the plaintext password anywhere but the input.
"""

from __future__ import annotations

from src.services.auth_service import hash_password, verify_password


def test_hash_has_expected_format():
    stored = hash_password("hunter2")
    parts = stored.split("$")
    assert len(parts) == 4
    algorithm, iterations, salt_hex, hash_hex = parts
    assert algorithm == "pbkdf2_sha256"
    assert int(iterations) > 0
    bytes.fromhex(salt_hex)
    bytes.fromhex(hash_hex)


def test_verify_succeeds_for_correct_password():
    stored = hash_password("hunter2")
    assert verify_password("hunter2", stored) is True


def test_verify_fails_for_wrong_password():
    stored = hash_password("hunter2")
    assert verify_password("wrong-password", stored) is False


def test_two_hashes_of_same_password_differ():
    first = hash_password("hunter2")
    second = hash_password("hunter2")
    assert first != second
    # ...but both still verify against the same plaintext.
    assert verify_password("hunter2", first) is True
    assert verify_password("hunter2", second) is True
