"""add_email_unsubscribes_and_campaign_emails

Revision ID: e5a9c1d7f230
Revises: d3f7b2c8e415
Create Date: 2026-11-13 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5a9c1d7f230'
down_revision = 'd3f7b2c8e415'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'email_unsubscribes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_email_unsubscribes_id'), 'email_unsubscribes', ['id'], unique=False)
    op.create_index(op.f('ix_email_unsubscribes_email'), 'email_unsubscribes', ['email'], unique=True)

    op.create_table(
        'campaign_emails',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('campaign', sa.String(length=64), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign', 'email', name='uq_campaign_email'),
    )
    op.create_index(op.f('ix_campaign_emails_id'), 'campaign_emails', ['id'], unique=False)
    op.create_index(op.f('ix_campaign_emails_campaign'), 'campaign_emails', ['campaign'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_campaign_emails_campaign'), table_name='campaign_emails')
    op.drop_index(op.f('ix_campaign_emails_id'), table_name='campaign_emails')
    op.drop_table('campaign_emails')
    op.drop_index(op.f('ix_email_unsubscribes_email'), table_name='email_unsubscribes')
    op.drop_index(op.f('ix_email_unsubscribes_id'), table_name='email_unsubscribes')
    op.drop_table('email_unsubscribes')
