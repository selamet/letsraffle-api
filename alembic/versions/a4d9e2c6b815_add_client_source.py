"""add_client_source

Revision ID: a4d9e2c6b815
Revises: b2e5d8f1a713
Create Date: 2026-11-25 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a4d9e2c6b815'
down_revision = 'b2e5d8f1a713'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('draws', sa.Column('source', sa.String(length=10), nullable=True))
    op.create_index(op.f('ix_draws_source'), 'draws', ['source'], unique=False)
    op.add_column('users', sa.Column('source', sa.String(length=10), nullable=True))
    op.add_column('participants', sa.Column('source', sa.String(length=10), nullable=True))


def downgrade() -> None:
    op.drop_column('participants', 'source')
    op.drop_column('users', 'source')
    op.drop_index(op.f('ix_draws_source'), table_name='draws')
    op.drop_column('draws', 'source')
