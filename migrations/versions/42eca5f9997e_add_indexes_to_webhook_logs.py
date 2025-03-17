"""add_indexes_to_webhook_logs

Revision ID: [auto-generated]
Revises: [auto-generated]
Create Date: [auto-generated]

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '[auto-generated]'
down_revision = '[auto-generated]'  # Keep these as they were generated
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