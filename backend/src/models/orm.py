"""SQLAlchemy ORM models for all user-defined data (data-model.md).

Every table here is Postgres-owned, user-defined data per Constitution Principle II. None of
these tables ever store a vendor price — `SKUSelection` only stores a reference
(`service_code` + `sku`) into the read-only AWS Pricing Catalog (Parquet/DuckDB), resolved
live at calculation time by `src/services/price_calculation.py`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
    # 023-agent-foundation (data-model §2, FR-019–FR-021): Admin-controlled agent access. A new
    # named user starts with the agent off and 3 free preview inputs; a null monthly limit
    # means the app-wide default. Guests keep the columns but never use the agent.
    agent_enabled_for_user: Mapped[bool] = mapped_column(default=False, server_default="false")
    agent_preview_input_counter: Mapped[int] = mapped_column(default=3, server_default="3")
    agent_monthly_input_limit: Mapped[int | None] = mapped_column(default=None)

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
    # 019 (data-model §4): varchar(64), for GCP and Azure location names.
    region: Mapped[str] = mapped_column(String(64), nullable=False)
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
        CheckConstraint(
            "arrow_style IN ('none', 'one_way', 'two_way', 'one_to_many', 'many_to_one')",
            name="ck_connector_arrow_style",
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
    # 019 (data-model §5): how the diagram draws the connector. Visual only.
    arrow_style: Mapped[str] = mapped_column(String(20), nullable=False, default="none",
                                             server_default="none")
    arrow_reversed: Mapped[bool] = mapped_column(nullable=False, default=False,
                                                 server_default="false")
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
    # 019: extra boxes of a one-to-many / many-to-one connector, oldest first.
    branches: Mapped[list[ConnectorBranch]] = relationship(
        back_populates="connector", cascade="all, delete-orphan",
        order_by="ConnectorBranch.created_at",
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
            "pricing_term IN ('on_demand', 'reserved_1yr', 'reserved_3yr', "
            "'savings_plan_1yr', 'savings_plan_3yr', 'commitment_1yr', 'commitment_3yr')",
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
    # 019 (data-model §3): `gcp_machine` / `azure_vm` options; null = the common pricing path.
    provider_options: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    collection: Mapped[Collection | None] = relationship(
        back_populates="sku_selections", foreign_keys=[collection_id]
    )
    connector: Mapped[DataConnector | None] = relationship(
        back_populates="sku_selection", foreign_keys=[connector_id]
    )


class ConnectorBranch(Base):
    """019 (data-model §5): one extra box of a one-to-many (extra "to") or many-to-one (extra
    "from") connector. Same-architecture and no-duplicate rules are in the service layer."""

    __tablename__ = "connector_branches"
    __table_args__ = (
        UniqueConstraint("connector_id", "collection_id", name="uq_connector_branch"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    connector_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_connectors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collections.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    connector: Mapped[DataConnector] = relationship(back_populates="branches")


class UserPreferences(Base):
    """019 (data-model §1): one typed JSON row per user (named or guest)."""

    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict,
                                       server_default="{}")
    schema_version: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class ServiceCategoryRule(Base):
    """019 (data-model §2, research R9): a provider grouping → a shared category."""

    __tablename__ = "service_category_rules"
    __table_args__ = (
        CheckConstraint("provider IN ('aws', 'gcp', 'azure')",
                        name="ck_service_category_rule_provider"),
        CheckConstraint("category IN ('compute', 'storage', 'database', 'networking')",
                        name="ck_service_category_rule_category"),
        UniqueConstraint("provider", "match_field", "match_value",
                         name="uq_service_category_rule_match"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    match_field: Mapped[str] = mapped_column(String(40), nullable=False)
    match_value: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    priority: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")


# --- 023-agent-foundation (data-model.md §1–§6) ------------------------------------------------


class AgentSettings(Base):
    """The single row of Admin-edited agent settings. A null column means "use the environment
    default" (research R5). The model API key is deliberately not stored here (FR-017)."""

    __tablename__ = "agent_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    agent_enabled: Mapped[bool | None] = mapped_column(default=None)
    agent_provider: Mapped[str | None] = mapped_column(String(20), default=None)
    agent_model: Mapped[str | None] = mapped_column(String(200), default=None)
    agent_base_url: Mapped[str | None] = mapped_column(String(500), default=None)
    agent_timeout_seconds: Mapped[int | None] = mapped_column(default=None)
    agent_global_monthly_cap_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), default=None
    )
    agent_default_user_monthly_inputs: Mapped[int | None] = mapped_column(default=None)
    agent_price_per_input_token_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 10), default=None
    )
    agent_price_per_output_token_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 10), default=None
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AgentSession(Base):
    """A user's one agent session (FR-010, FR-011): closed and deleted 3 days after it starts.
    `busy_message_id` is set while a message is being answered, so a second send is refused."""

    __tablename__ = "agent_sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    busy_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)


