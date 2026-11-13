"""agent foundation

Revision ID: 4f7a2c9e1b30
Revises: 9b4e2c7a1d05
Create Date: 2026-11-12 12:00:00.000000

023-agent-foundation (data-model.md §1–§6): the agent's settings row, sessions, messages, the
activity log (operations), usage records, and three per-user agent columns on `users`.

Plain DDL only (no ORM import), like the other revisions. Usage records keep their user and
outlive sessions (`session_id` is set to null when a session is deleted), because monthly limits
are counted from them (FR-013).
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '4f7a2c9e1b30'
down_revision: str | Sequence[str] | None = '9b4e2c7a1d05'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        ALTER TABLE users
          ADD COLUMN agent_enabled_for_user boolean NOT NULL DEFAULT false,
          ADD COLUMN agent_preview_input_counter integer NOT NULL DEFAULT 3,
          ADD COLUMN agent_monthly_input_limit integer,
          ADD CONSTRAINT ck_user_agent_preview_nonnegative
            CHECK (agent_preview_input_counter >= 0),
          ADD CONSTRAINT ck_user_agent_monthly_limit_nonnegative
            CHECK (agent_monthly_input_limit IS NULL OR agent_monthly_input_limit >= 0)
        """
    )
    op.execute(
        """
        CREATE TABLE agent_settings (
          id integer PRIMARY KEY DEFAULT 1,
          agent_enabled boolean,
          agent_provider varchar(20),
          agent_model varchar(200),
          agent_base_url varchar(500),
          agent_timeout_seconds integer,
          agent_global_monthly_cap_usd numeric(10, 2),
          agent_default_user_monthly_inputs integer,
          agent_price_per_input_token_usd numeric(14, 10),
          agent_price_per_output_token_usd numeric(14, 10),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT ck_agent_settings_single_row CHECK (id = 1)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE agent_sessions (
          id uuid PRIMARY KEY,
          user_id uuid NOT NULL UNIQUE REFERENCES users (id) ON DELETE CASCADE,
          started_at timestamptz NOT NULL,
          closes_at timestamptz NOT NULL,
          busy_message_id uuid
        )
        """
    )
    op.execute(
        """
        CREATE TABLE agent_messages (
          id uuid PRIMARY KEY,
          session_id uuid NOT NULL REFERENCES agent_sessions (id) ON DELETE CASCADE,
          seq integer NOT NULL,
          role varchar(10) NOT NULL,
          content text NOT NULL,
          architecture_id uuid,
          status varchar(20) NOT NULL,
          error_kind varchar(20),
          is_preview boolean NOT NULL DEFAULT false,
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT uq_agent_message_seq UNIQUE (session_id, seq),
          CONSTRAINT ck_agent_message_role CHECK (role IN ('user', 'agent'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE agent_operations (
          id uuid PRIMARY KEY,
          session_id uuid NOT NULL REFERENCES agent_sessions (id) ON DELETE CASCADE,
          message_id uuid NOT NULL REFERENCES agent_messages (id) ON DELETE CASCADE,
          seq integer NOT NULL,
          name varchar(100) NOT NULL,
          inputs jsonb NOT NULL DEFAULT '{}',
          outcome varchar(10) NOT NULL,
          summary jsonb NOT NULL DEFAULT '{}',
          snapshot jsonb,
          figures_removed integer NOT NULL DEFAULT 0,
          started_at timestamptz NOT NULL,
          duration_ms integer NOT NULL DEFAULT 0
        )
        """
    )
    op.execute("CREATE INDEX ix_agent_operations_session ON agent_operations (session_id)")
    op.execute(
        """
        CREATE TABLE agent_usage (
          id uuid PRIMARY KEY,
          user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
          session_id uuid REFERENCES agent_sessions (id) ON DELETE SET NULL,
          message_id uuid,
          created_at timestamptz NOT NULL DEFAULT now(),
          provider varchar(20) NOT NULL,
          model varchar(200) NOT NULL,
          input_tokens integer NOT NULL DEFAULT 0,
          output_tokens integer NOT NULL DEFAULT 0,
          cost_usd numeric(12, 6) NOT NULL DEFAULT 0,
          counts_as_input boolean NOT NULL DEFAULT false,
          is_preview boolean NOT NULL DEFAULT false
        )
        """
    )
    op.execute("CREATE INDEX ix_agent_usage_user_created ON agent_usage (user_id, created_at)")
    op.execute("CREATE INDEX ix_agent_usage_created ON agent_usage (created_at)")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE agent_usage")
    op.execute("DROP TABLE agent_operations")
    op.execute("DROP TABLE agent_messages")
    op.execute("DROP TABLE agent_sessions")
    op.execute("DROP TABLE agent_settings")
    op.execute(
        """
        ALTER TABLE users
          DROP CONSTRAINT ck_user_agent_monthly_limit_nonnegative,
          DROP CONSTRAINT ck_user_agent_preview_nonnegative,
          DROP COLUMN agent_monthly_input_limit,
          DROP COLUMN agent_preview_input_counter,
          DROP COLUMN agent_enabled_for_user
        """
    )
