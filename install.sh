#!/bin/bash
# Tailscale Tray Manager - Multi-platform installer
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root (sudo ./install.sh)${NC}"
    exit 1
fi

DISTRO=$(cat /etc/os-release | grep ^ID= | cut -d= -f2 | tr -d '"')
DISTRO_ID=$(cat /etc/os-release | grep ^ID_LIKE= | cut -d= -f2 | tr -d '"')

echo -e "${YELLOW}=== Tailscale Tray Manager Installer ===${NC}"
echo -e "Detected distribution: ${GREEN}$DISTRO${NC}"

# Helper: check if a command exists
have() { command -v "$1" >/dev/null 2>&1; }
pkgmgr() {
    case "$1" in
        fedora|rhel|centos|rocky|almalinux)
            echo "dnf";;
        ubuntu|debian|linuxmint|pop)
            echo "apt";;
        arch|manjaro|endeavouros)
            echo "pacman";;
        opensuse*|suse)
            echo "zypper";;
        *) echo "unknown";;
    esac
}

install_deps() {
    echo -e "${GREEN}[1/6] Installing GUI dependencies...${NC}"
    local pm
    pm=$(pkgmgr "$1")
    case "$pm" in
        dnf)
            dnf install -y python3-gobject gtk3 libayatana-appindicator-gtk3 libnotify 2>/dev/null || \
            dnf install -y python3-gobject gtk3 libnotify 2>/dev/null || true
            ;;
        apt)
            apt-get update -qq 2>/dev/null || true
            DEBIAN_FRONTEND=noninteractive apt-get install -y \
                python3-gi gir1.2-gtk-3.0 gir1.2-appindicator3-0.1 gir1.2-notify-0.7 2>/dev/null || \
            DEBIAN_FRONTEND=noninteractive apt-get install -y \
                python3-gi gir1.2-gtk-3.0 libnotify-bin 2>/dev/null || true
            ;;
        pacman)
            pacman -Sy --noconfirm python-gobject gtk3 libayatana-appindicator libnotify 2>/dev/null || true
            ;;
        zypper)
            zypper --non-interactive install python3-gobject gtk3 typelib-1_0-AppIndicator3-0_1 typelib-1_0-Notify-0_7 2>/dev/null || true
            ;;
        *)
            echo -e "${YELLOW}Unsupported package manager. Install manually:${NC}"
            echo "  python3-gobject (python3-gi)"
            echo "  gtk3"
            echo "  AppIndicator3"
            echo "  libnotify / Notification support"
            ;;
    esac
}

install_tailscale() {
    echo -e "${GREEN}[1b/6] Checking Tailscale...${NC}"
    if ! have tailscale; then
        echo -e "${YELLOW}Tailscale is not installed!${NC}"
        read -p "Do you want to install Tailscale now? [y/N] " -r
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            local pm
            pm=$(pkgmgr "$DISTRO")
            case "$pm" in
                dnf)
                    dnf config-manager --add-repo https://pkgs.tailscale.com/stable/fedora/tailscale.repo 2>/dev/null || true
                    dnf install -y tailscale || true
                    ;;
                apt)
                    curl -fsSL https://tailscale.com/install.sh | sh || true
                    ;;
                pacman)
                    pacman -Sy --noconfirm tailscale || true
                    ;;
                zypper)
                    zypper --non-interactive addrepo -g https://pkgs.tailscale.com/stable/opensuse/tailscale.repo 2>/dev/null || true
                    zypper --non-interactive install tailscale || true
                    ;;
                *)
                    echo -e "${YELLOW}Please install Tailscale manually: https://tailscale.com/download${NC}"
                    ;;
            esac
        else
            echo -e "${YELLOW}Continuing without Tailscale (app will still install but needs tailscale).${NC}"
        fi
    else
        echo -e "${GREEN}Tailscale already installed.${NC}"
    fi

    # Make sure tailscaled is running
    if have tailscaled; then
        systemctl enable tailscaled 2>/dev/null || true
        systemctl start tailscaled 2>/dev/null || true
    fi
}

# 1. Install dependencies
install_deps "$DISTRO"

# 1b. Install/verify tailscale
install_tailscale

# 2. Install the tray application
echo -e "${GREEN}[2/6] Installing tray application...${NC}"
install -m 755 tailscale-tray.py /usr/local/bin/tailscale-tray.py

# 3. Install polkit policy
echo -e "${GREEN}[3/6] Installing polkit policy...${NC}"
install -m 644 com.tailscale-tray.policy /usr/share/polkit-1/actions/ 2>/dev/null || true

# 4. Install passwordless sudoers rule (auto-detect admin group, any distro)
LOGIN_USER=${SUDO_USER:-$USER}
echo -e "${GREEN}[4/6] Installing passwordless sudoers rule...${NC}"

# Find which admin group(s) exist on this system (wheel, sudo, admin)
ADMIN_GROUPS=""
for g in wheel sudo admin; do
    if getent group "$g" >/dev/null 2>&1; then
        ADMIN_GROUPS="$ADMIN_GROUPS %$g"
    fi
