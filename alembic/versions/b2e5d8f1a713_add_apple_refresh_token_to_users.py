"""add_apple_refresh_token_to_users

Revision ID: b2e5d8f1a713
Revises: a1d4c7e9b602
Create Date: 2026-11-13 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2e5d8f1a713'
down_revision = 'a1d4c7e9b602'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('apple_refresh_token', sa.String(length=1024), nullable=True))
    op.add_column('users', sa.Column('apple_client_id', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'apple_client_id')
    op.drop_column('users', 'apple_refresh_token')
