#!/usr/bin/env bash
set -uo pipefail

APP_DIR="/opt/kebab_billing"
APP_USER="kebab"

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root." >&2
    exit 1
fi

echo "=> Updating KebabBilling..."
cd "$APP_DIR" || { echo "App directory not found at $APP_DIR" >&2; exit 1; }

echo "   Pulling latest code..."
git config --global --add safe.directory "$APP_DIR" 2>/dev/null || true
git pull --ff-only

echo "   Updating Python dependencies..."
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" -q

echo "   Restarting service..."
systemctl restart kebab-billing

echo "   Done! KebabBilling is now up to date."
