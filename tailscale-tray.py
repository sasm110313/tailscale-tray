#!/usr/bin/env python3
"""
Tailscale Tray Manager for Linux
A lightweight system tray application to manage Tailscale VPN exit node.

Config file: ~/.config/tailscale-tray/config.conf
  [tailscale]
  exit_node = <IP or hostname>
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
gi.require_version('Notify', '0.7')
from gi.repository import Gtk, AppIndicator3, GLib, Notify
import subprocess
import threading
import signal
import json
import os
import configparser
from datetime import datetime

APP_ID = "tailscale-tray"
APP_NAME = "Tailscale Tray"
CONFIG_DIR = os.path.expanduser("~/.config/tailscale-tray")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.conf")
LOG_FILE = os.path.join(CONFIG_DIR, "tailscale-tray.log")

ICON_CONNECTED = "network-vpn"
ICON_DISCONNECTED = "network-offline"
ICON_CONNECTING = "network-transmit-receive"

CONNECT_ICON = "go-next"
DISCONNECT_ICON = "process-stop"

# tailscale binary location (with fallbacks for different distros)
TAILSCALE_BIN = None
for cand in ("/usr/bin/tailscale", "/usr/local/bin/tailscale", "/bin/tailscale"):
    if os.path.exists(cand):
        TAILSCALE_BIN = cand
        break
if not TAILSCALE_BIN:
    TAILSCALE_BIN = "tailscale"  # fall back to PATH

DEFAULT_CONFIG = """[tailscale]
# Exit node IP address or hostname to connect to.
# Leave empty to have no exit node configured by default.
# Example: exit_node = 100.82.248.81
exit_node =

[options]
# Automatically disconnect the current exit node when quitting
disconnect_on_quit = false
"""


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def ensure_config_file():
    """Create config dir + default config file if missing."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        if not os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "w") as f:
                f.write(DEFAULT_CONFIG)
    except Exception as e:
        log(f"ensure_config error: {e}")


def load_config():
    config = configparser.ConfigParser()
    exit_node = ""

    if os.path.exists(CONFIG_FILE):
        try:
            config.read(CONFIG_FILE)
            exit_node = config.get("tailscale", "exit_node", fallback="").strip()
        except Exception as e:
            log(f"Config read error: {e}")

    return exit_node


def save_config(exit_node):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        config = configparser.ConfigParser()
        if os.path.exists(CONFIG_FILE):
            config.read(CONFIG_FILE)
        if not config.has_section("tailscale"):
            config.add_section("tailscale")
        config.set("tailscale", "exit_node", exit_node)
        with open(CONFIG_FILE, "w") as f:
            config.write(f)
        return True
    except Exception as e:
        log(f"Config write error: {e}")
        return False


class ConfigDialog:
    """A GTK dialog for editing the exit node config."""

    def __init__(self, parent, current_value):
        self.dialog = Gtk.Dialog(
            title="Tailscale Tray - Settings",
            transient_for=parent,
            modal=True,
            default_width=460,
            default_height=200,
            flags=0
        )
        self.dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_SAVE, Gtk.ResponseType.OK
        )

        box = self.dialog.get_content_area()
        box.set_spacing(12)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_left(12)
        box.set_margin_right(12)

        # Title
        title = Gtk.Label()
        title.set_markup("<span size='x-large' weight='bold'>Exit Node Settings</span>")
        title.set_halign(Gtk.Align.START)
        box.pack_start(title, False, False, 0)

        # Description
        desc = Gtk.Label()
        desc.set_markup(
            "Enter the IP address or hostname of the Tailscale node you\n"
            "want to use as your VPN exit node.\n"
            "<i>Leave empty to disable the exit node.</i>"
        )
        desc.set_halign(Gtk.Align.START)
        box.pack_start(desc, False, False, 0)

        # Entry with label
        entry_row = Gtk.Box(spacing=8)
        label = Gtk.Label(label="Exit node:")
        label.set_halign(Gtk.Align.START)
        entry_row.pack_start(label, False, False, 0)

        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("e.g. 100.82.248.81")
        self.entry.set_text(current_value)
        self.entry.connect("activate", self._on_enter)
        entry_row.pack_start(self.entry, True, True, 0)
        box.pack_start(entry_row, False, False, 0)

        # Hint
        hint = Gtk.Label()
        hint.set_markup(
            "<small>Config saved to: <span font_family='monospace'>~/.config/tailscale-tray/config.conf</span></small>"
        )
        hint.set_halign(Gtk.Align.START)
        box.pack_start(hint, False, False, 0)

        self.dialog.connect("response", self._on_response)
        self.result = None

    def _on_enter(self, widget):
        self.dialog.response(Gtk.ResponseType.OK)

    def _on_response(self, dialog, response):
        if response == Gtk.ResponseType.OK:
            self.result = self.entry.get_text().strip()
        dialog.destroy()

    def run(self):
        self.dialog.show_all()
        self.dialog.run()
        return self.result


