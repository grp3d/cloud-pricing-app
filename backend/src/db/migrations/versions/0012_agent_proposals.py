"""agent proposals

Revision ID: b81d5e0c2a47
Revises: 7c3e9a1f4d62
Create Date: 2026-11-15 12:00:00.000000

025-agent-architecture-changes (data-model.md §4): one row per proposal the agent made, a
reviewable change to an architecture, or a new architecture to create or import. It belongs to
its session and to the user message it answers; both cascade. It holds the base and target
states (research R2) and the cost summary shown, a record of what was shown, never a source of
prices (plan.md, Principle II).

Plain DDL only (no ORM import), like the other revisions.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b81d5e0c2a47'
down_revision: str | Sequence[str] | None = '7c3e9a1f4d62'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE TABLE agent_proposals (
          id uuid PRIMARY KEY,
          session_id uuid NOT NULL REFERENCES agent_sessions (id) ON DELETE CASCADE,
          message_id uuid NOT NULL REFERENCES agent_messages (id) ON DELETE CASCADE,
          seq integer NOT NULL,
          kind varchar(10) NOT NULL,
          architecture_id uuid,
          source_architecture_id uuid,
          title varchar(200) NOT NULL,
          status varchar(12) NOT NULL DEFAULT 'pending',
          items jsonb NOT NULL DEFAULT '[]',
          base_state jsonb,
          target_state jsonb NOT NULL DEFAULT '{}',
          base_fingerprint varchar(64),
          cost jsonb NOT NULL DEFAULT '{}',
          assumptions jsonb NOT NULL DEFAULT '[]',
          before_fingerprint varchar(64),
          after_fingerprint varchar(64),
          undo_status varchar(10),
          undo_end_reason varchar(16),
          created_at timestamptz NOT NULL DEFAULT now(),
          decided_at timestamptz,
          CONSTRAINT uq_agent_proposal_seq UNIQUE (session_id, seq),
          CONSTRAINT ck_agent_proposal_kind CHECK (kind IN ('change', 'create', 'import')),
          CONSTRAINT ck_agent_proposal_status
            CHECK (status IN ('pending', 'accepted', 'rejected', 'superseded', 'expired')),
          CONSTRAINT ck_agent_proposal_undo
            CHECK (undo_status IS NULL OR undo_status IN ('available', 'undone', 'ended')),
          CONSTRAINT ck_agent_proposal_undo_reason
            CHECK (undo_end_reason IS NULL OR undo_end_reason IN
                   ('edited', 'superseded', 'session_ended', 'deleted'))
        )
        """
    )
    op.execute("CREATE INDEX ix_agent_proposals_session ON agent_proposals (session_id, status)")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE agent_proposals")
