# migrations/versions/update_invalid_credentials.py

"""update invalid_credentials values in portfolios

revision = 'update_invalid_credentials'  # This is important
down_revision = '42eca5f9997e'  # Previous migration ID

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text, inspect


# revision identifiers, used by Alembic.
revision = 'update_invalid_credentials'
down_revision = '42eca5f9997e'
branch_labels = None
depends_on = None


def upgrade():
    # Get the database connection
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Check if invalid_credentials column exists
    columns = [col['name'] for col in inspector.get_columns('portfolios')]
    
    # If column doesn't exist, add it
    if 'invalid_credentials' not in columns:
        op.add_column('portfolios', sa.Column('invalid_credentials', sa.Boolean(), nullable=False, server_default='0'))
    
    # Update the values - set all to valid first
    conn.execute(text("""
    UPDATE portfolios SET invalid_credentials = 0
    """))
    
    # Set invalid_credentials to True for portfolios with no credentials
    conn.execute(text("""
    UPDATE portfolios SET invalid_credentials = 1
    WHERE id NOT IN (
        SELECT DISTINCT portfolio_id FROM exchange_credentials
        WHERE portfolio_id IS NOT NULL
    )
    """))


def downgrade():
    # No downgrade needed - we don't want to remove the column if it exists
    pass