class TailscaleTray:
    def __init__(self):
        Notify.init(APP_ID)
        self.exit_node = load_config()
        self.connected = False
        self.current_node = None
        self._check_real_status()

        self.indicator = AppIndicator3.Indicator.new(
            APP_ID,
            ICON_DISCONNECTED if not self.connected else ICON_CONNECTED,
            AppIndicator3.IndicatorCategory.SYSTEM_SERVICES
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)

        self.menu = Gtk.Menu()

        self.status_item = Gtk.MenuItem(label=self._status_text())
        self.status_item.set_sensitive(False)
        self.menu.append(self.status_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        self.connect_item = Gtk.ImageMenuItem(label=self._connect_label())
        self.connect_item.set_image(Gtk.Image.new_from_icon_name(CONNECT_ICON, Gtk.IconSize.MENU))
        self.connect_item.connect("activate", self._on_connect)
        self.menu.append(self.connect_item)

        self.disconnect_item = Gtk.ImageMenuItem(label="Disconnect Exit Node")
        self.disconnect_item.set_image(Gtk.Image.new_from_icon_name(DISCONNECT_ICON, Gtk.IconSize.MENU))
        self.disconnect_item.connect("activate", self._on_disconnect)
        self.menu.append(self.disconnect_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        config_item = Gtk.ImageMenuItem(label="Settings...")
        config_item.set_image(Gtk.Image.new_from_icon_name(Gtk.STOCK_PREFERENCES, Gtk.IconSize.MENU))
        config_item.connect("activate", self._on_config)
        self.menu.append(config_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        check_item = Gtk.ImageMenuItem(label="Refresh Status")
        check_item.set_image(Gtk.Image.new_from_icon_name(Gtk.STOCK_REFRESH, Gtk.IconSize.MENU))
        check_item.connect("activate", self._on_check)
        self.menu.append(check_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        about_item = Gtk.ImageMenuItem(label="About")
        about_item.set_image(Gtk.Image.new_from_icon_name(Gtk.STOCK_ABOUT, Gtk.IconSize.MENU))
        about_item.connect("activate", self._on_about)
        self.menu.append(about_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.ImageMenuItem(label="Quit")
        quit_item.set_image(Gtk.Image.new_from_icon_name(Gtk.STOCK_QUIT, Gtk.IconSize.MENU))
        quit_item.connect("activate", self._on_quit)
        self.menu.append(quit_item)

        self.menu.show_all()
        self.indicator.set_menu(self.menu)
        self._update_ui()
        log(f"Started, exit_node='{self.exit_node}', state: {'connected' if self.connected else 'disconnected'}")

    def _connect_label(self):
        if self.exit_node:
            return f"Connect to {self.exit_node}"
        return "Connect (not configured)"

    def _run_elevated(self, tailscale_args, callback=None):
        """Run tailscale as root. Tries sudo (NOPASSWD), falls back to pkexec (graphical prompt)."""
        log(f"Elevated: {TAILSCALE_BIN} {' '.join(tailscale_args)}")

        if callback is None:
            callback = lambda *a: None

        def _thread():
            # Try 1: sudo (non-interactive) - works when sudoers NOPASSWD rule is present
            cmd = ["sudo", "-n", TAILSCALE_BIN] + tailscale_args
            res = self._execute_list(cmd)
            if res[0] == 0:
                GLib.idle_add(callback, *res)
                return

            # Try 2: pkexec (graphical auth prompt) - works without pre-config, on any distro
            log("sudo failed/prompt required, falling back to pkexec...")
            pcmd = ["pkexec", TAILSCALE_BIN] + tailscale_args
            res2 = self._execute_list(pcmd, timeout=60)
            GLib.idle_add(callback, *res2)

        threading.Thread(target=_thread, daemon=True).start()

    def _execute_list(self, cmd, timeout=30):
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
            log(f"Exit code: {result.returncode}")
            if result.stdout.strip():
                log(f"stdout: {result.stdout.strip()[:500]}")
            if result.stderr.strip():
                log(f"stderr: {result.stderr.strip()[:500]}")
            return (result.returncode, result.stdout.strip(), result.stderr.strip())
        except subprocess.TimeoutExpired:
            log("Command timed out")
            return (-1, "", "Command timed out")
        except Exception as e:
            log(f"Exception: {e}")
            return (-1, "", str(e))

    def _check_real_status(self):
        try:
            result = subprocess.run(
                [TAILSCALE_BIN, "status", "--json"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                log(f"tailscale status failed: {result.stderr}")
                self.connected = False
                self.current_node = None
                return

            data = json.loads(result.stdout)
            en = data.get("ExitNodeStatus")
            self.connected = bool(en)

            if en:
                ips = en.get("TailscaleIPs") or []
                self.current_node = ips[0].split("/")[0] if ips else "unknown"
            else:
                self.current_node = None

            log(f"Status check: connected={self.connected}, node={self.current_node}")

        except json.JSONDecodeError as e:
            log(f"JSON error: {e}")
            self.connected = False
            self.current_node = None
        except Exception as e:
            log(f"Status error: {e}")
            self.connected = False
            self.current_node = None

    def _status_text(self):
        if self.connected:
            node = self.current_node or "unknown"
            return f"Connected to {node}"
        return "Disconnected"

    def _update_ui(self):
        if self.connected:
            self.indicator.set_icon_full(ICON_CONNECTED, "Connected")
            self.status_item.set_label(f"Status: {self._status_text()}")
        else:
            self.indicator.set_icon_full(ICON_DISCONNECTED, "Disconnected")
            self.status_item.set_label("Status: Disconnected")

        if self.exit_node:
            self.connect_item.set_label(self._connect_label())
            self.connect_item.set_sensitive(not self.connected)
            self.disconnect_item.set_sensitive(self.connected)
        else:
            self.connect_item.set_sensitive(False)
            self.disconnect_item.set_sensitive(self.connected)

    def _on_connect(self, widget):
        if not self.exit_node:
            self._notify("No Exit Node", "Set an exit node in Settings first")
            self._on_config(None)
            return
        log("=== CONNECT ===")
        self.connect_item.set_sensitive(False)
        self.disconnect_item.set_sensitive(False)
        self.indicator.set_icon_full(ICON_CONNECTING, "Connecting...")
        self._run_elevated(["set", f"--exit-node={self.exit_node}"], self._on_connect_done)

    def _on_connect_done(self, returncode, stdout, stderr):
        if returncode == 0:
            GLib.timeout_add(2000, self._verify_after_connect)
        else:
            self._notify("Connection Failed", stderr or "Error")
            self._check_real_status()
            self._update_ui()

    def _verify_after_connect(self):
        self._check_real_status()
        self._update_ui()
        if self.connected:
            self._notify("Connected", f"Exit node: {self.current_node}")
        else:
            self._notify("Warning", "Command OK but status shows disconnected")
        return False

    def _on_disconnect(self, widget):
        log("=== DISCONNECT ===")
        self.connect_item.set_sensitive(False)
        self.disconnect_item.set_sensitive(False)
        self.indicator.set_icon_full(ICON_CONNECTING, "Disconnecting...")
        self._run_elevated(["set", "--exit-node="], self._on_disconnect_done)

    def _on_disconnect_done(self, returncode, stdout, stderr):
        if returncode == 0:
            GLib.timeout_add(2000, self._verify_after_disconnect)
        else:
            self._notify("Disconnection Failed", stderr or "Error")
            self._check_real_status()
            self._update_ui()

    def _verify_after_disconnect(self):
        self._check_real_status()
        self._update_ui()
        if not self.connected:
            self._notify("Disconnected", "Exit node cleared")
        else:
            self._notify("Warning", "Command OK but still shows connected")
        return False

    def _on_check(self, widget):
        log("=== REFRESH ===")
        self._check_real_status()
        self._update_ui()

    def _on_config(self, widget):
        dialog = ConfigDialog(None, self.exit_node)
        result = dialog.run()
        if result is not None:
            if save_config(result):
                self.exit_node = result
                self._update_ui()
                self._notify("Config Saved", f"Exit node set to: '{result or '(empty)'}'")
            else:
                self._notify("Error", "Could not save config")

    def _on_about(self, widget):
        dlg = Gtk.MessageDialog(
            transient_for=None, modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=f"About {APP_NAME}"
        )
        dlg.format_secondary_markup(
            "<b>Tailscale Tray Manager</b>\n\n"
            "A simple system tray app to manage your Tailscale\n"
            "VPN exit node.\n\n"
            f"Config: <span font_family='monospace'>{CONFIG_FILE}</span>\n"
            f"Log: <span font_family='monospace'>{LOG_FILE}</span>"
        )
        dlg.run()
        dlg.destroy()

    def _notify(self, title, message):
        log(f"Notify: {title} - {message}")
        try:
            n = Notify.Notification.new(title, message)
            n.show()
        except Exception as e:
            log(f"Notify failed: {e}")

    def _on_quit(self, widget):
        Notify.uninit()
        Gtk.main_quit()


def main():
    ensure_config_file()
    log("=== Starting ===")
    signal.signal(signal.SIGTERM, lambda s, f: Gtk.main_quit())
    TailscaleTray()
    Gtk.main()


if __name__ == "__main__":
    main()
