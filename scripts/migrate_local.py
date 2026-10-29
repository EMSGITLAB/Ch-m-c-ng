"""Back up the marked local project DB before applying migrations."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pyodbc
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import get_settings  # noqa: E402

url = make_url(get_settings().database_url)
if url.get_backend_name() != "mssql":
    raise RuntimeError("This helper requires the marked local SQL Server database")
connection_string = url.query.get("odbc_connect")
if not connection_string:
    raise RuntimeError("This helper requires a local ODBC connection")
with pyodbc.connect(connection_string, autocommit=True) as connection:
    cursor = connection.cursor()
    if cursor.execute("SELECT DB_NAME()").fetchval() != "ChamCongFaceLocal":
        raise RuntimeError("Refusing to migrate an unrelated database")
    marker = cursor.execute("SELECT CAST(value AS nvarchar(100)) FROM sys.extended_properties WHERE class=0 AND name=N'chamcong_project'").fetchval()
    if marker != "chamcong-face-local":
        raise RuntimeError("Database project marker mismatch")
    directory = cursor.execute("SELECT CAST(SERVERPROPERTY('InstanceDefaultBackupPath') AS nvarchar(500))").fetchval()
    backup = str(Path(directory) / ("chamcong_before_migration_" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8] + ".bak"))
    cursor.execute("BACKUP DATABASE [ChamCongFaceLocal] TO DISK=? WITH INIT,COPY_ONLY,CHECKSUM", backup)
    while cursor.nextset():
        pass
    cursor.execute("RESTORE VERIFYONLY FROM DISK=? WITH CHECKSUM", backup)
    while cursor.nextset():
        pass
private = ROOT / ".runtime/backups"
private.mkdir(parents=True, exist_ok=True)
(private / "last-pre-migration-backup.json").write_text(json.dumps({"backup_path": backup, "checksum_verified": True}, indent=2), encoding="utf-8")
result = subprocess.run([sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"], cwd=ROOT,
    env=dict(os.environ, PYTHONIOENCODING="utf-8"), capture_output=True, text=True, encoding="utf-8", errors="replace")
(ROOT / ".runtime/migration.log").write_text(result.stdout + result.stderr, encoding="utf-8")
if result.returncode:
    print((result.stdout + result.stderr)[-5000:])
    raise SystemExit(result.returncode)
print("Project database backed up, backup checksum verified and migrations applied")
