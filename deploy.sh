#!/bin/bash

set -e  # Exit immediately if a command fails

# Get current branch
BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "Deploying branch: $BRANCH"

# Step 1: Push current branch to remote
echo "Pushing to GitHub..."
git push origin $BRANCH

# Step 2: SSH to Raspberry Pi and deploy
echo "Deploying to Raspberry Pi..."
ssh nik@raspberrypi.local "
  cd /home/nik/webhookapp &&
  git fetch origin &&
  (git checkout $BRANCH || git checkout -b $BRANCH origin/$BRANCH) &&
  git pull origin $BRANCH &&
  source venv/bin/activate &&
  pip install -r requirements.txt &&
  
  # Apply database migrations with error handling for existing indexes
  echo 'Running database migrations...' &&
  flask db upgrade || {
    if grep -q 'index.*already exists' <<< \$?; then
      echo 'Indexes already exist, marking migration as complete...'
      flask db stamp 42eca5f9997e
    else
      echo 'Migration failed for unexpected reason'
      exit 1
    fi
  } &&
  
  # Reload systemd configuration and restart service
  echo 'Reloading systemd configuration and restarting service...' &&
  sudo systemctl daemon-reload &&
  sudo systemctl restart webhookapp &&
  sleep 2 &&
  echo 'Checking service status:' &&
  sudo systemctl status webhookapp | head -10 &&
  
  # Check service response
  curl -s http://localhost:5001/ > /dev/null &&
  echo 'Service is responding to HTTP requests'
"

echo "Deployment of branch '$BRANCH' complete!"