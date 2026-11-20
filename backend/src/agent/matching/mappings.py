"""Seed mapping lookup (026, research R3): the reviewed matches 022 made for the AWS standard
architectures, by product key. Read-only; the table changes only with a migration."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, select

from src.models.orm import ServiceMapping


@dataclass
class MappingPart:
    part: int
    target_key: str
    service_code: str
    sku: str | None  # 022's SKU, tried first in the target region
    options: dict | None
    quantity_factor: Decimal | None
    note: str | None


@dataclass
class MappingAlternative:
    number: int
    parts: list[MappingPart] = field(default_factory=list)
    omit_reason: str | None = None  # 022 left the figure out: "no equivalent"

    @property
    def note(self) -> str | None:
        return next((p.note for p in self.parts if p.note), None)


async def seed_version(session) -> int | None:
    return (await session.execute(select(func.max(ServiceMapping.version)))).scalar()


async def seed_mappings(session, source_provider: str, source_key: str,
                        target_provider: str) -> list[MappingAlternative]:
    """The alternatives for one source product on one target provider, in 022's order; empty
    when there is no seed mapping."""
    version = await seed_version(session)
    if version is None:
        return []
    rows = (await session.execute(
        select(ServiceMapping).where(
            ServiceMapping.version == version,
            ServiceMapping.source_provider == source_provider,
            ServiceMapping.source_key == source_key,
            ServiceMapping.target_provider == target_provider)
        .order_by(ServiceMapping.alternative, ServiceMapping.part))).scalars().all()
    alternatives: dict[int, MappingAlternative] = {}
    for row in rows:
        alternative = alternatives.setdefault(row.alternative,
                                              MappingAlternative(number=row.alternative))
        if row.target_key is None:
            alternative.omit_reason = row.omit_reason
            continue
        alternative.parts.append(MappingPart(
            part=row.part, target_key=row.target_key, service_code=row.target_service_code,
            sku=row.target_sku, options=row.target_options,
            quantity_factor=row.quantity_factor, note=row.note))
    return list(alternatives.values())
