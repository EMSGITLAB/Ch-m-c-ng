"""Loopback-only transport fault injection for the disposable kiosk test server."""

import hashlib
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx


class QuietDisconnectServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        if not isinstance(sys.exception(), (ConnectionResetError, BrokenPipeError, TimeoutError)):
            super().handle_error(request, client_address)


class KioskFaultProxy:
    def __init__(self, upstream_port):
        self.mode = None
        self.claimed, self.injected, self.durable, self.new_events = set(), set(), set(), set()
        self.lock = threading.Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_):
                pass  # Never log cookies, image bodies or request parameters.

            def dispatch(self):
                self.connection.settimeout(15)
                if not self.path.startswith("/api/kiosk/") or ".." in self.path or "\\" in self.path:
                    self.send_error(400)
                    return
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    self.send_error(400)
                    return
                if not 0 <= size <= 2_000_000:
                    self.send_error(413)
                    return
                body = self.rfile.read(size)
                headers = {name: self.headers[name] for name in
                    ("Content-Type", "Cookie", "X-Kiosk-Intent", "X-Capture-Nonce") if name in self.headers}
                tag = hashlib.sha256(headers.get("Cookie", "").encode()).hexdigest()
                mode = owner.mode
                eligible = self.command == "POST" and (
                    (mode == "before_start" and self.path.endswith("/recognition/sessions"))
                    or (mode == "after_commit" and self.path.endswith("/commit"))
                    or (mode == "after_frame" and "/frames/" in self.path))
                with owner.lock:
                    fault = eligible and tag not in owner.claimed
                    if fault:
                        owner.claimed.add(tag)
                if fault and mode == "before_start":
                    with owner.lock:
                        owner.injected.add(tag)
                    self.disconnect()
                    return
                try:
                    with httpx.Client(base_url=f"http://127.0.0.1:{upstream_port}", timeout=15, trust_env=False) as client:
                        response = client.request(self.command, self.path, headers=headers, content=body)
                        if fault and response.status_code == 200:
                            if mode == "after_commit":
                                receipt = response.json()
                                check = client.get("/api/kiosk/recognition/sessions/" + receipt["request_id"],
                                                   headers=headers)
                                if (check.status_code != 200 or check.json().get("state") != "used"
                                        or check.json().get("receipt") != receipt):
                                    raise ValueError("Commit was not durably queryable before response loss")
                                with owner.lock:
                                    owner.durable.add(tag)
                                    if receipt.get("status") == "recorded":
                                        owner.new_events.add(tag)
                            with owner.lock:
                                owner.injected.add(tag)
                            self.disconnect()
                            return
                    self.send_response(response.status_code)
                    self.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
                    self.send_header("Content-Length", str(len(response.content)))
                    self.end_headers()
                    self.wfile.write(response.content)
                except (OSError, httpx.HTTPError, ValueError, KeyError):
                    self.disconnect()

            def disconnect(self):
                self.close_connection = True
                try:
                    self.connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

            do_GET = dispatch
            do_POST = dispatch

        self.server = QuietDisconnectServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
        self.thread.start()

    def arm(self, mode):
        if mode not in {"before_start", "after_commit", "after_frame"}:
            raise ValueError("Unsupported transport fault")
        with self.lock:
            self.mode = mode
            self.claimed.clear()
            self.injected.clear()
            self.durable.clear()
            self.new_events.clear()

    def snapshot(self):
        with self.lock:
            return {"mode": self.mode, "connections_dropped": len(self.injected),
                    "durable_receipts_confirmed_before_drop": len(self.durable),
                    "new_events_confirmed_before_drop": len(self.new_events)}

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
