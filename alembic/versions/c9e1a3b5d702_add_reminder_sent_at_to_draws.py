"""add_reminder_sent_at_to_draws

Revision ID: c9e1a3b5d702
Revises: b4d2f8a6c911
Create Date: 2026-11-05 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9e1a3b5d702'
down_revision = 'b4d2f8a6c911'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('draws', sa.Column('reminder_sent_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('draws', 'reminder_sent_at')
