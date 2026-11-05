"""add_devices

Revision ID: b4d2f8a6c911
Revises: a7c3e9d41b20
Create Date: 2026-11-05 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b4d2f8a6c911'
down_revision = 'a7c3e9d41b20'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'devices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=255), nullable=False),
        sa.Column('platform', sa.String(length=20), nullable=False),
        sa.Column('language', sa.String(length=2), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_devices_id'), 'devices', ['id'], unique=False)
    op.create_index(op.f('ix_devices_token'), 'devices', ['token'], unique=True)
    op.create_index(op.f('ix_devices_user_id'), 'devices', ['user_id'], unique=False)

    op.create_table(
        'device_participants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column('participant_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['participant_id'], ['participants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('device_id', 'participant_id', name='uq_device_participant'),
    )
    op.create_index(op.f('ix_device_participants_id'), 'device_participants', ['id'], unique=False)
    op.create_index(op.f('ix_device_participants_device_id'), 'device_participants', ['device_id'], unique=False)
    op.create_index(op.f('ix_device_participants_participant_id'), 'device_participants', ['participant_id'], unique=False)


def downgrade() -> None:
    op.drop_table('device_participants')
    op.drop_table('devices')
