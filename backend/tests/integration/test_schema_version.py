"""The backend refuses to start against a database that isn't migrated to the code's revision."""

from __future__ import annotations

import pytest

from src.db import schema_version
from tests.conftest import test_engine


async def test_migrated_database_passes():
    await schema_version.check_schema_version(test_engine)
    assert (
        await schema_version.database_revision(test_engine)
        == schema_version.code_revision()
    )


async def test_older_database_is_refused(monkeypatch):
    actual = await schema_version.database_revision(test_engine)
    monkeypatch.setattr(schema_version, "code_revision", lambda: "newer0000000")
    with pytest.raises(schema_version.SchemaVersionMismatchError) as refused:
        await schema_version.check_schema_version(test_engine)
    message = str(refused.value)
    assert f"database is at migration {actual}" in message
    assert "the code expects newer0000000" in message
    assert "alembic upgrade head" in message
