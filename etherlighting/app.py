from __future__ import annotations
import argparse
import json
import os
import secrets
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from core import load_rules, save_rules, make_plan, parse_macs, parse_ports
from switch import SSHSwitch, ReadOnlyQueue
from presets import load_presets, change_presets
from settings import load_settings, save_settings

ROOT = Path(__file__).resolve().parent


class Application:
    def __init__(self, data, options, switch):
        self.data, self.options, self.switch = data, options, switch
        data.mkdir(parents=True, exist_ok=True)
        self.rules = load_rules(data / "rules.json")
        self.presets = load_presets(data / "presets.json")
        self.settings = load_settings(data / "settings.json", options)
        self.lock = threading.RLock()
        self.quit = threading.Event()
        self.rows, self.ports = [], {}
        self.updated, self.error = 0, "Waiting for the switch"
        self.active = False
        self.applied = {}
        self.marker = data / "restore-pending.json"
        self.pending = self.marker.exists()
        self.csrf = secrets.token_urlsafe(32)
        self.allow_control = switch.writable and options.get("allow_led_control") is True
        self.next_poll, self.next_push = 0, 0
        self.last_push = 0

    def refresh(self, force=False, apply_colors=True):
        with self.lock:
            rows = parse_macs(self.switch.read("mac_table"))
            ports = parse_ports(self.switch.read("port_table"))
            self.rows, self.ports = rows, ports
            self.updated, self.error = time.time(), ""
            self.next_poll = time.monotonic() + self.settings["poll_seconds"]
            if self.active and apply_colors:
                self.apply(force=force)

    def plan(self):
        return make_plan(self.rows, self.ports, self.rules, settings=self.settings) if self.ports else dict(desired={}, decisions=[], fallback_ports=[])

    def dirty(self):
        if not self.pending:
            self.marker.write_text(json.dumps(dict(time=time.time())), encoding="utf-8")
        self.pending = True

    def restore(self):
        self.active = False
        if self.pending:
            if not self.allow_control:
                raise ValueError("LED restoration is pending. Enable LED control in configuration to restore it.")
            self.switch.restore()
            self.marker.unlink(missing_ok=True)
            self.pending = False
        self.applied = {}

    def apply(self, force=False):
        if not self.allow_control:
            raise ValueError("LED writes are disabled in this preview.")
        if self.error or time.time() - self.updated > 60:
            raise ValueError("Refresh the switch before applying colors.")
        desired = self.plan()["desired"]
        # Clear the previous port when a MAC moves, is paused, or disappears.
        if set(self.applied) - set(desired):
            self.restore()
            self.active = True
        for port, rule in desired.items():
            if not force and self.applied.get(port) == rule:
                continue
            self.dirty()  # Persist BEFORE writing, so crash recovery is visible.
            self.switch.color(port, rule["color"], rule["brightness"])
        self.applied = desired.copy()
        if force or not self.next_push:
            self.last_push = time.time()
            self.next_push = time.monotonic() + self.settings["push_seconds"]

    def snapshot(self):
        with self.lock:
            return dict(rows=self.rows, ports=list(self.ports.values()), rules=self.rules, presets=self.presets, settings=self.settings,
                        last_push=self.last_push, stale_after=self.settings["poll_seconds"] + 60,
                        plan=self.plan(), updated=self.updated, error=self.error,
                        active=self.active, allow_control=self.allow_control,
                        restore_pending=self.pending, applied=self.applied,
                        connection="direct" if self.switch.writable else "temporary",
                        switch_host=self.options.get("switch_host") or "Switch not configured")

    def action(self, path, body):
        with self.lock:
            if path == "/api/presets":
                self.presets = change_presets(self.data / "presets.json", self.presets, body)
            elif path == "/api/settings":
                self.settings = save_settings(self.data / "settings.json", body)
                self.next_poll = time.monotonic() + self.settings["poll_seconds"]
                self.next_push = time.monotonic() + self.settings["push_seconds"]
                if self.active:
                    try:
                        self.refresh()
                    except Exception as error:
                        self.handle_failure(error)
                        raise
            elif path == "/api/rules":
                self.rules = save_rules(self.data / "rules.json", body)
                if self.active:
                    self.refresh()
            elif path == "/api/refresh":
                self.refresh(force=True)
            elif path == "/api/start":
                if not self.allow_control:
                    raise ValueError("LED writes are disabled. Enable them in app configuration after reviewing the test instructions.")
                if self.pending:
                    self.restore()
                self.refresh()
                self.switch.verify_control()
                self.active = True
                self.apply(force=True)
            elif path == "/api/stop":
                self.restore()
            elif path == "/api/check":
                self.refresh(apply_colors=False)
                self.switch.verify_control()
            elif path == "/api/test":
                if not self.allow_control:
                    raise ValueError("LED writes are disabled in this preview.")
                if self.active or self.pending:
                    raise ValueError("Stop color control and restore the switch before a test.")
                self.refresh()
                address = body.get("mac")
                item = next((i for i in self.plan()["decisions"] if i["mac"] == address and i["status"] == "ready"), None)
                if not item:
                    raise ValueError("Save a rule for a device on an eligible port before testing.")
                self.switch.verify_control()
                self.dirty()
                try:
                    self.switch.color(item["port"], item["color"], item["brightness"])
                    self.quit.wait(10)
                finally:
                    self.restore()
            else:
                raise ValueError("Unknown action")
            return self.snapshot()

    def handle_failure(self, error):
        with self.lock:
            self.error = str(error)
            was_active = self.active
            self.active = False
            if was_active and self.pending:
                try:
                    self.restore()
                except Exception:
                    self.error += " Restoration is still pending; check the switch connection."

    def poll(self):
        while not self.quit.is_set():
            try:
                self.tick()
            except Exception as error:
                self.handle_failure(error)
                self.next_poll = time.monotonic() + self.settings["poll_seconds"]
            self.quit.wait(1)

    def tick(self):
        with self.lock:
            now = time.monotonic()
            push_due = self.active and self.settings["push_seconds"] > 0 and now >= self.next_push
            if now >= self.next_poll or push_due:
                # Revalidate locations before every periodic forced push.
                self.refresh(force=push_due)


