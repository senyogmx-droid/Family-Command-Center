#!/bin/bash
# =====================================================================
# Family Command Center - Bash/WSL-to-Linux Deployment Script
# =====================================================================

SERVER_IP="192.168.1.211"
SSH_USER="senyog"
TAR_FILE="deploy.tar"

SSH_TARGET="${SSH_USER}@${SERVER_IP}"

echo "========================================================"
echo "  Family Command Center - Fast Deployment to Linux (Bash)  "
echo "========================================================"
echo ""

# Package the files (excluding user databases, custom local caches, etc.)
echo "📦 Packaging deployment files..."
if [ -f "$TAR_FILE" ]; then
    rm "$TAR_FILE"
fi

tar --exclude="database.db" --exclude="photos.json" --exclude="calendar.json" --exclude="static/photos" --exclude="static/media" -cf "$TAR_FILE" server.py static
if [ $? -ne 0 ]; then
    echo "❌ Failed to package files."
    exit 1
fi
echo "✅ Bundle packaged successfully!"
echo ""

# Upload file via scp to the remote user's home directory (always exists)
echo "🚀 Uploading package to $SSH_TARGET..."
scp "$TAR_FILE" "$SSH_TARGET:"
if [ $? -ne 0 ]; then
    echo "❌ Failed to upload package."
    rm -f "$TAR_FILE"
    exit 1
fi
echo "✅ Package transferred successfully!"
echo ""

# Extract remote files and restart service
echo "🔧 Extracting files and restarting systemd service on Linux..."

# The remote command queries the systemd service to dynamically find the correct WorkingDirectory
REMOTE_CMD='DIR=$(systemctl show family-dashboard --property=WorkingDirectory | cut -d= -f2); '
REMOTE_CMD+='if [ -z "$DIR" ] || [ "$DIR" = "[not set]" ] || [ "$DIR" = "" ]; then DIR="/home/senyog/family-command-center"; fi; '
REMOTE_CMD+='echo -e "\n🎯 Target folder: $DIR"; '
REMOTE_CMD+='mkdir -p "$DIR" && '
REMOTE_CMD+='mv ~/deploy.tar "$DIR/" && '
REMOTE_CMD+='cd "$DIR" && '
REMOTE_CMD+='tar -xf deploy.tar && '
REMOTE_CMD+='rm deploy.tar && '
REMOTE_CMD+='echo "✨ Restarting family-dashboard service..." && '
REMOTE_CMD+='sudo systemctl restart family-dashboard'

# Allocate pseudo-terminal (-t) so that sudo can prompt for the password securely
ssh -t "$SSH_TARGET" "$REMOTE_CMD"
if [ $? -ne 0 ]; then
    echo "❌ Remote commands failed."
    rm -f "$TAR_FILE"
    exit 1
fi

# Clean up local temporary file
rm -f "$TAR_FILE"

echo ""
echo "========================================================"
echo "🎉 DEPLOYMENT COMPLETE! YOUR CHANGES ARE LIVE (v2.3.4)!"
echo "========================================================"
echo ""
read -p "Press enter to close..."