done
# Always at least include wheel and sudo in the rule so it works everywhere
if [ -z "$(echo "$ADMIN_GROUPS" | tr -d ' ')" ]; then
    ADMIN_GROUPS=" %wheel %sudo"
fi

# build the sudoers content with detected groups (no "NOPASSWD" markers stripped)
SUDOERS_CONTENT="# Created by Tailscale Tray installer $(date)
# Allows running 'tailscale set' without a password for tray app.
${ADMIN_GROUPS# } ALL=(root) NOPASSWD: /usr/bin/tailscale set *, /usr/local/bin/tailscale set *, /bin/tailscale set *
"
printf '%s' "$SUDOERS_CONTENT" > /etc/sudoers.d/tailscale-tray
chmod 440 /etc/sudoers.d/tailscale-tray
echo -e "  sudoers rule installed for groups:${YELLOW}$ADMIN_GROUPS${NC}"

# Ensure the installing user is in at least one admin group
USER_GROUPS=$(id -nG "$LOGIN_USER")
if ! echo "$USER_GROUPS" | grep -qwE 'wheel|sudo|admin'; then
    ADD_GROUP=""
    for g in wheel sudo admin; do
        if getent group "$g" >/dev/null 2>&1; then ADD_GROUP="$g"; break; fi
    done
    if [ -n "$ADD_GROUP" ]; then
        echo -e "${YELLOW}Adding user '$LOGIN_USER' to group '$ADD_GROUP'...${NC}"
        usermod -aG "$ADD_GROUP" "$LOGIN_USER"
        echo -e "${YELLOW}User added to '$ADD_GROUP'. They must LOG OUT and back in for this to take effect.${NC}"
    else
        echo -e "${YELLOW}Could not find an admin group to add user to. Manual sudo may be required.${NC}"
    fi
fi

# 5. Install systemd user service
echo -e "${GREEN}[5/6] Installing systemd service...${NC}"
install -m 644 tailscale-tray.service /etc/systemd/user/
systemctl daemon-reload

# 6. Setup user config
LOGIN_USER=${SUDO_USER:-$USER}
LOGIN_HOME=$(getent passwd "$LOGIN_USER" | cut -d: -f6)
echo -e "${GREEN}[6/6] Setting up config for user '$LOGIN_USER'...${NC}"

CONFIG_DIR="$LOGIN_HOME/.config/tailscale-tray"
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/config.conf" ]; then
    cp config.conf "$CONFIG_DIR/config.conf"
    chown -R "$LOGIN_USER":"$LOGIN_USER" "$CONFIG_DIR"
    echo -e "  Config created: ${GREEN}$CONFIG_DIR/config.conf${NC}"
else
    echo -e "  Config already exists (keeping it): ${GREEN}$CONFIG_DIR/config.conf${NC}"
fi

# Enable and start service (best-effort; needs user session bus)
echo
echo -e "${GREEN}Enabling and starting service for user '$LOGIN_USER'...${NC}"
if [ "$(id -u)" -eq 0 ] && [ -x "$(command -v loginctl)" ]; then
    # Detect the user's session and try enabling via their session bus
    SESSION_ID=$(loginctl list-sessions --no-legend 2>/dev/null | awk -v u="$LOGIN_USER" '$3==u {print $1; exit}')
    if [ -n "$SESSION_ID" ]; then
        XDG_RUNTIME_DIR="/run/user/$(id -u "$LOGIN_USER")"
        if [ -d "$XDG_RUNTIME_DIR" ]; then
            export XDG_RUNTIME_DIR
            su - "$LOGIN_USER" -c "systemctl --user enable tailscale-tray.service" 2>/dev/null \
                && su - "$LOGIN_USER" -c "systemctl --user restart tailscale-tray.service" 2>/dev/null \
                && ENABLED=1
        fi
    fi
fi
if [ -z "${ENABLED:-}" ]; then
    echo -e "${YELLOW}Could not auto-start the service from this non-graphical session.${NC}"
    echo -e "${YELLOW}As user '$LOGIN_USER', run these to finish setup:${NC}"
    echo -e "  ${GREEN}systemctl --user enable tailscale-tray.service${NC}"
    echo -e "  ${GREEN}systemctl --user restart tailscale-tray.service${NC}"
fi

echo
echo -e "${GREEN}=== Installation complete! ===${NC}"
echo
echo -e "Configure your exit node IP via the tray menu:"
echo -e "  ${YELLOW}Right-click tray icon -> Settings...${NC}"
echo -e "  or edit: ${YELLOW}nano $CONFIG_DIR/config.conf${NC}"
echo
echo -e "Manage the service:"
echo -e "  Status:  ${YELLOW}systemctl --user status tailscale-tray.service${NC}"
echo -e "  Restart: ${YELLOW}systemctl --user restart tailscale-tray.service${NC}"
echo -e "  Stop:    ${YELLOW}systemctl --user stop tailscale-tray.service${NC}"
echo -e "  Logs:    ${YELLOW}tail -f $CONFIG_DIR/tailscale-tray.log${NC}"
