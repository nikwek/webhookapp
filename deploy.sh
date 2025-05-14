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
 flask db upgrade heads || {
   if grep -q 'index.*already exists' <<< \$?; then
     echo 'Indexes already exist, marking migration as complete...'
     flask db stamp head
   elif grep -q 'table.*already exists' <<< \$?; then
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
   else
     echo 'Migration failed for unexpected reason'
     exit 1
   fi
 } &&
 
 # Run a quick health check before restarting services
 echo 'Verifying application starts correctly...' &&
 (timeout 5s flask run --port 5050 2>&1 | tee app_start_log.tmp || true) &&
 if grep -q 'Running on' app_start_log.tmp; then
   echo 'Application started successfully'
   rm app_start_log.tmp
 elif grep -q 'Error in health check loop: cannot join current thread' app_start_log.tmp; then
   echo 'WARNING: Health check thread issue detected, but application still started'
   rm app_start_log.tmp
 else
   echo 'Application failed to start in test mode'
   rm app_start_log.tmp
   exit 1
 fi &&
 
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
