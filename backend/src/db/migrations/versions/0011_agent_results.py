"""agent results

Revision ID: 7c3e9a1f4d62
Revises: 4f7a2c9e1b30
Create Date: 2026-11-13 12:00:00.000000

024-agent-pricing-questions (data-model.md §1): one row per comparison result shown in the
Agent tab's Results pane. A result belongs to its session and to the user message whose answer
produced it; both cascade. These rows are records of what was shown (with each provider's
snapshot revision), never a source of prices (plan.md, Principle II note).

Plain DDL only (no ORM import), like the other revisions.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7c3e9a1f4d62'
down_revision: str | Sequence[str] | None = '4f7a2c9e1b30'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE TABLE agent_results (
          id uuid PRIMARY KEY,
          session_id uuid NOT NULL REFERENCES agent_sessions (id) ON DELETE CASCADE,
          message_id uuid NOT NULL REFERENCES agent_messages (id) ON DELETE CASCADE,
          seq integer NOT NULL,
          kind varchar(30) NOT NULL,
          title varchar(200) NOT NULL,
          summary varchar(200) NOT NULL,
          basis jsonb NOT NULL DEFAULT '{}',
          sides jsonb NOT NULL DEFAULT '[]',
          rows jsonb NOT NULL DEFAULT '[]',
          totals jsonb NOT NULL DEFAULT '{}',
          snapshots jsonb NOT NULL DEFAULT '{}',
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT uq_agent_result_seq UNIQUE (session_id, seq),
          CONSTRAINT ck_agent_result_kind
            CHECK (kind IN ('category_comparison', 'architecture_comparison'))
        )
        """
    )
    op.execute("CREATE INDEX ix_agent_results_session ON agent_results (session_id)")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE agent_results")
