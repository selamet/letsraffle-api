"""add_apple_sign_in_to_users

Revision ID: a7c3e9d41b20
Revises: 1060878feeb5
Create Date: 2026-11-05 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7c3e9d41b20'
down_revision = '1060878feeb5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('apple_sub', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_users_apple_sub'), 'users', ['apple_sub'], unique=True)
    op.alter_column('users', 'password', existing_type=sa.String(length=255), nullable=True)


def downgrade() -> None:
    # Apple-only accounts have no password; they cannot survive the downgrade.
    op.execute("DELETE FROM users WHERE password IS NULL")
    op.alter_column('users', 'password', existing_type=sa.String(length=255), nullable=False)
    op.drop_index(op.f('ix_users_apple_sub'), table_name='users')
    op.drop_column('users', 'apple_sub')
