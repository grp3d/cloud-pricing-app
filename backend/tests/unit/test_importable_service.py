"""The shared importable listing (012 FR-023–FR-026; 023 US2 reuses it for the agent)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from src.models.orm import Architecture, User
from src.services.importable import importable_architectures


async def _user(db, name):
    user = User(id=uuid.uuid4(), username=name)
    db.add(user)
    await db.flush()
    return user


async def test_grouped_by_owner_admin_first_and_only_others_public(db_session, admin_headers):
    from sqlalchemy import select

    admin = (await db_session.execute(select(User).where(User.is_default_admin))).scalar_one()
    me = await _user(db_session, "me")
    zed, amy = await _user(db_session, "zed"), await _user(db_session, "amy")
    for owner, name, public, provider, deleted in [
        (admin, "B admin", True, "aws", False), (admin, "A admin", True, "aws", False),
        (zed, "Z1", True, "aws", False), (amy, "A1", True, "gcp", False),
        (amy, "private", False, "aws", False), (amy, "gone", True, "aws", True),
        (me, "mine", True, "aws", False),
    ]:
        db_session.add(Architecture(user_id=owner.id, name=name, provider=provider,
                                    is_public=public,
                                    deleted_at=datetime.now(UTC) if deleted else None))
    await db_session.commit()

    result = await importable_architectures(db_session, me)
    assert [(g.owner_username, [a.name for a in g.architectures]) for g in result.groups] == [
        ("Admin", ["A admin", "B admin"]), ("amy", ["A1"]), ("zed", ["Z1"]),
    ]
    gcp = await importable_architectures(db_session, me, "gcp")
    assert [(g.owner_username, [a.name for a in g.architectures]) for g in gcp.groups] == [
        ("amy", ["A1"]),
    ]
