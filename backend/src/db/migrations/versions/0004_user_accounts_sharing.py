"""user accounts sharing

Revision ID: db1df84f4a73
Revises: a5f7c446f131
Create Date: 2026-09-18 12:00:00.000000

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'db1df84f4a73'
down_revision: Union[str, Sequence[str], None] = 'a5f7c446f131'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The seeded default Admin account (012-user-accounts-sharing, spec FR-012, research.md §6) —
# a literal `pbkdf2_sha256$...` hash of the doc's stated default password "admin123", computed
# at migration-authoring time via `src.services.auth_service.hash_password("admin123")`.
_DEFAULT_ADMIN_PASSWORD_HASH = (
    "pbkdf2_sha256$260000$705e534cc2a2551cd8f603e6531dee48"
    "$c6e5f21007efd24a4552c2240770ca3ad9fad05d2fcfa7433cbca2aad79a3dc4"
)


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('username', sa.String(), nullable=True))
    op.add_column('users', sa.Column('password_hash', sa.String(), nullable=True))
    op.add_column(
        'users',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        'users',
        sa.Column('is_admin', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'users',
        sa.Column('is_default_admin', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        'ix_users_username_unique',
        'users',
        ['username'],
        unique=True,
        postgresql_where=sa.text('username IS NOT NULL'),
    )
    op.add_column(
        'architectures',
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # No server-side UUID default exists in this schema (every ORM id is client-generated via
    # `uuid.uuid4()`, orm.py's `_uuid_pk()`) — generate the seed row's id here the same way,
    # rather than relying on a Postgres extension (e.g. pgcrypto) this repo doesn't enable.
    op.execute(
        sa.text(
            "INSERT INTO users (id, username, password_hash, is_active, is_admin, "
            "is_default_admin) "
            "SELECT :id, 'Admin', :hash, true, true, true "
            "WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'Admin')"
        ).bindparams(id=uuid.uuid4(), hash=_DEFAULT_ADMIN_PASSWORD_HASH)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('architectures', 'is_public')
    op.drop_index('ix_users_username_unique', table_name='users')
    op.drop_column('users', 'is_default_admin')
    op.drop_column('users', 'is_admin')
    op.drop_column('users', 'is_active')
    op.drop_column('users', 'password_hash')
    op.drop_column('users', 'username')
