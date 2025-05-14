"""Merge branches

Revision ID: f2d64d5a8b11
Revises: update_invalid_credentials, add_exchange_column
Create Date: 2025-05-13 12:03:04.487121

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2d64d5a8b11'
down_revision = ('update_invalid_credentials', 'add_exchange_column')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