def handler_for(app, local=False):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(20)

        def log_message(self, fmt, *args):
            pass  # Never log bodies, credentials, or discovered device names.

        def allowed(self):
            allowed = {"127.0.0.1", "::1"} if local else {"172.30.32.2"}
            if self.client_address[0] not in allowed:
                return False
            if local:
                host = self.headers.get("Host", "").split(":")[0]
                return host in ("127.0.0.1", "localhost")
            return True

        def send(self, value, status=200, content_type="application/json"):
            raw = json.dumps(value).encode() if content_type == "application/json" else value
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'; base-uri 'self'")
            self.end_headers()
            self.wfile.write(raw)

        def path_only(self):
            path = urlsplit(self.path).path
            # Supervisor normally strips its prefix. Also handle proxies that
            # preserve it, without trusting this header for authentication.
            prefix = self.headers.get("X-Ingress-Path", "").rstrip("/")
            if prefix and path.startswith(prefix + "/"):
                path = path[len(prefix):]
            return path

        def do_GET(self):
            if not self.allowed():
                return self.send(dict(error="Use Home Assistant to open this app."), 403)
            path = self.path_only()
            if path == "/api/state":
                return self.send(app.snapshot())
            if path == "/api/rules":
                with app.lock:
                    return self.send(app.rules)
            files = {"/": ("index.html", "text/html; charset=utf-8"),
                     "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                     "/style.css": ("style.css", "text/css; charset=utf-8")}
            if path in files:
                name, mime = files[path]
                raw = (ROOT / "web" / name).read_bytes()
                if name == "index.html":
                    raw = raw.replace(b"__CSRF__", app.csrf.encode())
                return self.send(raw, content_type=mime)
            self.send(dict(error="Not found"), 404)

        def do_POST(self):
            if not self.allowed() or not secrets.compare_digest(self.headers.get("X-Etherlighting-CSRF", ""), app.csrf):
                return self.send(dict(error="Reload the app before saving changes."), 403)
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.send(dict(error="Expected JSON"), 415)
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 512_000:
                    raise ValueError("Invalid request size")
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError("Expected a JSON object")
                result = app.action(self.path_only(), body)
                self.send(result)
            except Exception as error:
                if self.path_only() not in ("/api/presets", "/api/settings"):
                    app.handle_failure(error)
                self.send(dict(error=str(error)), 400)

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--queue")
    parser.add_argument("--data", default="/data")
    parser.add_argument("--port", type=int, default=8099)
    args = parser.parse_args()
    data = Path(args.data)
    options = json.loads((data / "options.json").read_text()) if (data / "options.json").exists() else {}
    if args.queue and not args.local:
        raise ValueError("The temporary connection is available only in local preview mode.")
    switch = ReadOnlyQueue(args.queue) if args.queue else SSHSwitch(options)
    app = Application(data, options, switch)
    server = ThreadingHTTPServer(("127.0.0.1" if args.local else "0.0.0.0", args.port), handler_for(app, args.local))
    worker = threading.Thread(target=app.poll, daemon=True)
    worker.start()

    def stop(*_):
        app.quit.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server.serve_forever()
    finally:
        app.quit.set()
        worker.join(timeout=25)
        with app.lock:
            if app.active:
                try:
                    app.restore()
                except Exception:
                    print("LED restoration pending. Reconnect and use Stop & restore.", flush=True)
            switch.close()
        server.server_close()


if __name__ == "__main__":
    main()
