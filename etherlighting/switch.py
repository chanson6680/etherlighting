"""Strict SSH connection. Only discovery and validated LED commands are exposed."""
from __future__ import annotations
import json
import re
import time
import uuid
from pathlib import Path
from core import led_command, restore_command
from models import identify, validate_interface

READS = {
    "mac_table": "swctrl mac show",
    "port_table": "swctrl port show",
    "identity": "cat /etc/board.info; cat /etc/version",
    "led_help": "cat /proc/led/led_code",
    "raw_help": "cat /proc/led/led_color",
    "mode": "cat /proc/led/led_etherlight_mode",
}


class SSHSwitch:
    writable = True

    def __init__(self, options):
        self.options = options
        self.client = None
        self.checked = False
        self.device = None
        self.control_identity = None

    def close(self):
        if self.client:
            self.client.close()
        self.client = None
        self.checked = False
        self.device = None

    def connect(self):
        import paramiko
        from paramiko.hostkeys import HostKeyEntry
        host = self.options.get("switch_host", "")
        username = self.options.get("ssh_username", "")
        password = self.options.get("ssh_password", "")
        key = self.options.get("ssh_host_key", "").strip()
        if not host or not username or not password or not key:
            raise ValueError("Complete the switch connection in the app's Home Assistant configuration.")
        if not re.fullmatch(r"[a-zA-Z0-9.-]+", host):
            raise ValueError("Use an IPv4 address or DNS name for the switch.")
        try:
            entry = HostKeyEntry.from_line(host + " " + key)
            if not entry or not entry.key:
                raise ValueError()
        except Exception as error:
            raise ValueError("The SSH host key must contain its type and full public key.") from error
        client = paramiko.SSHClient()
        client.get_host_keys().add(host, entry.key.get_name(), entry.key)
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        try:
            client.connect(host, username=username, password=password, allow_agent=False,
                           look_for_keys=False, timeout=10, banner_timeout=10, auth_timeout=15)
            client.get_transport().set_keepalive(30)
            self.client = client
        except Exception:
            client.close()
            raise

    def _run(self, command, write=False):
        if not self.client or not self.client.get_transport() or not self.client.get_transport().is_active():
            self.close()
            self.connect()
        if write and not self.checked:
            self.verify_control()
        channel = self.client.get_transport().open_session(timeout=10)
        channel.settimeout(15)
        out, err = bytearray(), bytearray()
        try:
            channel.exec_command(command)
            deadline = time.monotonic() + 20
            while True:
                while channel.recv_ready():
                    out.extend(channel.recv(65536))
                while channel.recv_stderr_ready():
                    err.extend(channel.recv_stderr(65536))
                if len(out) + len(err) > 2_000_000:
                    raise ValueError("The switch response exceeded the read limit.")
                if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                    code = channel.recv_exit_status()
                    if code != 0:
                        detail = " ".join((err or out).decode("utf-8", "replace").split())[:300]
                        raise RuntimeError(f"Switch command failed (exit {code}): {detail or 'no error detail returned'}")
                    return out.decode("utf-8", "replace")
                if time.monotonic() > deadline:
                    raise TimeoutError("The switch took too long to respond.")
                time.sleep(0.03)
        finally:
            channel.close()

    def read(self, name):
        try:
            return self._run(READS[name])
        except Exception as error:
            raise RuntimeError(f"Reading {name}: {error}") from error

    def describe(self):
        # Refresh identity before discovery, including after a switch reboot.
        device = identify(self.read("identity"))
        if self.device != device:
            self.checked = False
        self.device = device
        return self.device

    def verify_control(self):
        self.checked = False
        device = self.describe()
        identity = (device["model"], device["firmware"])
        if self.control_identity and identity != self.control_identity:
            raise ValueError("Switch model or firmware changed. Restart the app and review compatibility before LED writes.")
        validate_interface(device, self.read("led_help"), self.read("raw_help"),
                           self.read("mode"), self.options.get("allow_experimental_models", False))
        try:
            self._run("printf '%s\\n' 'etherlighting-check'")
        except Exception as error:
            raise RuntimeError(f"Checking switch shell output (no LED write): {error}") from error
        self.checked = True
        self.control_identity = identity

    def color(self, port, color, brightness):
        if not self.checked:
            self.verify_control()
        try:
            self._run(led_command(port, color, brightness, self.device["port_count"]), write=True)
        except Exception as error:
            raise RuntimeError(f"Setting port {port} color: {error}") from error

    def restore(self):
        if not self.checked:
            self.verify_control()
        mode = int(self.read("mode").strip())
        try:
            self._run(restore_command(mode), write=True)
        except Exception as error:
            raise RuntimeError(f"Restoring stock lighting: {error}") from error


class ReadOnlyQueue:
    """Development-only adapter to the user-authenticated diagnostics helper."""
    writable = False

    def __init__(self, path):
        self.path = Path(path)

    def read(self, name):
        if name not in ("mac_table", "port_table"):
            raise ValueError("The preview connection only supports discovery.")
        status = json.loads((self.path / "status.json").read_text())
        if status.get("state") != "connected":
            raise RuntimeError("The temporary switch connection has closed.")
        job = "app-" + uuid.uuid4().hex + ".json"
        request = self.path / "requests" / job
        temporary = request.with_suffix(".tmp")
        temporary.write_text(json.dumps(dict(kind="probe", name=name)), encoding="utf-8")
        temporary.replace(request)
        result = self.path / "results" / job
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if result.exists():
                value = json.loads(result.read_text())
                if not value.get("ok") or value.get("exit_code"):
                    raise RuntimeError("The read-only switch check failed.")
                return value["stdout"]
            time.sleep(0.1)
        raise TimeoutError("The temporary connection did not respond.")

    def close(self):
        pass
