"""Restore an encrypted real backup into a disposable database; leave the live DB untouched."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import pyodbc
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import get_settings  # noqa: E402
from app.database import session_factory  # noqa: E402
from app.models import AttendanceEvent, Employee, FaceTemplate, ImportedFacePhoto  # noqa: E402
from app.native_backup import MARKER, RECOVERY_NAME, connection_string, restore_new_database  # noqa: E402
from app.revocation_ledger import read_ledger  # noqa: E402


def counts(db):
    return {model.__tablename__: db.scalar(select(func.count()).select_from(model))
            for model in (Employee, FaceTemplate, ImportedFacePhoto, AttendanceEvent)}


settings = get_settings()
metadata = json.loads((settings.runtime_dir / "backups/last-backup.json").read_text(encoding="utf-8"))
archive = Path(metadata["archive_path"])
if hashlib.sha256(archive.read_bytes()).hexdigest() != metadata["cipher_sha256"]:
    raise ValueError("Encrypted backup differs from the verified backup marker")
with session_factory()() as db:
    before = counts(db)
name = "ChamCong_RecoveryCheck_" + uuid4().hex[:8]
created, engine = False, None
started = perf_counter()
try:
    result = restore_new_database(archive, target_name=name)
    created = True
    root = Path(result["app_root"])
    url = URL.create("mssql+pyodbc", query={"odbc_connect": connection_string(name)}).render_as_string(hide_password=False)
    engine = create_engine(url, hide_parameters=True)
    with Session(engine) as db:
        restored = counts(db)
        assert result["backup_snapshot_counts_verified"], "Create a fresh snapshot with verified row counts first"
        # New attendance after a backup belongs to the next snapshot, not the old one.
        assert restored["attendance_events"] == result["attendance_events_preserved"]
        assert restored["employees"] <= before["employees"]
        for subject, revision in read_ledger(settings.runtime_dir).items():
            assert db.scalar(select(func.count()).select_from(FaceTemplate).where(
                FaceTemplate.employee_id == subject, FaceTemplate.biometric_revision < revision)) == 0
    duplicate_refused = False
    try:
        restore_new_database(archive, target_name=name)
    except ValueError:
        duplicate_refused = True
    assert duplicate_refused
    env = {key: value for key, value in os.environ.items() if not key.startswith("CHAMCONG_")}
    env["PYTHONIOENCODING"] = "utf-8"
    code = '''
import sys
sys.path.insert(0,"backend")
from app.main import app
from app.config import get_settings
from fastapi.testclient import TestClient
assert sys.argv[1] in get_settings().database_url
assert not get_settings().functional_trial_enabled
with TestClient(app) as client:
    assert client.get("/").status_code==200
    health=client.get("/health/ready").json()
    assert health["database"] and health["recognition"] and not health["attendance_enabled"]
    assert client.get("/api/auth/setup").json()["requires_setup"] is False
    assert client.get("/api/admin/operations/status").status_code==401
print("Recovered app, models, database and private configuration passed; old access remains disabled")
'''
    smoke = subprocess.run([sys.executable, "-c", code, name], cwd=root, env=env, capture_output=True,
                           text=True, encoding="utf-8", timeout=60)
    (settings.runtime_dir / "backups/recovered-app-check.log").write_text(smoke.stdout + smoke.stderr, encoding="utf-8")
    if smoke.returncode:
        print((smoke.stdout + smoke.stderr)[-4000:])
        raise RuntimeError("Recovered application check failed")
    with session_factory()() as db:
        assert counts(db) == before
    report = {"encrypted_archive_bytes": metadata["archive_bytes"], "checksum_and_authentication_verified": True,
              "restored_into_new_isolated_database": True, "existing_target_refused": True,
              "backup_snapshot_counts_verified_before_recovery_guard": True,
              "source_counts_unchanged": True, "restored_counts_match_backup": True,
              "models_config_key_and_compiled_frontend_restored": True,
              "deletion_ledger_applied": True, "old_sessions_kiosk_tokens_and_policies_disabled": True,
              "local_drill_seconds": round(perf_counter() - started, 2),
              "external_storage_confirmed": metadata.get("external_storage_confirmed", False), "physical_vm_restore_tested": False,
              "identities_images_vectors_in_evidence": False}
    (ROOT / "evidence/m5/backup-restore-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
finally:
    if engine:
        engine.dispose()
    if created:
        assert RECOVERY_NAME.fullmatch(name)
        with pyodbc.connect(connection_string("master"), autocommit=True) as admin:
            cursor = admin.cursor()
            marker = cursor.execute(f"SELECT CAST(value AS nvarchar(100)) FROM [{name}].sys.extended_properties "
                                     "WHERE class=0 AND name=N'chamcong_project'").fetchval()
            if marker != MARKER:
                raise RuntimeError("Refusing to clean a recovery DB with mismatched ownership")
            cursor.execute(f"ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
            cursor.execute(f"DROP DATABASE [{name}]")
