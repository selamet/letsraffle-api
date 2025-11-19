"""add_language_to_draws

Revision ID: f72ae675548e
Revises: 60e0d1a9a1e2
Create Date: 2025-11-19 22:44:44.384192

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f72ae675548e'
down_revision = '60e0d1a9a1e2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add language column to draws table with default value 'TR'
    op.add_column('draws', sa.Column('language', sa.String(length=2), nullable=False, server_default='TR'))


def downgrade() -> None:
    # Remove language column from draws table
    op.drop_column('draws', 'language')
