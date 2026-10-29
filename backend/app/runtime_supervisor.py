"""Local native supervisor. State files never authorize killing an arbitrary PID."""

import ctypes
import json
import logging
import os
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import uuid4


class AlreadyRunning(RuntimeError):
    pass


class FileLease:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = path.open("a+b")
        if self.file.seek(0, 2) == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.file.close()
            raise AlreadyRunning("A supervisor already owns this runtime") from error

    def close(self):
        self.file.close()


class ProcessJob:
    """Windows closes the owned process tree if the supervisor dies."""

    def __init__(self, process):
        self.handle = None
        if os.name != "nt":
            return
        from ctypes import wintypes as w

        class Basic(ctypes.Structure):
            _fields_ = [("user", ctypes.c_longlong), ("job_user", ctypes.c_longlong), ("flags", w.DWORD),
                        ("minimum", ctypes.c_size_t), ("maximum", ctypes.c_size_t), ("active", w.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in ("read", "write", "other", "rb", "wb", "ob")]

        class Extended(ctypes.Structure):
            _fields_ = [("basic", Basic), ("io", IO), ("process_limit", ctypes.c_size_t),
                        ("job_limit", ctypes.c_size_t), ("peak_process", ctypes.c_size_t),
                        ("peak_job", ctypes.c_size_t)]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes, kernel.CreateJobObjectW.restype = [ctypes.c_void_p, w.LPCWSTR], w.HANDLE
        kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        kernel.SetInformationJobObject.restype = w.BOOL
        kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        kernel.AssignProcessToJobObject.restype = w.BOOL
        kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [w.HANDLE], w.BOOL
        handle = kernel.CreateJobObjectW(None, None)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if (not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits))
                or not kernel.AssignProcessToJobObject(handle, int(process._handle))):
            error = ctypes.get_last_error()
            kernel.CloseHandle(handle)
            raise ctypes.WinError(error)
        self.handle, self.kernel = handle, kernel

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def read_state(runtime):
    try:
        return json.loads((Path(runtime) / "service-state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def service_status(runtime):
    try:
        lease = FileLease(Path(runtime) / "service.lock")
    except AlreadyRunning:
        return read_state(runtime) | {"running": True}
    lease.close()
    return read_state(runtime) | {"running": False}


def request_stop(runtime, timeout=15):
    runtime = Path(runtime)
    status = service_status(runtime)
    if not status["running"]:
        return True
    nonce = status.get("instance_nonce")
    if not nonce:
        return False
    (runtime / "service-stop.json").write_text(json.dumps({"instance_nonce": nonce}), encoding="utf-8")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not service_status(runtime)["running"]:
            return True
        time.sleep(0.2)
    return False


class Supervisor:
    def __init__(self, root, runtime, port=8000, restart_delay=1):
        self.root, self.runtime = Path(root).resolve(), Path(runtime).resolve()
        self.port, self.restart_delay = port, restart_delay
        self.instance = uuid4().hex
        self.logger = logging.getLogger("chamcong.supervisor." + self.instance)
        self.logger.propagate = False
        self.runtime.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(self.runtime / "service.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

    def write_state(self, **values):
        state = {"instance_nonce": self.instance, "supervisor_pid": os.getpid(), "port": self.port,
                 "updated_at": datetime.now(UTC).isoformat(), **values}
        path = self.runtime / "service-state.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state), encoding="utf-8")
        for _ in range(5):
            try:
                temporary.replace(path)
                return
            except PermissionError:
                time.sleep(0.02)
        raise OSError("Cannot persist supervisor state")

    def stopping(self):
        try:
            value = json.loads((self.runtime / "service-stop.json").read_text(encoding="utf-8"))
            return value.get("instance_nonce") == self.instance
        except (OSError, ValueError):
            return False

    def run(self):
        lease = FileLease(self.runtime / "service.lock")
        child, job, restarts = None, None, 0
        try:
            with socket.socket() as probe:
                try:
                    probe.bind(("127.0.0.1", self.port))
                except OSError:
                    self.logger.error("port_busy")
                    return 3
            self.write_state(state="starting", restart_count=0)
            self.logger.info("supervisor_started")
            while not self.stopping():
                command = [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", str(self.root / "backend"),
                           "--host", "127.0.0.1", "--port", str(self.port), "--workers", "1",
                           "--no-access-log", "--log-level", "critical"]
                child = subprocess.Popen(command, cwd=self.root, stdin=subprocess.DEVNULL,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                try:
                    job = ProcessJob(child)
                except OSError:
                    child.terminate()
                    child.wait(timeout=10)
                    self.logger.error("process_job_failed")
                    return 4
                self.write_state(state="running", child_pid=child.pid, restart_count=restarts)
                self.logger.info("backend_started restart_count=%d", restarts)
                began = time.monotonic()
                while child.poll() is None and not self.stopping():
                    time.sleep(0.2)
                if self.stopping():
                    break
                exit_code = child.wait()
                job.close()
                job = None
                restarts += 1
                self.logger.warning("backend_exited exit_code=%d restart_count=%d", exit_code, restarts)
                self.write_state(state="restarting", restart_count=restarts, exit_code=exit_code)
                delay = self.restart_delay if time.monotonic() - began > 10 else min(30, self.restart_delay * 2 ** min(restarts - 1, 5))
                until = time.monotonic() + delay
                while time.monotonic() < until and not self.stopping():
                    time.sleep(0.1)
            return 0
        finally:
            if child and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
            if job:
                job.close()
            self.write_state(state="stopped", restart_count=restarts)
            self.logger.info("supervisor_stopped")
            for handler in self.logger.handlers[:]:
                handler.close()
                self.logger.removeHandler(handler)
            lease.close()
