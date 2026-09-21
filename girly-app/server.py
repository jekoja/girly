#!/usr/bin/env python3
"""Girly 🌸 — a private, reassuring menstrual cycle tracker.

Python powers the core: it serves the web frontend, owns accounts & sessions,
computes cycle predictions, and exposes the admin console API. The AI
companion (assistant/server.py) runs in a background thread of this same
process, so a single command starts everything:

    python3 server.py

Environment variables (all optional):
    GIRLY_ADDR       bind address, e.g. ":8080" or "0.0.0.0:8080" (default ":8080")
    PORT             bind port when GIRLY_ADDR is unset (Render sets this)
    GIRLY_DATA       path to the JSON store (default data/girly.json)
    GIRLY_WEB        frontend root (default web/)
    GIRLY_ASSISTANT  companion service URL (default http://127.0.0.1:3000)

    Optional AI layer for the companion (answers health & hygiene questions;
    without a key it falls back to the built-in knowledge base):
    GEMINI_API_KEY     enables Gemini (default gemini-3.1-flash-lite)
    ANTHROPIC_API_KEY  enables Anthropic instead (default claude-sonnet-5)
    GIRLY_AI_PROVIDER  force "gemini" or "anthropic" when both keys are set
    GIRLY_AI_API_KEY   generic key, paired with GIRLY_AI_PROVIDER
    GIRLY_AI_MODEL     override the model
    GIRLY_AI_API_URL   override the API endpoint ({model} is substituted)
"""

import json
import mimetypes
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from handlers import ApiError, App
from store import Store

BODY_LIMIT = 1 << 23  # 8 MiB — room for base64-encoded attachment uploads

GET_ROUTES = {
    "/api/me": App.api_me,
    "/api/dashboard": App.api_dashboard,
    "/api/calendar": App.api_calendar,
    "/api/admin/stats": App.api_admin_stats,
    "/api/admin/users": App.api_admin_users,
    "/api/admin/audit": App.api_admin_audit,
    "/api/admin/telemetry": App.api_admin_telemetry,
}

POST_ROUTES = {
    "/api/register": App.api_register,
    "/api/login": App.api_login,
    "/api/logout": App.api_logout,
    "/api/logs": App.api_logs,
    "/api/period": App.api_period,
    "/api/mode": App.api_mode,
    "/api/chat": App.api_chat,
    "/api/profile/avatar": App.api_profile_avatar,
    "/api/profile/password": App.api_profile_password,
    "/api/attachments": App.api_attachments,
    "/api/admin/users/reset": App.api_admin_reset,
    "/api/admin/users/revoke": App.api_admin_revoke,
    "/api/admin/users/delete": App.api_admin_delete,
}


