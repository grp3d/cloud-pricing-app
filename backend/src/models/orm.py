"""SQLAlchemy ORM models for all user-defined data (data-model.md).

Every table here is Postgres-owned, user-defined data per Constitution Principle II. None of
these tables ever store a vendor price — `SKUSelection` only stores a reference
(`service_code` + `sku`) into the read-only AWS Pricing Catalog (Parquet/DuckDB), resolved
live at calculation time by `src/services/price_calculation.py`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class User(Base):
    """The distinct identity that owns Architectures (spec FR-002)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    architectures: Mapped[list[Architecture]] = relationship(back_populates="user")


class Architecture(Base):
    """A user-owned, named, reusable, priced design (spec FR-001-003)."""

    __tablename__ = "architectures"
    __table_args__ = (
        CheckConstraint("provider IN ('aws', 'gcp', 'azure')", name="ck_architecture_provider"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False, default="aws")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    user: Mapped[User] = relationship(back_populates="architectures")
    collections: Mapped[list[Collection]] = relationship(
        back_populates="architecture", cascade="all, delete-orphan"
    )
    connectors: Mapped[list[DataConnector]] = relationship(
        back_populates="architecture", cascade="all, delete-orphan"
    )


class Collection(Base):
    """A user-defined grouping of AWS SKUs within an Architecture (spec FR-004)."""

    __tablename__ = "collections"
    __table_args__ = (
        CheckConstraint(
            "type IN ('application_component', 'vpc')", name="ck_collection_type"
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    architecture_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("architectures.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    architecture: Mapped[Architecture] = relationship(back_populates="collections")
    sku_selections: Mapped[list[SKUSelection]] = relationship(
        back_populates="collection",
        cascade="all, delete-orphan",
        foreign_keys="SKUSelection.collection_id",
    )


class DataConnector(Base):
    """A user-created link between two Collections in the same Architecture (spec FR-008-009)."""

    __tablename__ = "data_connectors"
    __table_args__ = (
        CheckConstraint(
            "from_collection_id != to_collection_id", name="ck_connector_no_self_link"
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    architecture_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("architectures.id"), nullable=False, index=True
    )
    from_collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collections.id"), nullable=False
    )
    to_collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collections.id"), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    architecture: Mapped[Architecture] = relationship(back_populates="connectors")
    sku_selection: Mapped[SKUSelection | None] = relationship(
        back_populates="connector",
        cascade="all, delete-orphan",
        foreign_keys="SKUSelection.connector_id",
        uselist=False,
    )


class SKUSelection(Base):
    """A reference to one AWS pricing catalog SKU plus pricing inputs (spec FR-006-007, FR-009).

    Exactly one of collection_id / connector_id is set (never both, never neither) — see
    ck_sku_selection_exactly_one_parent.
    """

    __tablename__ = "sku_selections"
    __table_args__ = (
        CheckConstraint(
            "(collection_id IS NOT NULL)::int + (connector_id IS NOT NULL)::int = 1",
            name="ck_sku_selection_exactly_one_parent",
        ),
        CheckConstraint(
            "pricing_term IN ('on_demand', 'reserved_1yr', 'reserved_3yr')",
            name="ck_sku_selection_pricing_term",
        ),
        CheckConstraint(
            "purchase_option IN "
            "('no_upfront', 'partial_upfront', 'all_upfront', 'not_applicable')",
            name="ck_sku_selection_purchase_option",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    collection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collections.id"), nullable=True, index=True
    )
    connector_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("data_connectors.id"), nullable=True, index=True, unique=True
    )
    service_code: Mapped[str] = mapped_column(String(100), nullable=False)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    pricing_term: Mapped[str] = mapped_column(String(20), nullable=False)
    purchase_option: Mapped[str] = mapped_column(String(20), nullable=False)
    usage_quantity: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    collection: Mapped[Collection | None] = relationship(
        back_populates="sku_selections", foreign_keys=[collection_id]
    )
    connector: Mapped[DataConnector | None] = relationship(
        back_populates="sku_selection", foreign_keys=[connector_id]
    )
