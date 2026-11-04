"""service category seed

Revision ID: 4d8a2f7c9e07
Revises: 9b1f6e2c4d06
Create Date: 2026-11-04 12:00:00.000000

019-gcp-azure-providers-trends (data-model §2, research R9): seeds `service_category_rules` from
`src/db/seed/service_categories.json`, idempotently, like 0005's standard architectures. A rule
already present (same provider, field and value) is left as it is, so a later edit survives a
re-run. Plain SQL only: the app ORM is never imported.
"""
import json
import uuid
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4d8a2f7c9e07'
down_revision: Union[str, Sequence[str], None] = '9b1f6e2c4d06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEED_PATH = Path(__file__).resolve().parents[2] / "seed" / "service_categories.json"


def _rules() -> list[dict]:
    return json.loads(SEED_PATH.read_text())["rules"]


def upgrade() -> None:
    """Upgrade schema."""
    insert = sa.text(
        "INSERT INTO service_category_rules "
        "(id, provider, match_field, match_value, category, priority) "
        "VALUES (:id, :provider, :match_field, :match_value, :category, :priority) "
        "ON CONFLICT (provider, match_field, match_value) DO NOTHING"
    )
    bind = op.get_bind()
    for rule in _rules():
        bind.execute(insert, {"id": uuid.uuid4(), **rule})


def downgrade() -> None:
    """Downgrade schema: remove the seeded rules (matched by provider, field and value)."""
    delete = sa.text(
        "DELETE FROM service_category_rules WHERE provider = :provider "
        "AND match_field = :match_field AND match_value = :match_value"
    )
    bind = op.get_bind()
    for rule in _rules():
        bind.execute(delete, {k: rule[k] for k in ("provider", "match_field", "match_value")})
