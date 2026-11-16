"""025: helpers for tests that compare saved architectures (research R2)."""

from __future__ import annotations

import uuid

from src.models.orm import User
from src.services.architecture_state import ArchitectureState


async def make_user(db, prefix: str = "u") -> User:
    user = User(id=uuid.uuid4(), username=f"{prefix}-{uuid.uuid4().hex[:6]}")
    db.add(user)
    await db.flush()
    return user


def assert_state_equal(actual: ArchitectureState | None, expected: ArchitectureState) -> None:
    """Equal content, field by field, with a readable message naming the first difference."""
    assert actual is not None, "architecture not found"
    got, want = actual.canonical(), expected.canonical()
    if got == want:
        return
    for key in ("name", "provider"):
        assert got[key] == want[key], f"{key}: {got[key]!r} != {want[key]!r}"
    for key in ("collections", "services", "connectors"):
        got_rows = {row["id"]: row for row in got[key]}
        want_rows = {row["id"]: row for row in want[key]}
        missing = sorted(set(want_rows) - set(got_rows))
        extra = sorted(set(got_rows) - set(want_rows))
        assert not missing, f"{key}: missing {missing}"
        assert not extra, f"{key}: unexpected {extra}"
        for row_id, row in want_rows.items():
            for field, value in row.items():
                assert got_rows[row_id][field] == value, (
                    f"{key} {row_id} {field}: {got_rows[row_id][field]!r} != {value!r}")
