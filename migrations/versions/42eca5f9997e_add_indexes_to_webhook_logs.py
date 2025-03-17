"""add_indexes_to_webhook_logs

Revision ID: 42eca5f9997e
Revises: 3f5665c11741
Create Date: 2025-03-17 09:21:23.168053

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '42eca5f9997e'
down_revision = '3f5665c11741'
branch_labels = None
depends_on = None


def upgrade():
    # Add indexes to webhook_logs table
    op.create_index(op.f('ix_webhook_logs_automation_id'), 'webhook_logs', ['automation_id'], unique=False)
    op.create_index(op.f('ix_webhook_logs_timestamp'), 'webhook_logs', ['timestamp'], unique=False)

def downgrade():
    # Remove indexes from webhook_logs table
    op.drop_index(op.f('ix_webhook_logs_timestamp'), table_name='webhook_logs')
    op.drop_index(op.f('ix_webhook_logs_automation_id'), table_name='webhook_logs')