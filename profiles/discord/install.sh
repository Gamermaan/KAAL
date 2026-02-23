#!/bin/bash
# KAAL Discord C2 Profile Installer
# Matches Mythic's ./mythic-cli install github pattern

set -e

echo "🔌 Installing KAAL Discord C2 Profile..."

# Get installation directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
KAAL_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

echo "   > KAAL Root: $KAAL_ROOT"
echo "   > Profile Dir: $SCRIPT_DIR"

# Install Dependencies Locally (if not using Docker)
echo "📦 Installing Python dependencies..."
pip install -r "$SCRIPT_DIR/requirements.txt"

# Register Profile
echo "📝 Registering profile..."
# In a real scenario, this might update a database or registry file
# For now, we verify the config exists
if [ ! -f "$SCRIPT_DIR/config.yaml" ]; then
    echo "❌ config.yaml missing!"
    exit 1
fi

echo "✅ Discord C2 profile installed successfully!"
echo ""
echo "To start the profile:"
echo "   python profiles/discord/main.py"
echo ""
