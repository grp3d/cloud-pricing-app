"""Every seeded standard-architecture entry is priceable (014-architecture-templates-import-export,
spec SC-003).

Builds each seeded definition with the shared row builder under a throwaway user and prices it
for one month against whatever pricing dataset `AWS_PRICING_PARQUET_DIR` points at. An entry
whose unit isn't recognized, or whose SKU has no On-Demand price, would surface as unpriceable.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.models.orm import Architecture, Collection, DataConnector, User
from src.models.schemas import ArchitectureExportFile, CalculationDuration
from src.services.architecture_transfer import build_architecture, specs_from_definition
from src.services.price_calculation import calculate_architecture_price

SEED_PATH = Path(__file__).resolve().parents[2] / "src" / "db" / "seed" / (
    "standard_architectures.json"
)
SEED = ArchitectureExportFile.model_validate_json(SEED_PATH.read_text())


@pytest.mark.parametrize("definition", SEED.architectures, ids=lambda d: d.name)
async def test_seeded_architecture_prices_with_no_unpriceable_items(db_session, definition):
    owner = User(id=uuid.uuid4())
    db_session.add(owner)
    collections, connectors = specs_from_definition(definition)
    architecture = build_architecture(
        db_session,
        owner=owner,
        name=definition.name,
        provider=definition.provider,
        collections=collections,
        connectors=connectors,
    )
    await db_session.commit()

    loaded = (
        await db_session.execute(
            select(Architecture)
            .where(Architecture.id == architecture.id)
            .options(
                selectinload(Architecture.collections).selectinload(Collection.sku_selections),
                selectinload(Architecture.connectors).selectinload(DataConnector.sku_selection),
            )
        )
    ).scalar_one()

    result = calculate_architecture_price(loaded, CalculationDuration.one_month)

    assert result.unpriceable == [], [
        (u.service_code, u.sku, u.reason) for u in result.unpriceable
    ]
    expected_entries = sum(len(c.sku_selections) for c in definition.collections)
    assert len(result.line_items) == expected_entries
    assert all(item.priceable for item in result.line_items)
    assert result.total_price > 0
