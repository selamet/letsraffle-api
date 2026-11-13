"""add_notification_bookkeeping_to_draws

Revision ID: a1d4c7e9b602
Revises: f6c2e8a4b351
Create Date: 2026-11-13 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1d4c7e9b602'
down_revision = 'f6c2e8a4b351'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('draws', sa.Column('join_push_sent_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('draws', sa.Column('not_run_notified_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('draws', 'not_run_notified_at')
    op.drop_column('draws', 'join_push_sent_at')
