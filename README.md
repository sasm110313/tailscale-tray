# Tailscale Tray Manager

A lightweight, powerful system tray application for Linux to manage your **Tailscale VPN exit node** with a single click.

![Platform: Linux](https://img.shields.io/badge/platform-Linux-blue) ![Python](https://img.shields.io/badge/python-3.x-green)

---

## ✨ Features

- 🖥️ Runs in the system tray (top panel / notification area)
- ⚡ One-click **Connect** / **Disconnect** of your Tailscale exit node
- 🎛️ **Graphical Settings window** to configure your exit node IP (no manual file editing needed)
- 🔍 Real status verification using `tailscale status --json` (accurate, no guessing)
- 🔔 Desktop notifications on connect/disconnect/errors
- 🔄 Auto-starts on login via systemd
- 📝 Full logging for easy debugging
- 🐧 Works on **Fedora, Ubuntu, Debian, Arch, openSUSE** and most distros

---

## ⚠️ Prerequisites (IMPORTANT — read first)

Before installing, you must have:

1. **Tailscale installed** on this machine, on your tailnet, and logged in (`tailscale up`).
   - Install Tailscale: https://tailscale.com/download
2. **An exit node** must already be enabled on a **remote/external server** in your tailnet.
   - On that server (must be in a different location than you, ideally a VPS):
     ```bash
     sudo tailscale up --advertise-exit-node
     ```
   - Then approve/allow it as an exit node in the Tailscale admin console:
     https://login.tailscale.com/admin/dns
3. The **IP address** (e.g. `100.82.248.81`) or hostname of that exit-node server — you'll enter this in the app's Settings.

> ⚠️ **The exit node must be a SEPARATE machine (e.g. a VPS/cloud server), not your own computer.** Running it on the same machine you're on makes no sense for VPN exit traffic.

---

## 🚀 Install

### Method 1 — Git clone (recommended)

```bash
git clone https://github.com/sasm110313/tailscale-tray
cd tailscale-tray
sudo ./install.sh
```

The installer **auto-detects your distro** (Fedora, Ubuntu, Debian, Arch, openSUSE...) and installs the correct dependencies — and can even install Tailscale for you if it's missing.

### Method 2 — Quick install (one-liner)

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/sasm110313/tailscale-tray/refs/heads/master/setup.sh)
```

The one-liner downloads `setup.sh`, clones the repo, and runs the same installation automatically. Needs `git` + `curl`.

---

## 🛠️ Usage

1. After install, the tray icon appears in your top panel.
2. **Right-click the tray icon** → **Settings...**
3. Enter your exit node's **IP address** (e.g. `100.82.248.81`) and click **Save**.
4. Now click **"Connect to 100.82.248.81"** — your VPN is on.
5. To turn it off, click **"Disconnect Exit Node"**.

### Tray menu options

| Menu item | Action |
|-----------|--------|
| **Connect to &lt;node&gt;** | Sets the exit node (VPN on) |
| **Disconnect Exit Node** | Clears the exit node (VPN off) |
| **Settings...** | Opens the GUI config window |
| **Refresh Status** | Re-checks actual Tailscale status |
| **About** | Shows config & log paths |
| **Quit** | Closes the app |

---

## ⚙️ Configuration

You can configure via the **GUI** (recommended) or the config file directly:

```bash
nano ~/.config/tailscale-tray/config.conf
```

```ini
[tailscale]
exit_node = 100.82.248.81
```

Leave `exit_node` empty to disable. After editing the file, restart the service or click **Settings...** (it reloads the config).

**Log file:** `~/.config/tailscale-tray/tailscale-tray.log`

---

## 🔐 Root access (auto-handled)

The app needs root to run `tailscale set`. It handles this automatically on **any** system with a two-step fallback:

1. **`sudo -n`** — works immediately when the installer's sudoers rule is present (no password prompt).
2. **`pkexec`** — if sudo needs a password (e.g. no NOPASSWD rule), the app auto-falls back to a **graphical password prompt** via polkit. No manual config needed.

The installer adds `/etc/sudoers.d/tailscale-tray`, which automatically:
- Detects the correct admin group (`wheel`, `sudo`, or `admin`)
- Adds the installing user to that group if they're not already in one
- Allows running only `tailscale set` without a password (safe, scoped)

---

## 📦 Manage the service

```bash
# Check status
systemctl --user status tailscale-tray.service

# Restart (after editing config file)
systemctl --user restart tailscale-tray.service

# Stop
systemctl --user stop tailscale-tray.service

# Start
systemctl --user start tailscale-tray.service

# Watch logs live
tail -f ~/.config/tailscale-tray/tailscale-tray.log
```

The service starts **automatically on login**.

---

## 🔧 Manual dependency installation

If the installer's auto-detection didn't work, install these manually:

### Fedora / RHEL / CentOS
```bash
sudo dnf install python3-gobject gtk3 libayatana-appindicator-gtk3 libnotify
```

### Ubuntu / Debian
```bash
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-appindicator3-0.1 gir1.2-notify-0.7
```

### Arch
```bash
sudo pacman -S python-gobject gtk3 libayatana-appindicator libnotify
```

### openSUSE
```bash
sudo zypper install python3-gobject gtk3 typelib-1_0-AppIndicator3-0_1 typelib-1_0-Notify-0_7
```

---

## 🧹 Uninstall

```bash
sudo ./uninstall.sh
```

Your config file is kept at `~/.config/tailscale-tray/` — delete it manually if you want it gone.

---

## 🐛 Troubleshooting

**The icon doesn't appear in the tray?**
```bash
systemctl --user status tailscale-tray.service
tail -f ~/.config/tailscale-tray/tailscale-tray.log
```
Make sure you have an appindicator extension (e.g. `gnome-shell-extension-appindicator` on GNOME).

**"Connection failed"?**
- Confirm Tailscale is running: `systemctl status tailscaled`
- Confirm you're logged in: `tailscale status`
- Check the exit node is advertised & approved on the remote server.

---

## 📄 License

MIT — free to use, modify, and distribute.
