"""add oauth credentials table

Revision ID: a495c2e5da7e
Revises: 101c1366fcce
Create Date: 2025-02-17 16:46:34.443097

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a495c2e5da7e'
down_revision = '101c1366fcce'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('oauth_credentials',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(length=50), nullable=False),
    sa.Column('access_token', sa.String(length=500), nullable=False),
    sa.Column('refresh_token', sa.String(length=500), nullable=True),
    sa.Column('expires_at', sa.DateTime(), nullable=True),
    sa.Column('scope', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('exchange_credentials', schema=None) as batch_op:
        batch_op.add_column(sa.Column('portfolio_id', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('portfolio_name', sa.String(length=100), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('exchange_credentials', schema=None) as batch_op:
        batch_op.drop_column('portfolio_name')
        batch_op.drop_column('portfolio_id')

    op.drop_table('oauth_credentials')
    # ### end Alembic commands ###
