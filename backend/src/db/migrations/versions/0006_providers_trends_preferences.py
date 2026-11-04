"""providers, trends and preferences

Revision ID: 9b1f6e2c4d06
Revises: 7c2e9d41b8a3
Create Date: 2026-11-03 12:00:00.000000

019-gcp-azure-providers-trends (data-model §1–§5). Every schema change of the feature:

- `user_preferences`: one typed JSON row per user, deleted with the user (§1).
- `service_category_rules`: provider groupings → shared categories (§2); seeded by 0007.
- `sku_selections`: `pricing_term` CHECK widened with savings plans and commitments, and a
  nullable `provider_options` JSONB (§3).
- `collections.region` as varchar(64), for GCP and Azure location names (§4). 0003 created it
  without a length; every existing value fits.
- `data_connectors.arrow_style` and `arrow_reversed`, and `connector_branches` (§5).

Plain SQL and Alembic operations only, in the style of 0004/0005: the app ORM is never imported.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '9b1f6e2c4d06'
down_revision: Union[str, Sequence[str], None] = '7c2e9d41b8a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_TERMS = "('on_demand', 'reserved_1yr', 'reserved_3yr')"
_NEW_TERMS = (
    "('on_demand', 'reserved_1yr', 'reserved_3yr', 'savings_plan_1yr', 'savings_plan_3yr', "
    "'commitment_1yr', 'commitment_3yr')"
)
_ARROW_STYLES = "('none', 'one_way', 'two_way', 'one_to_many', 'many_to_one')"
_CATEGORIES = "('compute', 'storage', 'database', 'networking')"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'user_preferences',
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'),
                  primary_key=True),
        sa.Column('data', postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column('schema_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )

    op.create_table(
        'service_category_rules',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('provider', sa.String(20), nullable=False),
        sa.Column('match_field', sa.String(40), nullable=False),
        sa.Column('match_value', sa.String(255), nullable=False),
        sa.Column('category', sa.String(20), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.CheckConstraint("provider IN ('aws', 'gcp', 'azure')",
                           name='ck_service_category_rule_provider'),
        sa.CheckConstraint(f"category IN {_CATEGORIES}", name='ck_service_category_rule_category'),
        sa.UniqueConstraint('provider', 'match_field', 'match_value',
                            name='uq_service_category_rule_match'),
    )

    op.drop_constraint('ck_sku_selection_pricing_term', 'sku_selections', type_='check')
    op.create_check_constraint('ck_sku_selection_pricing_term', 'sku_selections',
                               f"pricing_term IN {_NEW_TERMS}")
    op.add_column('sku_selections', sa.Column('provider_options', postgresql.JSONB(),
                                              nullable=True))

    op.alter_column('collections', 'region', type_=sa.String(64), existing_nullable=False)

    op.add_column('data_connectors', sa.Column('arrow_style', sa.String(20), nullable=False,
                                               server_default='none'))
    op.add_column('data_connectors', sa.Column('arrow_reversed', sa.Boolean(), nullable=False,
                                               server_default=sa.false()))
    op.create_check_constraint('ck_connector_arrow_style', 'data_connectors',
                               f"arrow_style IN {_ARROW_STYLES}")

    op.create_table(
        'connector_branches',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('connector_id', sa.Uuid(),
                  sa.ForeignKey('data_connectors.id', ondelete='CASCADE'), nullable=False,
                  index=True),
        sa.Column('collection_id', sa.Uuid(), sa.ForeignKey('collections.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('connector_id', 'collection_id', name='uq_connector_branch'),
    )


def downgrade() -> None:
    """Downgrade schema. Rows using the new price types must be removed first: the narrowed
    CHECK refuses them, so the downgrade fails rather than losing them silently."""
    op.drop_table('connector_branches')
    op.drop_constraint('ck_connector_arrow_style', 'data_connectors', type_='check')
    op.drop_column('data_connectors', 'arrow_reversed')
    op.drop_column('data_connectors', 'arrow_style')

    op.alter_column('collections', 'region', type_=sa.String(), existing_nullable=False)

    op.drop_column('sku_selections', 'provider_options')
    op.drop_constraint('ck_sku_selection_pricing_term', 'sku_selections', type_='check')
    op.create_check_constraint('ck_sku_selection_pricing_term', 'sku_selections',
                               f"pricing_term IN {_OLD_TERMS}")

    op.drop_table('service_category_rules')
    op.drop_table('user_preferences')
