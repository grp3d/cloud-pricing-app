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
    """The distinct identity that owns Architectures (spec FR-002).

    `username IS NULL` rows are anonymous, lazily-created guest identities (one per browser,
    unchanged since 001) — `username` is set exactly once, at admin creation time, for a named
    account (012-user-accounts-sharing, spec FR-005). `is_default_admin` marks only the single
    seeded Admin row (migration `0004_user_accounts_sharing`) that can never be deactivated or
    purged (FR-013) — kept distinct from `is_admin` so a future admin-*promoted* user would
    remain purgeable/deactivatable.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    username: Mapped[str | None] = mapped_column(String(255), default=None)
    password_hash: Mapped[str | None] = mapped_column(default=None)
    is_active: Mapped[bool] = mapped_column(default=True)
    is_admin: Mapped[bool] = mapped_column(default=False)
    is_default_admin: Mapped[bool] = mapped_column(default=False)
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
    # Owner-toggled visibility (012-user-accounts-sharing, spec FR-020) — only a named user's
    # (username IS NOT NULL) architecture may ever be public; enforced in the service layer,
    # not here, since it depends on the *owner's* row, not this one.
    is_public: Mapped[bool] = mapped_column(default=False)
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
    """A user-defined grouping of AWS SKUs within an Architecture (spec FR-004).

    May optionally be nested inside a VPC Collection via `parent_collection_id`
    (002-vpc-component-nesting, spec FR-001-FR-004): only an `application_component` may have a
    parent, and that parent must itself be a `vpc` (enforced at the DB layer for the single-row
    rule; the cross-row "parent must actually be type=vpc" rule is enforced in
    `services/architecture_service.py`, since a CHECK constraint cannot reference another row).
    """

    __tablename__ = "collections"
    __table_args__ = (
        CheckConstraint(
            "type IN ('application_component', 'vpc')", name="ck_collection_type"
        ),
        CheckConstraint(
            "parent_collection_id IS NULL OR type = 'application_component'",
            name="ck_collection_parent_only_app_component",
        ),
        CheckConstraint(
            "parent_collection_id != id", name="ck_collection_no_self_parent"
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    architecture_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("architectures.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # AWS region this collection belongs to (010-multi-region-support, spec FR-002). A plain
    # string, not a DB enum/FK: the set of valid values is driven by which regions the pricing
    # dataset currently has data for (research.md §1, §3), which changes independently of this
    # schema — validated at the API layer against `GET /regions`, not here.
    region: Mapped[str] = mapped_column(String(20), nullable=False)
    parent_collection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collections.id", ondelete="SET NULL"), nullable=True, index=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    architecture: Mapped[Architecture] = relationship(back_populates="collections")
    # `order_by` (live user report): without it, Postgres has no guaranteed return order for
    # this relationship at all — in practice it often happened to match insertion order until
    # an UPDATE to one row (e.g. saving a Service Editor change) shifted that row's physical
    # tuple, which could then change the *whole list's* apparent order on the next fetch, with
    # no relationship to what the user actually did. Ordering by `created_at` makes "services
    # appear in the order they were added to the Collection, and stay there regardless of what
    # gets edited later" a guarantee of the query itself, not an accident of physical storage.
    sku_selections: Mapped[list[SKUSelection]] = relationship(
        back_populates="collection",
        cascade="all, delete-orphan",
        foreign_keys="SKUSelection.collection_id",
        order_by="SKUSelection.created_at",
    )
    parent: Mapped[Collection | None] = relationship(
        remote_side="Collection.id", foreign_keys=[parent_collection_id], back_populates="children"
    )
    children: Mapped[list[Collection]] = relationship(
        back_populates="parent", foreign_keys=[parent_collection_id]
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
    # 010-multi-region-support: lets callers resolve a Connector's search/pricing region
    # (spec FR-006 — always the "from" side) as `connector.from_collection.region` without a
    # separate query, when eager-loaded.
    from_collection: Mapped[Collection] = relationship(foreign_keys=[from_collection_id])
    to_collection: Mapped[Collection] = relationship(foreign_keys=[to_collection_id])


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
