#!/usr/bin/env python3
"""
Database migration script to add portfolio integration.
Run this script directly to apply the migration.
"""

import os
import sys
import sqlite3
from datetime import datetime

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

def run_migration():
    # Get database path from environment or use default
    db_path = os.environ.get('DATABASE_URL', 'instance/webhook.db')
    if db_path.startswith('sqlite:///'):
        db_path = db_path[10:]  # Remove sqlite:/// prefix if present
    
    print(f"Running migration on database: {db_path}")
    
    if not os.path.exists(db_path):
        print(f"Database file does not exist: {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Step 1: Create portfolios table
        print("Creating portfolios table...")
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS portfolios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id VARCHAR(100) NOT NULL,
            name VARCHAR(100) NOT NULL,
            user_id INTEGER NOT NULL,
            exchange VARCHAR(50) NOT NULL DEFAULT 'coinbase',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
        ''')
        
        # Step 2: Check if portfolio_id column exists in automations table
        print("Checking automations table...")
        cursor.execute("PRAGMA table_info(automations)")
        columns = cursor.fetchall()
        column_names = [column[1] for column in columns]
        
        if 'portfolio_id' not in column_names:
            print("Adding portfolio_id column to automations table...")
            cursor.execute('ALTER TABLE automations ADD COLUMN portfolio_id INTEGER REFERENCES portfolios(id)')
        else:
            print("portfolio_id column already exists in automations table")
        
        # Step 3: Check & modify exchange_credentials table
        print("Checking exchange_credentials table...")
        cursor.execute("PRAGMA table_info(exchange_credentials)")
        columns = cursor.fetchall()
        column_names = [column[1] for column in columns]
        
        if 'automation_id' not in column_names:
            print("Adding automation_id column to exchange_credentials table...")
            cursor.execute('ALTER TABLE exchange_credentials ADD COLUMN automation_id INTEGER REFERENCES automations(id)')
        else:
            print("automation_id column already exists in exchange_credentials table")
        
        if 'portfolio_id' not in column_names:
            print("Adding portfolio_id column to exchange_credentials table...")
            cursor.execute('ALTER TABLE exchange_credentials ADD COLUMN portfolio_id INTEGER REFERENCES portfolios(id)')
        else:
            print("portfolio_id column already exists in exchange_credentials table")
        
        if 'is_default' not in column_names:
            print("Adding is_default column to exchange_credentials table...")
            cursor.execute('ALTER TABLE exchange_credentials ADD COLUMN is_default BOOLEAN DEFAULT 0')
        else:
            print("is_default column already exists in exchange_credentials table")
        
        # Commit changes
        conn.commit()
        print("Migration completed successfully!")
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"Error during migration: {str(e)}")
        return False
        
    finally:
        conn.close()

if __name__ == "__main__":
    run_migration()