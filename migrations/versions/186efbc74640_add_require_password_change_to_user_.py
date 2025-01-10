"""Add require_password_change to User model

Revision ID: 186efbc74640
Revises: e406fe635c39
Create Date: 2025-01-10 10:51:59.970090

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '186efbc74640'
down_revision = 'e406fe635c39'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('require_password_change', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))
        batch_op.alter_column('password',
               existing_type=sa.VARCHAR(length=200),
               type_=sa.String(length=120),
               existing_nullable=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column('password',
               existing_type=sa.String(length=120),
               type_=sa.VARCHAR(length=200),
               existing_nullable=False)
        batch_op.drop_column('created_at')
        batch_op.drop_column('require_password_change')

    # ### end Alembic commands ###