class GirlyRequestHandler(BaseHTTPRequestHandler):
    server_version = "Girly/1.0"

    @property
    def app(self):
        return self.server.app

    @property
    def web_root(self):
        return self.server.web_root

    # ---- replies ----

    def _send_json(self, status, payload, extra_headers=()):
        body = (json.dumps(payload) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for key, value in extra_headers:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status, message):
        self._send_json(status, {"error": message})

    # ---- request parsing ----

    def _read_body(self):
        """A JSON request body (≤ 1 MiB), or {} — raises ApiError(400) on junk."""
        try:
            length = min(int(self.headers.get("Content-Length", 0) or 0), BODY_LIMIT)
            raw = self.rfile.read(length) if length > 0 else b""
            return json.loads(raw) if raw else {}
        except (ValueError, json.JSONDecodeError):
            raise ApiError(400, "invalid request body")

    def _dispatch(self, method):
        parts = urlsplit(self.path)
        path = parts.path
        query = parse_qs(parts.query)

        # stored chat attachments (owner or admin only)
        if method == "GET" and path.startswith("/api/attachments/"):
            self._serve_attachment(path)
            return

        if path.startswith("/api/"):
            route = (GET_ROUTES if method == "GET" else POST_ROUTES).get(path)
            if route is None:
                self._send_error_json(404, "not found")
                return
            start = time.monotonic()
            try:
                body = self._read_body() if method == "POST" else {}
                status, payload, extra_headers = route(self.app, body, query, self.headers)
                self._send_json(status, payload, extra_headers)
            except ApiError as err:
                self._send_error_json(err.status, err.message)
            elapsed = (time.monotonic() - start) * 1000
            print(f"[girly] {method} {path} ({elapsed:.1f}ms)")
            return

        if method == "GET":
            self._serve_static(path)
        else:
            self._send_error_json(404, "not found")

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ---- static files ----

    def _safe_join(self, path):
        root = os.path.abspath(self.web_root)
        full = os.path.normpath(os.path.join(root, path.lstrip("/")))
        if full == root or full.startswith(root + os.sep):
            return full
        return None

    def _serve_static(self, path):
        if path == "/":
            path = "/index.html"
        full = self._safe_join(path)
        if full is None or not os.path.isfile(full):
            # fall back to index for unknown routes
            full = os.path.join(self.web_root, "index.html")

        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in (
            "application/javascript",
            "application/json",
            "image/svg+xml",
        ):
            ctype += "; charset=utf-8"

        with open(full, "rb") as f:
            body = f.read()
        # Static files (and API responses) are never cached, so UI and data
        # changes always show on refresh.
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # ---- stored attachments ----

    def _serve_attachment(self, path):
        user = self.app.current_user(self.headers)
        if user is None:
            self._send_error_json(401, "not signed in")
            return
        rel = path[len("/api/attachments/"):]
        owner_id, _, fname = rel.partition("/")
        if not fname or "/" in fname or ".." in rel:
            self._send_error_json(404, "not found")
            return
        if user.get("id") != owner_id and user.get("role") != "admin":
            self._send_error_json(403, "that attachment belongs to another member")
            return
        root = os.path.abspath(os.path.join(self.app.data_dir, "attachments"))
        full = os.path.abspath(os.path.join(root, owner_id, fname))
        if not full.startswith(root + os.sep) or not os.path.isfile(full):
            self._send_error_json(404, "not found")
            return

        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        with open(full, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # API requests are logged with timing in _dispatch


def parse_addr():
    """Resolve the bind address from GIRLY_ADDR / PORT / default ":8080"."""
    addr = os.environ.get("GIRLY_ADDR", "")
    if not addr:
        port = os.environ.get("PORT", "8080")
        return "0.0.0.0", int(port)
    host, _, port = addr.rpartition(":")
    if not host:
        host = "0.0.0.0"
    return host.strip("[]"), int(port)


def start_companion():
    """Run the assistant service (assistant/server.py) in a daemon thread, the
    way run.sh used to as a separate process. If port 3000 is already serving
    (someone started the companion themselves), just use that one."""
    try:
        from assistant.server import PORT as companion_port
        from assistant.server import Handler as CompanionHandler
    except ImportError as err:
        print(f"[girly] companion service unavailable: {err}")
        return

    try:
        companion = ThreadingHTTPServer(("127.0.0.1", companion_port), CompanionHandler)
    except OSError:
        print(f"[girly] companion port {companion_port} already in use — reusing it")
        return

    thread = threading.Thread(
        target=companion.serve_forever, name="companion", daemon=True
    )
    thread.start()
    print(f"   companion: http://127.0.0.1:{companion_port} (in-process)")


def main():
    # Defaults are relative to the working directory; override with env vars
    # if needed.
    data_path = os.environ.get("GIRLY_DATA", "data/girly.json")
    data_dir = os.path.dirname(data_path) or "."
    try:
        os.makedirs(data_dir, exist_ok=True)
        store = Store.load(data_path)
    except OSError as err:
        print("[girly] could not load store:", err)
        sys.exit(1)

    web_root = os.environ.get("GIRLY_WEB", "web")
    if not os.path.isdir(web_root):
        alt = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
        if os.path.isdir(alt):
            web_root = alt

    host, port = parse_addr()
    assistant_url = os.environ.get("GIRLY_ASSISTANT", "http://127.0.0.1:3000")
    app = App(store, assistant_url, data_dir)

    start_companion()

    print(f"🌸 Girly is listening on http://localhost:{port}")
    print(f"   frontend : {web_root}")
    print(f"   store    : {data_path}")
    print(f"   companion: {assistant_url}")

    httpd = ThreadingHTTPServer((host, port), GirlyRequestHandler)
    httpd.app = app
    httpd.web_root = web_root
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[girly] shutting down — bye 💜")


if __name__ == "__main__":
    main()
