#!/bin/bash
set -e

echo "=== Building 红果短剧下载器 for macOS ==="
# Clean
rm -rf dist build __pycache__

# Build GUI app
pyinstaller build_mac.spec --noconfirm

# Build CLI
pyinstaller build_cli_mac.spec --noconfirm

echo "=== Build complete ==="
echo "GUI: dist/红果短剧下载器.app"
echo "CLI: dist/hongguo-cli"
