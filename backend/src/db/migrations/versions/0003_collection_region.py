"""collection region

Revision ID: a5f7c446f131
Revises: 0cfcc0d58f3f
Create Date: 2026-09-15 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a5f7c446f131'
down_revision: Union[str, Sequence[str], None] = '0cfcc0d58f3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The app's former single global pricing region (010-multi-region-support, spec FR-016,
# Clarifications) — every collection that existed before this migration is backfilled to this
# literal value, preserving its current pricing behavior unchanged.
_FORMER_GLOBAL_REGION = "us-east-1"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('collections', sa.Column('region', sa.String(), nullable=True))
    op.execute(
        sa.text("UPDATE collections SET region = :region WHERE region IS NULL").bindparams(
            region=_FORMER_GLOBAL_REGION
        )
    )
    op.alter_column('collections', 'region', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('collections', 'region')
