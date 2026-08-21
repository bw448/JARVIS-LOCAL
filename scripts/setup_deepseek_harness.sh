#!/bin/bash
# Setup script for DeepSeek Harness integration with JARVIS

set -e

echo "=== DeepSeek Harness Integration Setup ==="
echo ""

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $python_version"

# Install DeepSeek Harness SDK
echo ""
echo "Installing DeepSeek Harness SDK..."
pip install deepseek-harness-sdk --quiet

# Verify installation
echo "Verifying installation..."
python3 -c "from deepseek_harness import DeepSeekHarness; print('✓ DeepSeek Harness SDK installed successfully')" || {
    echo "✗ Failed to install DeepSeek Harness SDK"
    exit 1
}

# Create default config directory
CONFIG_DIR="$HOME/.jarvis"
mkdir -p "$CONFIG_DIR"

# Create default DSH config if not exists
DSH_CONFIG="$CONFIG_DIR/dsh_config.json"
if [ ! -f "$DSH_CONFIG" ]; then
    cat > "$DSH_CONFIG" << 'CONFIGEOF'
{
    "dsh": {
        "enabled": false,
        "model": "deepseek-chat",
        "provider": "deepseek-official",
        "max_tokens": null,
        "runtime_bin": "",
        "session_root": "",
        "cordis_config": "",
        "base_url": "",
        "api_key": "",
        "request_timeout": 120.0,
        "shutdown_timeout": 2.0,
        "env_overrides": {}
    }
}
CONFIGEOF
    echo "✓ Created default DSH config at $DSH_CONFIG"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To enable DeepSeek Harness in JARVIS:"
echo "1. Edit your JARVIS settings"
echo "2. Set dsh.enabled = true"
echo "3. Configure your API key and model"
echo ""
echo "Example settings update:"
echo '  "dsh": {'
echo '    "enabled": true,'
echo '    "model": "deepseek-chat",'
echo '    "api_key": "your-api-key-here"'
echo '  }'
echo ""
echo "For offline usage, see docs/deepseek-harness-offline.md"
