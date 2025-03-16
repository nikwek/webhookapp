#!/bin/bash

# Get current branch
CURRENT_BRANCH=$(git branch --show-current)
echo "Deploying branch: $CURRENT_BRANCH"

# SSH into Pi and deploy changes
ssh nik@raspberrypi.local "cd ~/webhookapp && \
                          git fetch --all && \
                          git checkout $CURRENT_BRANCH && \
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