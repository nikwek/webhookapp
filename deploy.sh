# deploy.sh
#!/bin/bash

# Push changes to GitHub
# git add .
# git commit -m "$1"
# git push origin main

# SSH into Pi and pull changes
ssh nik@raspberrypi.local "cd ~/webhookapp && git pull && sudo systemctl restart webhookapp"

echo "Deployment complete!"