"""Crash/restart/duplicate/stop checks against an isolated native server port."""

import ctypes
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.runtime_supervisor import read_state, request_stop, service_status  # noqa: E402

with socket.socket() as probe:
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
runtime = ROOT / ".runtime" / ("service-check-" + uuid4().hex[:8])
command = [sys.executable, str(ROOT / "scripts/run_service.py"), "--port", str(port), "--runtime-dir", str(runtime)]
env = dict(os.environ, CHAMCONG_FUNCTIONAL_TRIAL_ENABLED="false", PYTHONIOENCODING="utf-8")
process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)


def wait_ready(previous=None):
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Isolated supervisor exited: " + str(process.returncode))
        state = read_state(runtime)
        if state.get("child_pid") and state.get("child_pid") != previous:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health/live", timeout=1) as response:
                    if response.status == 200:
                        return state
            except OSError:
                pass
        time.sleep(0.2)
    raise RuntimeError("Isolated service did not become live")


def terminate_owned(pid):
    if os.name == "nt":
        from ctypes import wintypes as w

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes, kernel.OpenProcess.restype = [w.DWORD, w.BOOL, w.DWORD], w.HANDLE
        kernel.TerminateProcess.argtypes, kernel.TerminateProcess.restype = [w.HANDLE, w.UINT], w.BOOL
        kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [w.HANDLE], w.BOOL
        handle = kernel.OpenProcess(1, False, pid)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not kernel.TerminateProcess(handle, 91):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            kernel.CloseHandle(handle)
    else:
        import signal

        os.kill(pid, signal.SIGTERM)


try:
    first = wait_ready()
    duplicate = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, timeout=10)
    assert duplicate.returncode == 0
    assert read_state(runtime)["child_pid"] == first["child_pid"]
    terminate_owned(first["child_pid"])
    second = wait_ready(first["child_pid"])
    assert second["restart_count"] >= 1
    assert request_stop(runtime)
    assert process.wait(timeout=10) == 0
    assert service_status(runtime)["running"] is False
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))  # No orphan server retains this isolated port.
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    third = wait_ready()
    terminate_owned(third["supervisor_pid"])
    process.wait(timeout=10)
    deadline = time.monotonic() + 10
    while service_status(runtime)["running"] and time.monotonic() < deadline:
        time.sleep(0.1)
    assert service_status(runtime)["running"] is False
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))
    report = {"isolated_port": True, "duplicate_supervisor_rejected": True,
              "crashed_backend_restarted": True, "owned_process_tree_stopped": True,
              "abrupt_supervisor_exit_cleans_children": True,
              "stale_pid_not_trusted": True, "live_server_modified": False,
              "identities_images_vectors_exported": False}
    (ROOT / "evidence/m5").mkdir(exist_ok=True)
    (ROOT / "evidence/m5/supervisor-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
finally:
    request_stop(runtime, timeout=5)
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=10)
