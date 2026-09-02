#!/usr/bin/env python3
"""
Tailscale Tray Manager for Linux
A lightweight, powerful system tray application to manage Tailscale VPN exit node,
auto-discover exit nodes in your tailnet, toggle LAN access, and monitor status.

Config file: ~/.config/tailscale-tray/config.conf
"""

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

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
import shutil
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

# tailscale binary location resolution
def find_tailscale_bin():
    found = shutil.which("tailscale")
    if found:
        return found
    for cand in ("/usr/bin/tailscale", "/usr/local/bin/tailscale", "/bin/tailscale", "/snap/bin/tailscale"):
        if os.path.exists(cand):
            return cand
    return "tailscale"

TAILSCALE_BIN = find_tailscale_bin()

DEFAULT_CONFIG = """[tailscale]
# Exit node IP address or hostname to connect to.
# Leave empty to have no exit node configured by default.
# Example: exit_node = 100.64.0.1
exit_node =

# Allow access to local network (LAN) when using exit node
allow_lan = false

# Auto-connect configured exit node on application startup
auto_connect = false

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
    settings = {
        "exit_node": "",
        "allow_lan": False,
        "auto_connect": False,
        "disconnect_on_quit": False,
    }

    if os.path.exists(CONFIG_FILE):
        try:
            config.read(CONFIG_FILE)
            settings["exit_node"] = config.get("tailscale", "exit_node", fallback="").strip()
            settings["allow_lan"] = config.getboolean("tailscale", "allow_lan", fallback=False)
            settings["auto_connect"] = config.getboolean("tailscale", "auto_connect", fallback=False)
            settings["disconnect_on_quit"] = config.getboolean("options", "disconnect_on_quit", fallback=False)
        except Exception as e:
            log(f"Config read error: {e}")

    return settings


def save_config(settings):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        config = configparser.ConfigParser()
        if os.path.exists(CONFIG_FILE):
            config.read(CONFIG_FILE)
        if not config.has_section("tailscale"):
            config.add_section("tailscale")
        if not config.has_section("options"):
            config.add_section("options")

        config.set("tailscale", "exit_node", settings.get("exit_node", ""))
        config.set("tailscale", "allow_lan", str(settings.get("allow_lan", False)).lower())
        config.set("tailscale", "auto_connect", str(settings.get("auto_connect", False)).lower())
        config.set("options", "disconnect_on_quit", str(settings.get("disconnect_on_quit", False)).lower())

        with open(CONFIG_FILE, "w") as f:
            config.write(f)
        return True
    except Exception as e:
        log(f"Config write error: {e}")
        return False


def make_icon_menu_item(label_text, icon_name):
    """Create a modern Gtk.MenuItem containing an icon and label without deprecation warnings."""
    item = Gtk.MenuItem()
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    image = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
    label = Gtk.Label(label=label_text)
    box.pack_start(image, False, False, 0)
    box.pack_start(label, False, False, 0)
    item.add(box)
    return item, label


class ConfigDialog:
    """A GTK dialog for editing configuration settings."""

    def __init__(self, parent, current_settings):
        self.dialog = Gtk.Dialog(
            title="Tailscale Tray - Settings",
            transient_for=parent,
            modal=True,
            default_width=480,
            default_height=320,
            flags=0
        )
        self.dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_SAVE, Gtk.ResponseType.OK
        )

        box = self.dialog.get_content_area()
        box.set_spacing(12)
        box.set_margin_top(14)
        box.set_margin_bottom(14)
        box.set_margin_start(16)
        box.set_margin_end(16)

        # Title
        title = Gtk.Label()
        title.set_markup("<span size='x-large' weight='bold'>Tailscale Tray Settings</span>")
        title.set_halign(Gtk.Align.START)
        box.pack_start(title, False, False, 0)

        # Description
        desc = Gtk.Label()
        desc.set_markup(
            "Configure your default exit node IP/hostname and connection behavior."
        )
        desc.set_halign(Gtk.Align.START)
        box.pack_start(desc, False, False, 0)

        # Entry with label
        entry_row = Gtk.Box(spacing=8)
        label = Gtk.Label(label="Default Exit Node:")
        label.set_halign(Gtk.Align.START)
        entry_row.pack_start(label, False, False, 0)

        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("e.g. 100.64.0.1 or node-name")
        self.entry.set_text(current_settings.get("exit_node", ""))
        self.entry.connect("activate", self._on_enter)
        entry_row.pack_start(self.entry, True, True, 0)
        box.pack_start(entry_row, False, False, 0)

        # Checkboxes
        self.chk_allow_lan = Gtk.CheckButton(label="Allow access to local network (LAN) when connected")
        self.chk_allow_lan.set_active(current_settings.get("allow_lan", False))
        box.pack_start(self.chk_allow_lan, False, False, 0)

        self.chk_auto_connect = Gtk.CheckButton(label="Auto-connect exit node on application startup")
        self.chk_auto_connect.set_active(current_settings.get("auto_connect", False))
        box.pack_start(self.chk_auto_connect, False, False, 0)

        self.chk_disconnect_quit = Gtk.CheckButton(label="Disconnect exit node on quit")
        self.chk_disconnect_quit.set_active(current_settings.get("disconnect_on_quit", False))
        box.pack_start(self.chk_disconnect_quit, False, False, 0)

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
            self.result = {
                "exit_node": self.entry.get_text().strip(),
                "allow_lan": self.chk_allow_lan.get_active(),
                "auto_connect": self.chk_auto_connect.get_active(),
                "disconnect_on_quit": self.chk_disconnect_quit.get_active(),
            }
        dialog.destroy()

    def run(self):
        self.dialog.show_all()
        self.dialog.run()
        return self.result


class TailscaleTray:
    def __init__(self):
        Notify.init(APP_ID)
        self.settings = load_config()
        self.connected = False
        self.current_node = None
        self.tailscale_online = False
        self.tailnet_name = ""
        self.my_ip = ""
        self.discovered_nodes = [] # list of dicts: {'name': str, 'ip': str, 'online': bool, 'is_current': bool}
        self.is_operating = False

        self.indicator = AppIndicator3.Indicator.new(
            APP_ID,
            ICON_DISCONNECTED,
            AppIndicator3.IndicatorCategory.SYSTEM_SERVICES
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)

        self._build_menu()
        
        # Initial status check & periodic status polling (every 5s)
        self._async_check_status(first_run=True)
        GLib.timeout_add_seconds(5, self._periodic_status_check)

        log(f"Started. Default exit_node='{self.settings['exit_node']}', LAN='{self.settings['allow_lan']}'")

    def _build_menu(self):
        self.menu = Gtk.Menu()

        # Status item
        self.status_item = Gtk.MenuItem(label="Status: Checking...")
        self.status_item.set_sensitive(False)
        self.menu.append(self.status_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        # Exit Node Submenu
        self.exit_node_menu_item = Gtk.MenuItem(label="Exit Nodes")
        self.exit_nodes_submenu = Gtk.Menu()
        self.exit_node_menu_item.set_submenu(self.exit_nodes_submenu)
        self.menu.append(self.exit_node_menu_item)

        # Allow LAN Access toggle menu item
        self.lan_item = Gtk.CheckMenuItem(label="Allow Local Network (LAN) Access")
        self.lan_item.set_active(self.settings.get("allow_lan", False))
        self.lan_item.connect("toggled", self._on_toggle_lan)
        self.menu.append(self.lan_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        # Quick Connect/Disconnect Items
        self.connect_item, self.connect_label = make_icon_menu_item(self._connect_label(), CONNECT_ICON)
        self.connect_item.connect("activate", self._on_connect_default)
        self.menu.append(self.connect_item)

        self.disconnect_item, _ = make_icon_menu_item("Disconnect Exit Node", DISCONNECT_ICON)
        self.disconnect_item.connect("activate", self._on_disconnect)
        self.menu.append(self.disconnect_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        # Settings
        config_item, _ = make_icon_menu_item("Settings...", Gtk.STOCK_PREFERENCES)
        config_item.connect("activate", self._on_config)
        self.menu.append(config_item)

        # Refresh
        check_item, _ = make_icon_menu_item("Refresh Status", Gtk.STOCK_REFRESH)
        check_item.connect("activate", lambda w: self._async_check_status())
        self.menu.append(check_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        # About
        about_item, _ = make_icon_menu_item("About", Gtk.STOCK_ABOUT)
        about_item.connect("activate", self._on_about)
        self.menu.append(about_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        # Quit
        quit_item, _ = make_icon_menu_item("Quit", Gtk.STOCK_QUIT)
        quit_item.connect("activate", self._on_quit)
        self.menu.append(quit_item)

        self.menu.show_all()
        self.indicator.set_menu(self.menu)

    def _connect_label(self):
        target = self.settings.get("exit_node", "")
        if target:
            return f"Connect to {target}"
        return "Connect Default Exit Node"

    def _run_async_command(self, cmd, callback, timeout=30):
        """Run shell command in background thread without blocking GTK UI."""
        def _worker():
            res = self._execute_cmd(cmd, timeout=timeout)
            GLib.idle_add(callback, *res)

        threading.Thread(target=_worker, daemon=True).start()

    def _run_elevated_async(self, tailscale_args, callback):
        """Run tailscale as root asynchronously using sudo (NOPASSWD) or pkexec."""
        def _worker():
            cmd = ["sudo", "-n", TAILSCALE_BIN] + tailscale_args
            res = self._execute_cmd(cmd, timeout=30)
            if res[0] == 0:
                GLib.idle_add(callback, *res)
                return

            log("sudo failed or required password, falling back to pkexec...")
            pcmd = ["pkexec", TAILSCALE_BIN] + tailscale_args
            res2 = self._execute_cmd(pcmd, timeout=60)
            GLib.idle_add(callback, *res2)

        threading.Thread(target=_worker, daemon=True).start()

    def _execute_cmd(self, cmd, timeout=30):
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
            return (result.returncode, result.stdout.strip(), result.stderr.strip())
        except subprocess.TimeoutExpired:
            return (-1, "", "Command timed out")
        except Exception as e:
            return (-1, "", str(e))

    def _periodic_status_check(self):
        if not self.is_operating:
            self._async_check_status()
        return True # Continue polling

    def _async_check_status(self, first_run=False):
        cmd = [TAILSCALE_BIN, "status", "--json"]
        self._run_async_command(cmd, lambda rc, stdout, stderr: self._parse_status_result(rc, stdout, stderr, first_run))

    def _parse_status_result(self, returncode, stdout, stderr, first_run=False):
        if returncode != 0:
            log(f"Status command failed: {stderr}")
            self.tailscale_online = False
            self.connected = False
            self.current_node = None
            self.discovered_nodes = []
            self._update_ui()
            return

        try:
            data = json.loads(stdout)
            backend_state = data.get("BackendState", "")
            self.tailscale_online = (backend_state == "Running")
            
            # Current device IP & tailnet info
            self_node = data.get("Self") or {}
            ips = self_node.get("TailscaleIPs") or []
            self.my_ip = ips[0] if ips else ""
            self.tailnet_name = data.get("MagicDNSSuffix", "")

            # Exit node status
            en = data.get("ExitNodeStatus")
            self.connected = bool(en)

            current_exit_ip = None
            if en:
                en_ips = en.get("TailscaleIPs") or []
                current_exit_ip = en_ips[0].split("/")[0] if en_ips else None
                self.current_node = en.get("HostName") or current_exit_ip or "unknown"
            else:
                self.current_node = None

            # Auto-discover peers that can act as exit nodes
            peers = data.get("Peer") or {}
            nodes = []
            for node_key, peer in peers.items():
                is_exit_option = peer.get("ExitNodeOption", False) or peer.get("ExitNode", False)
                if is_exit_option:
                    hostname = peer.get("HostName") or peer.get("DNSName", "").split(".")[0] or "Unknown Node"
                    p_ips = peer.get("TailscaleIPs") or []
                    p_ip = p_ips[0] if p_ips else ""
                    online = peer.get("Online", False)
                    is_curr = (current_exit_ip and p_ip == current_exit_ip) or (self.current_node and hostname == self.current_node)
                    nodes.append({
                        "name": hostname,
                        "ip": p_ip,
                        "online": online,
                        "is_current": is_curr
                    })

            self.discovered_nodes = nodes
            self._update_ui()

            # Perform auto-connect on startup if configured
            if first_run and self.settings.get("auto_connect") and not self.connected and self.settings.get("exit_node"):
                log("Auto-connect triggered on launch.")
                self._connect_to_node(self.settings.get("exit_node"))

        except json.JSONDecodeError as e:
            log(f"Status JSON error: {e}")
            self.tailscale_online = False
            self.connected = False
            self._update_ui()

    def _update_ui(self):
        if not self.tailscale_online:
            self.indicator.set_icon_full(ICON_DISCONNECTED, "Tailscale Offline")
            self.status_item.set_label("Status: Tailscale Offline / Stopped")
        elif self.connected:
            self.indicator.set_icon_full(ICON_CONNECTED, "Connected")
            self.status_item.set_label(f"Status: Connected ({self.current_node})")
        else:
            self.indicator.set_icon_full(ICON_DISCONNECTED, "Disconnected")
            self.status_item.set_label("Status: Tailscale Online (Direct)")

        self.connect_label.set_text(self._connect_label())
        self.connect_item.set_sensitive(self.tailscale_online and not self.is_operating and not self.connected)
        self.disconnect_item.set_sensitive(self.tailscale_online and not self.is_operating and self.connected)
        self.lan_item.set_sensitive(not self.is_operating)

        self._rebuild_exit_nodes_submenu()

    def _rebuild_exit_nodes_submenu(self):
        # Clear existing items
        for child in self.exit_nodes_submenu.get_children():
            self.exit_nodes_submenu.remove(child)

        if not self.discovered_nodes:
            item = Gtk.MenuItem(label="No exit nodes found in tailnet")
            item.set_sensitive(False)
            self.exit_nodes_submenu.append(item)
        else:
            group = None
            # Option: Disconnect / Direct connection
            off_item = Gtk.RadioMenuItem.new_with_label(group, "Direct (No Exit Node)")
            group = off_item.get_group()
            if not self.connected:
                off_item.set_active(True)
            off_item.connect("activate", self._on_select_off)
            self.exit_nodes_submenu.append(off_item)

            self.exit_nodes_submenu.append(Gtk.SeparatorMenuItem())

            for node in self.discovered_nodes:
                status_icon = "🟢" if node["online"] else "⚪"
                label_text = f"{status_icon} {node['name']} ({node['ip']})"
                n_item = Gtk.RadioMenuItem.new_with_label(group, label_text)
                group = n_item.get_group()

                if node["is_current"]:
                    n_item.set_active(True)

                target_ip = node["ip"] or node["name"]
                n_item.connect("activate", self._on_select_node_menu, target_ip)
                self.exit_nodes_submenu.append(n_item)

        self.exit_nodes_submenu.append(Gtk.SeparatorMenuItem())
        custom_item = Gtk.MenuItem(label="Enter Custom IP/Hostname...")
        custom_item.connect("activate", self._on_config)
        self.exit_nodes_submenu.append(custom_item)

        self.exit_nodes_submenu.show_all()

    def _on_select_off(self, widget):
        if widget.get_active() and self.connected and not self.is_operating:
            self._on_disconnect(widget)

    def _on_select_node_menu(self, widget, target_ip):
        if widget.get_active() and not self.is_operating:
            if self.current_node != target_ip and target_ip:
                self._connect_to_node(target_ip)

    def _on_toggle_lan(self, widget):
        new_val = widget.get_active()
        self.settings["allow_lan"] = new_val
        save_config(self.settings)
        log(f"Allow LAN toggled to: {new_val}")
        
        # If currently connected, re-apply set command with new LAN option
        if self.connected and self.current_node and not self.is_operating:
            self._connect_to_node(self.current_node)

    def _on_connect_default(self, widget):
        target = self.settings.get("exit_node", "")
        if not target:
            self._notify("No Exit Node Configured", "Opening settings to set an exit node IP...")
            self._on_config(None)
            return
        self._connect_to_node(target)

    def _connect_to_node(self, exit_node_target):
        if self.is_operating:
            return
        log(f"=== CONNECT TO {exit_node_target} ===")
        self.is_operating = True
        self.indicator.set_icon_full(ICON_CONNECTING, "Connecting...")
        
        args = ["set", f"--exit-node={exit_node_target}"]
        if self.settings.get("allow_lan", False):
            args.append("--exit-node-allow-lan-access=true")
        else:
            args.append("--exit-node-allow-lan-access=false")

        self._run_elevated_async(args, lambda rc, stdout, stderr: self._on_connect_done(rc, stdout, stderr, exit_node_target))

    def _on_connect_done(self, returncode, stdout, stderr, target):
        self.is_operating = False
        if returncode == 0:
            self.settings["exit_node"] = target
            save_config(self.settings)
            GLib.timeout_add(1500, self._verify_after_connect)
        else:
            self._notify("Connection Failed", stderr or "Error setting exit node")
            self._async_check_status()

    def _verify_after_connect(self):
        self._async_check_status()
        if self.connected:
            self._notify("Connected to Exit Node", f"Node: {self.current_node or self.settings.get('exit_node')}")
        else:
            self._notify("Connection Status", "Waiting for Tailscale connection to establish...")
        return False

    def _on_disconnect(self, widget=None):
        if self.is_operating:
            return
        log("=== DISCONNECT ===")
        self.is_operating = True
        self.indicator.set_icon_full(ICON_CONNECTING, "Disconnecting...")
        args = ["set", "--exit-node="]
        self._run_elevated_async(args, self._on_disconnect_done)

    def _on_disconnect_done(self, returncode, stdout, stderr):
        self.is_operating = False
        if returncode == 0:
            GLib.timeout_add(1500, self._verify_after_disconnect)
        else:
            self._notify("Disconnection Failed", stderr or "Error clearing exit node")
            self._async_check_status()

    def _verify_after_disconnect(self):
        self._async_check_status()
        if not self.connected:
            self._notify("Disconnected", "Exit node cleared. Using direct connection.")
        else:
            self._notify("Warning", "Disconnect command sent, updating status...")
        return False

    def _on_config(self, widget):
        dialog = ConfigDialog(None, self.settings)
        result = dialog.run()
        if result is not None:
            self.settings.update(result)
            if save_config(self.settings):
                self._update_ui()
                self._notify("Settings Saved", f"Default exit node: '{self.settings['exit_node'] or '(none)'}'")
            else:
                self._notify("Error", "Could not save settings to config file")

    def _on_about(self, widget):
        dlg = Gtk.MessageDialog(
            transient_for=None, modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=f"About {APP_NAME}"
        )
        dlg.format_secondary_markup(
            "<b>Tailscale Tray Manager</b>\n\n"
            "A lightweight system tray application to manage your Tailscale\n"
            "VPN exit node with auto-discovery & LAN access options.\n\n"
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
        if self.settings.get("disconnect_on_quit") and self.connected:
            log("Disconnect on quit enabled. Clearing exit node...")
            self._execute_cmd(["sudo", "-n", TAILSCALE_BIN, "set", "--exit-node="])
        Notify.uninit()
        Gtk.main_quit()


def main():
    ensure_config_file()
    log("=== Starting Tailscale Tray ===")
    signal.signal(signal.SIGTERM, lambda s, f: Gtk.main_quit())
    TailscaleTray()
    Gtk.main()


if __name__ == "__main__":
    main()
