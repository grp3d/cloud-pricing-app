"""service mappings

Revision ID: c4f2a9d8e1b3
Revises: b81d5e0c2a47
Create Date: 2026-11-19 12:00:00.000000

026-agent-cross-cloud-translation (data-model.md §1–§2):

- `service_mappings`: the seed mappings generated from 022's rules
  (`src/db/seed/service_mappings_{gcp,azure}.json`), inserted once. Linking data by stable
  identifiers (product keys, a service code, 022's SKU as a first try), never labels or prices
  (Principle II).
- `agent_proposals`: kind `translate`, and a `translation` record of what was shown.

Plain SQL only (no ORM import), like the other revisions.
"""
import json
import uuid
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4f2a9d8e1b3'
down_revision: str | Sequence[str] | None = 'b81d5e0c2a47'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_DIR = Path(__file__).resolve().parents[2] / "seed"
PROVIDERS = ("gcp", "azure")


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE TABLE service_mappings (
          id uuid PRIMARY KEY,
          version integer NOT NULL,
          source_provider varchar(10) NOT NULL,
          source_key varchar(400) NOT NULL,
          target_provider varchar(10) NOT NULL,
          alternative smallint NOT NULL,
          part smallint NOT NULL,
          target_key varchar(400),
          target_service_code varchar(100),
          target_sku varchar(200),
          target_options jsonb,
          quantity_factor numeric,
          note text,
          omit_reason text,
          origin varchar(20) NOT NULL,
          CONSTRAINT uq_service_mapping UNIQUE
            (version, source_provider, source_key, target_provider, alternative, part),
          CONSTRAINT ck_service_mapping_target
            CHECK ((target_key IS NULL) <> (omit_reason IS NULL)),
          CONSTRAINT ck_service_mapping_providers CHECK (source_provider <> target_provider)
        )
        """
    )
    op.execute("CREATE INDEX ix_service_mappings_source ON service_mappings "
               "(source_provider, source_key, target_provider)")
    insert = sa.text(
        "INSERT INTO service_mappings (id, version, source_provider, source_key, "
        "target_provider, alternative, part, target_key, target_service_code, target_sku, "
        "target_options, quantity_factor, note, omit_reason, origin) VALUES (:id, :version, "
        ":source_provider, :source_key, :target_provider, :alternative, :part, :target_key, "
        ":target_service_code, :target_sku, CAST(:target_options AS jsonb), :quantity_factor, "
        ":note, :omit_reason, 'seed_022') ON CONFLICT ON CONSTRAINT uq_service_mapping DO NOTHING"
    )
    bind = op.get_bind()
    for provider in PROVIDERS:
        seed = json.loads((SEED_DIR / f"service_mappings_{provider}.json").read_text())
        for row in seed["mappings"]:
            options = row["target_options"]
            bind.execute(insert, {
                **row, "id": uuid.uuid4(), "version": seed["version"],
                "source_provider": seed["source_provider"],
                "target_provider": seed["target_provider"],
                "target_options": None if options is None else json.dumps(options),
            })
    op.execute("ALTER TABLE agent_proposals DROP CONSTRAINT ck_agent_proposal_kind")
    op.execute("ALTER TABLE agent_proposals ADD CONSTRAINT ck_agent_proposal_kind "
               "CHECK (kind IN ('change', 'create', 'import', 'translate'))")
    op.execute("ALTER TABLE agent_proposals ADD COLUMN translation jsonb")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM agent_proposals WHERE kind = 'translate'")
    op.execute("ALTER TABLE agent_proposals DROP COLUMN translation")
    op.execute("ALTER TABLE agent_proposals DROP CONSTRAINT ck_agent_proposal_kind")
    op.execute("ALTER TABLE agent_proposals ADD CONSTRAINT ck_agent_proposal_kind "
               "CHECK (kind IN ('change', 'create', 'import'))")
    op.execute("DROP TABLE service_mappings")
