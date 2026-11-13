"""add_reminder_email_sent_at_to_draws

Revision ID: f6c2e8a4b351
Revises: e5a9c1d7f230
Create Date: 2026-11-13 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6c2e8a4b351'
down_revision = 'e5a9c1d7f230'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('draws', sa.Column('reminder_email_sent_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('draws', 'reminder_email_sent_at')
