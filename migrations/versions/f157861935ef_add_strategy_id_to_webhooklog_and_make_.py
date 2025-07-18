"""Add strategy_id to WebhookLog and make automation_id nullable

Revision ID: f157861935ef
Revises: 0f5e3bcbce32
Create Date: 2025-06-16 08:51:24.270004

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f157861935ef'
down_revision = '0f5e3bcbce32'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('webhook_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('strategy_id', sa.Integer(), nullable=True))
        batch_op.alter_column('automation_id',
               existing_type=sa.VARCHAR(length=36),
               nullable=True)
        batch_op.create_index(batch_op.f('ix_webhook_logs_strategy_id'), ['strategy_id'], unique=False)
        batch_op.create_foreign_key('fk_webhook_logs_strategy_id_trading_strategies', 'trading_strategies', ['strategy_id'], ['id'])

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('webhook_logs', schema=None) as batch_op:
        batch_op.drop_constraint('fk_webhook_logs_strategy_id_trading_strategies', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_webhook_logs_strategy_id'))
        batch_op.alter_column('automation_id',
               existing_type=sa.VARCHAR(length=36),
               nullable=False)
        batch_op.drop_column('strategy_id')

    # ### end Alembic commands ###
