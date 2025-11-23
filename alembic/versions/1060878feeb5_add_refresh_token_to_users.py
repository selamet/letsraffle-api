"""add_refresh_token_to_users

Revision ID: 1060878feeb5
Revises: f72ae675548e
Create Date: 2025-11-23 15:44:03.694908

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1060878feeb5'
down_revision = 'f72ae675548e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This migration is intentionally empty
    # Refresh tokens are not stored in database, they are stateless JWT tokens
    pass


def downgrade() -> None:
    # This migration is intentionally empty
    pass
