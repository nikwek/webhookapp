#!/bin/bash

# Get current branch
CURRENT_BRANCH=$(git branch --show-current)
echo "Deploying branch: $CURRENT_BRANCH"

# First push the current branch to remote to ensure it exists
echo "Pushing current branch to remote repository..."
git push -u origin $CURRENT_BRANCH

# SSH into Pi and deploy changes
ssh nik@raspberrypi.local "cd ~/webhookapp && \
                          git fetch --all && \
                          git checkout $CURRENT_BRANCH || git checkout -b $CURRENT_BRANCH --track origin/$CURRENT_BRANCH && \
                          git pull origin $CURRENT_BRANCH && \
                          echo 'Stopping webhookapp service...' && \
                          sudo systemctl stop webhookapp && \
                          echo 'Ensuring all gunicorn processes are terminated...' && \
                          sudo pkill -f gunicorn || true && \
                          sleep 2 && \
                          echo 'Starting webhookapp service...' && \
                          sudo systemctl start webhookapp && \
                          echo 'Checking service status:' && \
                          sudo systemctl status webhookapp --no-pager"

echo "Deployment of branch '$CURRENT_BRANCH' complete!"