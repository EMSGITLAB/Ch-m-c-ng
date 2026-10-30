"""Disposable native SQL Server + webapp for UI checks, with synthetic people only.

Keep the returned session alive while testing; send 'stop' on stdin to clean up.
Never starts or changes a production attendance policy.
"""

import contextlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path

import pyodbc
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.auth import hasher  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.models import AdminUser, AttendanceEvent, Device, Employee, Shift, ShiftAssignment  # noqa: E402

for port in (8011, 5174):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))
name = "ChamCong_UICheck_" + secrets.token_hex(4)
assert re.fullmatch(r"ChamCong_UICheck_[0-9a-f]{8}", name)
private = ROOT / ".runtime/ui-check"
private.mkdir(parents=True, exist_ok=True)
connection_string = make_url(get_settings().database_url).query["odbc_connect"]
with pyodbc.connect(connection_string, autocommit=True) as admin, contextlib.ExitStack() as stack:
    cursor = admin.cursor()
    children, engine, created = [], None, False
    try:
        cursor.execute(f"CREATE DATABASE [{name}]")
        created = True
        cursor.execute(f"USE [{name}]")
        cursor.execute("EXEC sys.sp_addextendedproperty @name=N'chamcong_ui_sandbox', @value=N'disposable-synthetic-only'")
        cursor.execute("USE [master]")
        connection = re.sub(r"(?i)DATABASE=[^;]+", "DATABASE=" + name, connection_string)
        url = URL.create("mssql+pyodbc", query={"odbc_connect": connection}).render_as_string(hide_password=False)
        env = dict(os.environ, CHAMCONG_DATABASE_URL=url, CHAMCONG_SESSION_SECRET=secrets.token_urlsafe(48),
            CHAMCONG_ALLOWED_ORIGINS=json.dumps(["http://127.0.0.1:5174", "http://127.0.0.1:8011"]),
            CHAMCONG_RUNTIME_DIR=str(private / name), CHAMCONG_BACKUP_DIRECTORY=str(private / name / "backups"),
            PYTHONIOENCODING="utf-8")
        result = subprocess.run([sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"],
            cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode:
            raise RuntimeError(result.stderr[-5000:])
        engine = create_engine(url)
        with Session(engine) as db:
            db.add(AdminUser(id=1, username="ui-test", password_hash=hasher.hash("ui-check-only-123!")))
            person = Employee(code="UI0001", name="Nhân viên thử giao diện", department="Dữ liệu thử tách biệt")
            second = Employee(code="UI0002", name="Hồ sơ thử thứ hai", department="Dữ liệu thử tách biệt")
            shift = Shift(name="Ca thử giao diện", start_minute=480, end_minute=1020, rules={"breaks": [{"start_offset":240, "end_offset":300, "paid":False}]})
            device = Device(name="Thiết bị thử giao diện", direction="in")
            db.add_all([person, second, shift, device])
            db.flush()
            db.add(ShiftAssignment(employee_id=person.id, shift_id=shift.id, work_date=date(2025, 12, 31)))
            db.add(AttendanceEvent(employee_id=person.id, device_id=device.id, request_id="ui-sandbox-in",
                direction="in", server_time=datetime(2025, 12, 31, 1, tzinfo=UTC), recognition_version="synthetic-ui-test-only"))
            db.commit()
        config = private / "vite.config.mjs"
        config.write_text("import base from " + json.dumps((ROOT / "frontend/vite.config.ts").as_posix()) + ";\nexport default {...base,server:{host:'127.0.0.1',port:5174,strictPort:true,proxy:{'/api':'http://127.0.0.1:8011','/health':'http://127.0.0.1:8011'}}};\n", encoding="utf-8")
        commands = [
            [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", "8011"],
            [shutil.which("node"), "frontend/node_modules/vite/bin/vite.js", "frontend", "--config", str(config)],
        ]
        for label, command in zip(["backend", "frontend"], commands, strict=True):
            log = stack.enter_context((private / (label + ".log")).open("wb"))
            children.append(subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT))
        deadline = time.monotonic() + 45
        for target in ["http://127.0.0.1:8011/health/live", "http://127.0.0.1:5174/"]:
            while True:
                if any(child.poll() is not None for child in children):
                    raise RuntimeError("UI sandbox child exited; inspect .runtime/ui-check logs")
                try:
                    with urllib.request.urlopen(target, timeout=2) as response:
                        if response.status == 200:
                            break
                except (urllib.error.URLError, TimeoutError):
                    if time.monotonic() >= deadline:
                        raise RuntimeError("UI sandbox startup timed out") from None
                    time.sleep(0.25)
        print(json.dumps({"ready": True, "url": "http://127.0.0.1:5174/#admin", "username": "ui-test",
                          "database": name, "synthetic_only": True, "live_database_modified": False}), flush=True)
        while input().strip().lower() != "stop":
            print("Send stop to clean up this disposable UI sandbox", flush=True)
    finally:
        for child in reversed(children):
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        if engine:
            engine.dispose()
        if created:
            assert re.fullmatch(r"ChamCong_UICheck_[0-9a-f]{8}", name)
            marker = cursor.execute(f"SELECT CAST(value AS nvarchar(100)) FROM [{name}].sys.extended_properties WHERE class=0 AND name=N'chamcong_ui_sandbox'").fetchval()
            if marker != "disposable-synthetic-only":
                raise RuntimeError("UI sandbox database marker mismatch; refusing cleanup")
            cursor.execute(f"ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
            cursor.execute(f"DROP DATABASE [{name}]")
            print("Disposable UI sandbox processes stopped and synthetic database removed", flush=True)
