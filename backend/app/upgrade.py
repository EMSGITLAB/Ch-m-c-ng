"""Validate an upgrade on a recovered NEW database; preserve source and compatible rollback."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

from .native_backup import restore_new_database
from .private_storage import protect_directory

CONTRACT = "authenticated-v2-external-deletion-ledger"


def verify_candidate(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "release-manifest.json").read_text(encoding="utf-8"))
    if (manifest.get("schema") != 1 or manifest.get("private_data_included") is not False
            or manifest.get("recovery_contract") != CONTRACT or not manifest.get("offline_wheels_included")):
        raise ValueError("Candidate lacks the required private-data, offline and recovery contracts")
    files = manifest.get("files")
    required = {"backend/app/main.py", "backend/app/native_backup.py", "backend/requirements.lock",
                "backend/alembic.ini", "models/manifest.json", "frontend/dist/index.html", "scripts/run_service.py"}
    if not isinstance(files, dict) or not required <= set(files):
        raise ValueError("Candidate is missing required public files")
    for name, digest in files.items():
        relative = PurePosixPath(name)
        path = (directory / name).resolve()
        if (not relative.parts or relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name
                or not path.is_relative_to(directory) or path.name == ".env"
                or path.suffix.lower() in {".key", ".cckey", ".ccbackup", ".bak", ".mdf", ".ldf"}
                or relative.parts[0] in {"data", "evidence", "logs", ".runtime"}):
            raise ValueError("Unsafe/private candidate path")
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Candidate checksum mismatch")
    if not any(name.startswith("wheels/") and name.endswith(".whl") for name in files):
        raise ValueError("Candidate has no offline wheels")
    return directory, manifest


def clean_env():
    return {key: value for key, value in os.environ.items() if not key.startswith("CHAMCONG_")} | {
        "PYTHONIOENCODING": "utf-8"}


def run_step(root, command, name):
    result = subprocess.run(command, cwd=root, env=clean_env(), capture_output=True,
                            text=True, encoding="utf-8", timeout=240)
    logs = root / ".runtime/upgrade"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / (name+".log")).write_text(result.stdout+result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError("Upgrade step failed: "+name)


def offline_install(root, wheels):
    python = root / ".venv/Scripts/python.exe"
    if python.exists():
        raise ValueError("Upgrade checks require a fresh virtual environment")
    run_step(root, [sys.executable, "-m", "venv", str(root / ".venv")], "venv")
    run_step(root, [str(python), "-m", "pip", "install", "--no-index", "--find-links", str(wheels),
                    "-r", "backend/requirements.lock", "--disable-pip-version-check"], "offline-install")
    return python


def smoke(root, python, database_name):
    code = '''
import sys
sys.path.insert(0,"backend")
from sqlalchemy import text
from app.main import app
from app.database import get_engine
from fastapi.testclient import TestClient
with get_engine().connect() as db:
    assert db.scalar(text("SELECT DB_NAME()")) == sys.argv[1]
with TestClient(app) as client:
    assert client.get("/").status_code == 200
    state=client.get("/api/system/status").json()
    assert state["recognition_ready"] and not state["attendance_enabled"]
    assert client.get("/api/admin/operations/status").status_code == 401
    for path in ("/.env","/backend/app/models.py","/models/manifest.json"):
        assert client.get(path).status_code == 404
print("Isolated recovered application and models ready; old credentials and policy remain disabled")
'''
    run_step(root, [str(python), "-c", code, database_name], "app-smoke")


def migrate(root, python):
    run_step(root, [str(python), "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"], "migration")


def stage(archive, release, *, key_path=None, key_password=None, rollback_wheels=None, _migrate=migrate):
    release, manifest = verify_candidate(release)
    wheels = Path(rollback_wheels).resolve() if rollback_wheels else release / "wheels"
    original = restore_new_database(archive, key_path=key_path, key_password=key_password)
    original_root = Path(original["app_root"])
    old_python = offline_install(original_root, wheels)
    smoke(original_root, old_python, original["database_name"])
    candidate = original_root / ".runtime/upgrade-candidate"
    protect_directory(candidate)
    for name in manifest["files"]:
        if name.startswith("wheels/") or name in {"config/business.json", "config/server.env.example"}:
            continue
        target = candidate / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(release / name, target)
    for name in (".env", "config/business.json", ".runtime/keys/backup.key", ".runtime/privacy/revocations.fernet"):
        target = candidate / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original_root / name, target)
    report = {"source_database_modified": False, "traffic_switched": False, "validation_only": True,
              "candidate_app_root": str(candidate), "candidate_database_name": original["database_name"],
              "old_app_offline_install_and_smoke_passed": True, "business_config_preserved": True,
              "encrypted_archive_not_modified": True}
    try:
        python = offline_install(candidate, release / "wheels")
        _migrate(candidate, python)
        smoke(candidate, python, original["database_name"])
        report |= {"staged": True, "candidate_smoke_passed": True, "rollback_needed": False}
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        # The migration may have left partial DDL. Never point the old app at that database.
        restored = restore_new_database(archive, key_path=key_path, key_password=key_password)
        rollback_root = Path(restored["app_root"])
        python = offline_install(rollback_root, wheels)
        smoke(rollback_root, python, restored["database_name"])
        report |= {"staged": False, "failure_type": type(error).__name__, "rollback_needed": True,
                   "rollback_app_root": str(rollback_root), "rollback_database_name": restored["database_name"],
                   "compatible_rollback_offline_install_and_smoke_passed": True}
    marker = original_root / ".runtime/upgrade-result.json"
    marker.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
