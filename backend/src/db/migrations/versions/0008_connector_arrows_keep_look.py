"""existing connectors keep their arrowhead

Revision ID: 6c3e9a1b5f08
Revises: 4d8a2f7c9e07
Create Date: 2026-11-05 12:00:00.000000

019-gcp-azure-providers-trends (FR-026, data-model §5): arrow style `none` is drawn as a plain
line, but every connector made before 019 was drawn with an arrowhead at its `to` end (010).
0006 added `arrow_style` with the default `none`, so this sets the connectors that existed then
to `one_way`, and existing diagrams look as before. Only rows still at `none` and not reversed
are changed; nothing could have set them through the app before this release.

Downgrade leaves the styles as they are: `one_way` set here can't be told from one a user chose.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '6c3e9a1b5f08'
down_revision: Union[str, Sequence[str], None] = '4d8a2f7c9e07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "UPDATE data_connectors SET arrow_style = 'one_way' "
        "WHERE arrow_style = 'none' AND arrow_reversed = false"
    )


def downgrade() -> None:
    """Downgrade schema."""
