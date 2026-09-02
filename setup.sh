#!/bin/bash
# Tailscale Tray — one-liner installer.
# Clones the repo and runs install.sh, so it works from any directory.
set -e

REPO_URL="https://github.com/sasm110313/tailscale-tray.git"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "=== Tailscale Tray Manager - Quick Install ==="

if ! command -v git >/dev/null 2>&1; then
    echo "git is required. Install it first, then re-run." >&2
    exit 1
fi

echo "Cloning repository..."
git clone --depth 1 "$REPO_URL" "$TMP_DIR/tailscale-tray"

cd "$TMP_DIR/tailscale-tray"
if [ "$(id -u)" -eq 0 ]; then
    ./install.sh
else
    sudo ./install.sh
fi
