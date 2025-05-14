"""Add exchange column to account_caches table

Revision ID: add_exchange_column
Revises: 3f5665c11741
Create Date: 2025-05-13 12:01:01.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_exchange_column'
down_revision = '3f5665c11741'
branch_labels = None
depends_on = None


def upgrade():
    # Add exchange column to account_caches table with default value 'coinbase'
    with op.batch_alter_table('account_caches') as batch_op:
        batch_op.add_column(sa.Column('exchange', sa.String(50), nullable=True, server_default='coinbase'))
        
    # Update existing records to have exchange='coinbase'
    op.execute("UPDATE account_caches SET exchange = 'coinbase'")
    
    # Make exchange column not nullable after setting default values
    with op.batch_alter_table('account_caches') as batch_op:
        batch_op.alter_column('exchange', nullable=False, existing_type=sa.String(50), server_default='coinbase')


def downgrade():
    # Remove exchange column
    with op.batch_alter_table('account_caches') as batch_op:
        batch_op.drop_column('exchange')
