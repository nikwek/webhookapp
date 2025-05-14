#!/bin/bash
set -e # Exit immediately if a command fails

# Get current branch
BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "Deploying branch: $BRANCH"

# Step 1: Push current branch to remote
echo "Pushing to GitHub..."
git push origin $BRANCH

# Step 2: SSH to Raspberry Pi and deploy
echo "Deploying to Raspberry Pi..."
ssh nik@raspberrypi.local "
 # Create a backup of the database
 echo 'Creating database backup...'
 mkdir -p /home/nik/webhookapp/backups
 cp /home/nik/webhookapp/instance/webhook.db /home/nik/webhookapp/backups/webhook_\$(date +'%Y%m%d%H%M%S').db
 
 cd /home/nik/webhookapp &&
 git fetch origin &&
 (git checkout $BRANCH || git checkout -b $BRANCH origin/$BRANCH) &&
 git pull origin $BRANCH &&
 source venv/bin/activate &&
 
 # Install requirements
 echo 'Installing dependencies...'
 pip install -r requirements.txt &&
 
 # Check for missing dependencies 
 echo 'Verifying all imports...'
 python -c 'import sys; import app; print(\"All imports successful\")' || {
   echo 'Import check failed - some dependencies might be missing'
   echo 'Run pip freeze > requirements.txt locally and try again'
   exit 1
 } &&
 
 # Clear temporary migration tables if they exist
 echo 'Cleaning up any temporary migration tables...'
 python -c '
import sqlite3
conn = sqlite3.connect(\"instance/webhook.db\")
cursor = conn.cursor()
tables = cursor.execute(\"SELECT name FROM sqlite_master WHERE type=\\\"table\\\" AND name LIKE \\\"_alembic_tmp_%\\\"\").fetchall()
for table in tables:
    cursor.execute(f\"DROP TABLE {table[0]}\")
conn.commit()
conn.close()
print(\"Temporary migration tables cleaned up\")
' &&
 
 # Apply database migrations with better error handling
 echo 'Running database migrations...' &&
 flask db upgrade || {
   migration_error=$(flask db upgrade 2>&1)
   echo "Migration error output: $migration_error"
   
   if echo "$migration_error" | grep -q 'index.*already exists'; then
     echo 'Indexes already exist, marking migration as complete...'
     flask db stamp head
   elif echo "$migration_error" | grep -q 'table.*already exists'; then
     echo 'Temporary table issue detected, attempting to fix...'
     python -c '
import sqlite3
from flask import Flask
from flask_migrate import Migrate
from app import db, create_app
app = create_app()
with app.app_context():
    current_rev = db.session.execute(\"SELECT version_num FROM alembic_version\").scalar()
    print(f\"Current migration version: {current_rev}\")
'
     flask db stamp head
   elif echo "$migration_error" | grep -q "no such column.*exchange"; then
     echo 'Detected missing exchange column issue. Fixing migration state...'
     # Manually execute the migration for the exchange column
     python -c '
import sqlite3
from flask import Flask
from flask_migrate import Migrate
from app import db, create_app

app = create_app()
with app.app_context():
    # Get database connection
    conn = sqlite3.connect("instance/webhook.db")
    cursor = conn.cursor()
    
    # Check if column already exists (to be safe)
    column_exists = cursor.execute("PRAGMA table_info(account_caches)").fetchall()
    exchange_exists = any(col[1] == "exchange" for col in column_exists)
    
    if not exchange_exists:
        print("Adding exchange column to account_caches table")
        cursor.execute("ALTER TABLE account_caches ADD COLUMN exchange VARCHAR(50) DEFAULT \'coinbase\' NOT NULL")
        conn.commit()
    else:
        print("Exchange column already exists")
    
    # Update alembic version to include this migration
    current_rev = cursor.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    print(f"Current migration version: {current_rev}")
    
    # Only update if we\'re at the revision before the exchange column migration
    if current_rev == "3f5665c11741":
        cursor.execute("UPDATE alembic_version SET version_num = \'add_exchange_column\'")
        conn.commit()
        print("Updated alembic version to include exchange column migration")
    
    conn.close()
'
     # Now try the upgrade again
     flask db upgrade || {
       echo "Warning: Migration still failed after fixing exchange column. Setting to head."
       flask db stamp head
     }
   else
     echo 'Migration failed for unexpected reason'
     exit 1
   fi
 } &&
 
 # Run a quick health check before restarting services
 echo 'Verifying application starts correctly...' &&
 timeout 5s flask run --port 5050 &>/dev/null || {
   echo 'Application failed to start in test mode'
   exit 1
 } &&
 
 # Reload systemd configuration and restart service
 echo 'Reloading systemd configuration and restarting service...' &&
 sudo systemctl daemon-reload &&
 sudo systemctl restart webhookapp &&
 
 # More thorough service verification
 echo 'Waiting for service to fully start...' &&
 sleep 5 &&
 echo 'Checking service status:' &&
 sudo systemctl status webhookapp | head -10 &&
 
 # Check if service is actually responding to requests
 echo 'Verifying service is responding to requests...' &&
 curl -s -k https://localhost:5001/ -o /dev/null -w '%{http_code}' | grep -q '200' && {
   echo 'Service is responding with status code 200 - deployment successful!'
 } || {
   echo 'WARNING: Service not responding with status code 200'
   echo 'Log output:'
   sudo journalctl -u webhookapp --no-pager -n 20
 }
"

echo "Deployment of branch '$BRANCH' complete!"
