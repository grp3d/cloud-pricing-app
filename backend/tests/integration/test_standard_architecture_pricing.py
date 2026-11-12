"""Every seeded standard-architecture entry is priceable (014-architecture-templates-import-export,
spec SC-003).

Builds each seeded definition with the shared row builder under a throwaway user and prices it
for one month against whatever pricing dataset `PRICING_DATA_URI` points at. An entry
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
STANDARD_PRICING_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "pricing_parquet_standard"
# 022: the GCP and Azure standard architectures price fully too (SC-002).
DEFINITIONS = list(SEED.architectures) + [
    definition
    for provider in ("gcp", "azure")
    for definition in ArchitectureExportFile.model_validate_json(
        SEED_PATH.with_name(f"standard_architectures_{provider}.json").read_text()
    ).architectures
]


@pytest.mark.parametrize("definition", DEFINITIONS, ids=lambda d: f"{d.provider}: {d.name}")
async def test_seeded_architecture_prices_with_no_unpriceable_items(
    db_session, definition, use_pricing_root
):
    if definition.provider != "aws":
        # 022: the GCP and Azure seeds' items are in their own fixture root.
        use_pricing_root(STANDARD_PRICING_ROOT)
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
