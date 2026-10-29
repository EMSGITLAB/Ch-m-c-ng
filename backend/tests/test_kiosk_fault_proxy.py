import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

spec = importlib.util.spec_from_file_location(
    "kiosk_fault_proxy_script", Path(__file__).resolve().parents[2] / "scripts/kiosk_fault_proxy.py")
proxy_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy_module)


@pytest.mark.parametrize("mode,path", [
    ("before_start", "/api/kiosk/recognition/sessions"),
    ("after_frame", "/api/kiosk/recognition/sessions/request/frames/1"),
    ("after_commit", "/api/kiosk/attendance/request/commit")])
def test_proxy_drops_actual_connection_once_and_preserves_retry(mode, path):
    calls = []
    receipt = {"request_id": "request", "event_id": "fixture-event", "status": "recorded"}

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            calls.append(self.path)
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.respond(receipt if self.path.endswith("/commit") else {"frame_accepted": True})

        def do_GET(self):
            self.respond({"state": "used", "receipt": receipt})

        def respond(self, value):
            content = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
    thread.start()
    proxy = proxy_module.KioskFaultProxy(server.server_port)
    proxy.arm(mode)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{proxy.port}", timeout=3) as client:
            with pytest.raises(httpx.RemoteProtocolError):
                client.post(path, json={}, headers={"Cookie": "chamcong_kiosk=disposable-test-cookie"})
            assert len(calls) == (0 if mode == "before_start" else 1)
            assert client.post(path, json={}, headers={"Cookie": "chamcong_kiosk=disposable-test-cookie"}).status_code == 200
            assert len(calls) == (1 if mode == "before_start" else 2)
            assert client.get("/outside-allowed-scope").status_code == 400
        assert proxy.snapshot() == {"mode": mode, "connections_dropped": 1,
            "durable_receipts_confirmed_before_drop": int(mode == "after_commit"),
            "new_events_confirmed_before_drop": int(mode == "after_commit")}
    finally:
        proxy.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
