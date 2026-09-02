#!/bin/bash
# Tailscale Tray Manager - Uninstaller
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root (sudo ./uninstall.sh)${NC}"
    exit 1
fi

echo -e "${YELLOW}Uninstalling Tailscale Tray Manager...${NC}"

LOGIN_USER=${SUDO_USER:-$USER}

# Stop and disable service
su - "$LOGIN_USER" -c "systemctl --user stop tailscale-tray.service" 2>/dev/null || true
su - "$LOGIN_USER" -c "systemctl --user disable tailscale-tray.service" 2>/dev/null || true

# Remove files
rm -f /usr/local/bin/tailscale-tray.py
rm -f /usr/share/polkit-1/actions/com.tailscale-tray.policy
rm -f /etc/sudoers.d/tailscale-tray
rm -f /etc/systemd/user/tailscale-tray.service

systemctl daemon-reload

echo -e "${GREEN}Uninstall complete!${NC}"
echo -e "${YELLOW}Your config was kept at: ${NC}$(getent passwd "$LOGIN_USER" | cut -d: -f6)/.config/tailscale-tray/"
echo -e "${YELLOW}Remove it manually if you no longer need it.${NC}"
