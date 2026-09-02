# Tailscale Tray Manager

A lightweight, powerful system tray application for Linux to manage your **Tailscale VPN exit node** with auto-discovery, LAN access controls, and non-blocking background monitoring.

![Platform: Linux](https://img.shields.io/badge/platform-Linux-blue) ![Python](https://img.shields.io/badge/python-3.x-green)

---

## ✨ Features

- 🖥️ **Runs in System Tray**: Smooth integration with top panel / notification area across all Linux Desktop Environments (GNOME, KDE Plasma, XFCE, Cinnamon, MATE, etc.).
- 🌐 **Exit Node Auto-Discovery**: Automatically lists all available exit nodes in your tailnet with live online status indicators (🟢 Online / ⚪ Offline). Switch between exit nodes with a single click from the **Exit Nodes** submenu.
- ⚡ **One-Click Connect / Disconnect**: Quick toggle for your default exit node or custom IPs.
- 🛡️ **LAN Access Control**: Easily toggle local network access (`--exit-node-allow-lan-access`) directly from the menu or settings.
- 🚀 **Non-Blocking UI**: Asynchronous thread execution prevents GTK UI freezes during network operations.
- 🔄 **Periodic Background Status Polling**: Automatically checks status every 5 seconds without user intervention.
- 🎛️ **Graphical Settings Window**: Configure default exit node, auto-connect on boot, LAN access, and quit options.
- 🔔 **Desktop Notifications**: Real-time notifications for connections, disconnections, and status changes.
- 🔐 **Zero-Password Elevation**: Auto-detects sudoers rules and falls back smoothly to PolicyKit (`pkexec`) graphical auth prompt if needed.
- 🔄 **Auto-Start**: Systemd user service auto-starts on login.

---

## ⚠️ Prerequisites

1. **Tailscale installed** on this machine and logged in (`tailscale up`).
2. **An exit node** enabled on a remote server in your tailnet:
   ```bash
   sudo tailscale up --advertise-exit-node
   ```
   and approved in the [Tailscale Admin Console](https://login.tailscale.com/admin/dns).

---

## 🚀 Install

### Method 1 — Git clone (recommended)

```bash
git clone https://github.com/sasm110313/tailscale-tray
cd tailscale-tray
sudo ./install.sh
```

### Method 2 — Quick install (one-liner)

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/sasm110313/tailscale-tray/refs/heads/master/setup.sh)
```

---

## 🛠️ Usage

1. **Exit Nodes Submenu**: Right-click the tray icon and select **Exit Nodes** to choose any auto-discovered node in your tailnet.
2. **Quick Connect**: Click **"Connect to <node>"** to activate your default exit node.
3. **Allow Local Network Access**: Check **"Allow Local Network (LAN) Access"** to keep access to local devices (printers, local routers, etc.) while connected to the VPN.
4. **Settings...**: Open the GUI settings window to change startup preferences or set a default exit node IP (`e.g. 100.64.0.1`).

### Tray Menu Overview

| Menu item | Action |
|-----------|--------|
| **Status** | Shows current connection state, active node name, and IP |
| **Exit Nodes ➔** | Submenu listing all discovered exit nodes (click any to switch) |
| **Allow Local Network Access** | Checkbox toggle for LAN access (`--exit-node-allow-lan-access`) |
| **Connect to &lt;node&gt;** | Connects to configured default exit node |
| **Disconnect Exit Node** | Clears active exit node (returns to direct connection) |
| **Settings...** | Opens GUI configuration dialog |
| **Refresh Status** | Manually triggers status refresh |
| **About** | Shows version, config, and log paths |
| **Quit** | Exit the tray app (optionally disconnects exit node) |

---

## ⚙️ Configuration

Config file: `~/.config/tailscale-tray/config.conf`

```ini
[tailscale]
exit_node = 100.64.0.1
allow_lan = false
auto_connect = false

[options]
disconnect_on_quit = false
```

**Log file:** `~/.config/tailscale-tray/tailscale-tray.log`

---

## 📦 Manage the Service

```bash
# Status
systemctl --user status tailscale-tray.service

# Restart
systemctl --user restart tailscale-tray.service

# Logs
tail -f ~/.config/tailscale-tray/tailscale-tray.log
```

---

## 🧹 Uninstall

```bash
sudo ./uninstall.sh
```

---

## 📄 License

MIT — free to use, modify, and distribute.