class AgentMessage(Base):
    """One turn of a session's conversation. An agent message's `content` is the text as shown,
    figure references already replaced by the pricing engine's values (research R1)."""

    __tablename__ = "agent_messages"
    __table_args__ = (
        UniqueConstraint("session_id", "seq", name="uq_agent_message_seq"),
        CheckConstraint("role IN ('user', 'agent')", name="ck_agent_message_role"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str] = mapped_column(nullable=False)
    # No FK: the architecture may later be deleted; the message keeps what was open (FR-012).
    architecture_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_kind: Mapped[str | None] = mapped_column(String(20), default=None)
    is_preview: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AgentOperation(Base):
    """One operation the agent ran: the activity log (FR-024, Principle VII)."""

    __tablename__ = "agent_operations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_messages.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    inputs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    outcome: Mapped[str] = mapped_column(String(10), nullable=False)
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    snapshot: Mapped[dict | None] = mapped_column(JSONB, default=None)
    figures_removed: Mapped[int] = mapped_column(default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int] = mapped_column(default=0)


class AgentUsage(Base):
    """One model call (research R7). Kept after its session is deleted (FR-013): monthly limits
    and the global spending cap are counted from these rows."""

    __tablename__ = "agent_usage"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="SET NULL"), default=None
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal(0))
    counts_as_input: Mapped[bool] = mapped_column(default=False)
    is_preview: Mapped[bool] = mapped_column(default=False)


class AgentResult(Base):
    """One comparison result shown in the Agent tab's Results pane (024, data-model.md §1).

    It belongs to the session and to the **user** message whose answer produced it (the agent
    message is written only when the answer ends). Principle II: this is a record of what the
    agent showed, with each provider's snapshot date and revision, like `agent_messages.content`.
    It is never read as a source of prices; every comparison prices afresh through the engine.
    Don't reuse it as a price cache."""

    __tablename__ = "agent_results"
    __table_args__ = (
        UniqueConstraint("session_id", "seq", name="uq_agent_result_seq"),
        CheckConstraint("kind IN ('category_comparison', 'architecture_comparison')",
                        name="ck_agent_result_kind"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_messages.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(String(200), nullable=False)
    basis: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    sides: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    rows: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    totals: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    snapshots: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AgentProposal(Base):
    """One proposal the agent made (025, data-model.md §4): a reviewable change to an
    architecture, or a new architecture to create or import. Nothing is saved to architectures
    until the user accepts (FR-003); accept, undo and redo apply `target_state` or `base_state`
    (research R2). Principle II: `cost` is a record of what was shown, with its snapshot; nothing
    prices from it (a stale proposal is re-priced before acceptance)."""

    __tablename__ = "agent_proposals"
    __table_args__ = (
        UniqueConstraint("session_id", "seq", name="uq_agent_proposal_seq"),
        CheckConstraint("kind IN ('change', 'create', 'import', 'translate')",
                        name="ck_agent_proposal_kind"),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'superseded', 'expired')",
            name="ck_agent_proposal_status"),
        CheckConstraint("undo_status IS NULL OR undo_status IN ('available', 'undone', 'ended')",
                        name="ck_agent_proposal_undo"),
        CheckConstraint(
            "undo_end_reason IS NULL OR undo_end_reason IN "
            "('edited', 'superseded', 'session_ended', 'deleted')",
            name="ck_agent_proposal_undo_reason"),
        Index("ix_agent_proposals_session", "session_id", "status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_messages.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    architecture_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)
    source_architecture_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
                                                                     default=None)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")
    items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    base_state: Mapped[dict | None] = mapped_column(JSONB, default=None)
    target_state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    base_fingerprint: Mapped[str | None] = mapped_column(String(64), default=None)
    cost: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    assumptions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # 026: a translation's record (data-model.md §2): mapping table, cost difference, regions,
    # choices, mapping version and the source's fingerprint. Null for other kinds.
    translation: Mapped[dict | None] = mapped_column(JSONB, default=None)
    before_fingerprint: Mapped[str | None] = mapped_column(String(64), default=None)
    after_fingerprint: Mapped[str | None] = mapped_column(String(64), default=None)
    undo_status: Mapped[str | None] = mapped_column(String(10), default=None)
    undo_end_reason: Mapped[str | None] = mapped_column(String(16), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class ServiceMapping(Base):
    """A seed mapping (026, data-model.md §1): one kind of AWS product → its equivalent on GCP or
    Azure, in every region, generated from 022's rules and inserted by migration 0013. Linking
    data by product keys (research R2), never labels or prices (Principle II). Read-only at run
    time."""

    __tablename__ = "service_mappings"
    __table_args__ = (
        UniqueConstraint("version", "source_provider", "source_key", "target_provider",
                         "alternative", "part", name="uq_service_mapping"),
        CheckConstraint("(target_key IS NULL) <> (omit_reason IS NULL)",
                        name="ck_service_mapping_target"),
        CheckConstraint("source_provider <> target_provider",
                        name="ck_service_mapping_providers"),
        Index("ix_service_mappings_source", "source_provider", "source_key", "target_provider"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    version: Mapped[int] = mapped_column(nullable=False)
    source_provider: Mapped[str] = mapped_column(String(10), nullable=False)
    source_key: Mapped[str] = mapped_column(String(400), nullable=False)
    target_provider: Mapped[str] = mapped_column(String(10), nullable=False)
    alternative: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    part: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    target_key: Mapped[str | None] = mapped_column(String(400), default=None)
    target_service_code: Mapped[str | None] = mapped_column(String(100), default=None)
    target_sku: Mapped[str | None] = mapped_column(String(200), default=None)
    target_options: Mapped[dict | None] = mapped_column(JSONB, default=None)
    quantity_factor: Mapped[Decimal | None] = mapped_column(Numeric, default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    omit_reason: Mapped[str | None] = mapped_column(Text, default=None)
    origin: Mapped[str] = mapped_column(String(20), nullable=False)
