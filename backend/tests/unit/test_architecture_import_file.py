"""Unit tests for the Admin file import service (014-architecture-templates-import-export,
spec FR-018-FR-023, SC-006; research.md §8-§9).

Runs against the real test database and pricing data (`find_existing_skus` /
`list_available_regions`), using the known fixture SKU for valid entries and an impossible SKU
for the missing-service case.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from src.models.orm import Architecture, Collection, SKUSelection, User
from src.services import architecture_transfer
from src.services.architecture_transfer import InvalidImportFileError, import_architectures

KNOWN = ("AmazonEC2", "NN4EGUUQRWVYP98C")  # us-east-1 t3.medium, present in the fixture


def _entry(name: str, sku: str = KNOWN[1]) -> dict:
    return {
        "name": name,
        "provider": "aws",
        "collections": [
            {
                "ref": "c1",
                "type": "vpc",
                "name": "VPC (us-east-1)",
                "region": "us-east-1",
                "parent_ref": None,
                "sku_selections": [
                    {
                        "service_code": KNOWN[0],
                        "sku": sku,
                        "pricing_term": "on_demand",
                        "purchase_option": "not_applicable",
                        "usage_quantity": "24.0000",
                    }
                ],
            },
            {
                "ref": "c2",
                "type": "application_component",
                "name": "Web tier",
                "region": "us-east-1",
                "parent_ref": "c1",
                "sku_selections": [],
            },
        ],
        "connectors": [],
    }


def _doc(*entries) -> dict:
    return {
        "format": "cloud-pricing-architectures",
        "format_version": 1,
        "exported_at": "2026-09-25T14:30:22Z",
        "source_username": "someone",
        "architectures": list(entries),
    }


async def _owner(db_session, *existing_names: str) -> User:
    owner = User(id=uuid.uuid4(), username=f"u-{uuid.uuid4().hex[:8]}")
    db_session.add(owner)
    for name in existing_names:
        db_session.add(Architecture(id=uuid.uuid4(), user_id=owner.id, name=name, provider="aws"))
    await db_session.commit()
    return owner


async def _owned(db_session, owner: User) -> list[Architecture]:
    return (
        await db_session.execute(
            select(Architecture).where(Architecture.user_id == owner.id).order_by(Architecture.name)
        )
    ).scalars().all()


@pytest.mark.parametrize(
    "doc",
    [[], {"format": "other", "format_version": 1, "architectures": []}, {"format_version": 1}],
)
async def test_bad_envelope_rejected_and_nothing_written(db_session, doc):
    owner = await _owner(db_session)
    with pytest.raises(InvalidImportFileError):
        await import_architectures(db_session, owner=owner, doc=doc)
    assert await _owned(db_session, owner) == []


async def test_partial_success_in_file_order(db_session):
    owner = await _owner(db_session, "Taken")
    result = await import_architectures(
        db_session,
        owner=owner,
        doc=_doc(_entry("Fresh"), _entry("Taken"), _entry("Legacy", sku="ZZZZZZZZZZZZZZZZ")),
    )
    assert [(r.name, r.status, r.error) for r in result.results] == [
        ("Fresh", "success", None),
        ("Taken", "failed", "Architecture name already exists"),
        (
            "Legacy",
            "failed",
            "Service not found in pricing data: AmazonEC2 / ZZZZZZZZZZZZZZZZ (us-east-1)",
        ),
    ]
    assert (result.imported_count, result.failed_count) == (1, 2)

    owned = await _owned(db_session, owner)
    assert [a.name for a in owned] == ["Fresh", "Taken"]
    fresh = next(a for a in owned if a.name == "Fresh")
    assert fresh.is_public is False and fresh.user_id == owner.id
    collections = (
        await db_session.execute(
            select(Collection).where(Collection.architecture_id == fresh.id)
        )
    ).scalars().all()
    by_name = {c.name: c for c in collections}
    assert by_name["Web tier"].parent_collection_id == by_name["VPC (us-east-1)"].id
    skus = (
        await db_session.execute(
            select(SKUSelection.sku).where(
                SKUSelection.collection_id == by_name["VPC (us-east-1)"].id
            )
        )
    ).scalars().all()
    assert skus == [KNOWN[1]]


async def test_duplicate_names_within_one_file(db_session):
    owner = await _owner(db_session)
    result = await import_architectures(
        db_session, owner=owner, doc=_doc(_entry("Twin"), _entry("Twin"))
    )
    assert [r.status for r in result.results] == ["success", "failed"]
    assert result.results[1].error == "Architecture name already exists"


async def test_unreadable_entry_has_no_name(db_session):
    owner = await _owner(db_session)
    result = await import_architectures(
        db_session, owner=owner, doc=_doc({"provider": "aws"}, "not an object")
    )
    assert [(r.name, r.status) for r in result.results] == [(None, "failed"), (None, "failed")]
    assert all(r.error.startswith("Invalid architecture definition:") for r in result.results)


async def test_empty_file_is_a_valid_empty_import(db_session):
    owner = await _owner(db_session)
    result = await import_architectures(db_session, owner=owner, doc=_doc())
    assert (result.imported_count, result.failed_count, result.results) == (0, 0, [])


async def test_database_error_rolls_back_only_that_entry(db_session, monkeypatch):
    owner = await _owner(db_session)
    real_build = architecture_transfer.build_architecture

    def flaky_build(session, **kwargs):
        if kwargs["name"] == "Broken":
            raise SQLAlchemyError("boom")
        return real_build(session, **kwargs)

    monkeypatch.setattr(architecture_transfer, "build_architecture", flaky_build)
    result = await import_architectures(
        db_session, owner=owner, doc=_doc(_entry("Before"), _entry("Broken"), _entry("After"))
    )
    assert [(r.name, r.status, r.error) for r in result.results] == [
        ("Before", "success", None),
        ("Broken", "failed", "Could not save architecture"),
        ("After", "success", None),
    ]
    assert [a.name for a in await _owned(db_session, owner)] == ["After", "Before"]


async def test_sku_existence_checked_once_per_region(db_session, monkeypatch):
    owner = await _owner(db_session)
    calls: list[str] = []
    real = architecture_transfer.find_existing_skus

    def spy(pairs, *, region, snapshot_date=None):
        calls.append(region)
        return real(pairs, region=region, snapshot_date=snapshot_date)

    monkeypatch.setattr(architecture_transfer, "find_existing_skus", spy)
    await import_architectures(
        db_session, owner=owner, doc=_doc(_entry("A"), _entry("B"), _entry("C"))
    )
    assert calls == ["us-east-1"]
