"""Authenticated local recovery bundles and restore into a NEW marked database only."""

import hashlib
import io
import json
import os
import re
import secrets
import shutil
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

import pyodbc
from sqlalchemy import create_engine, delete, func, select, text, update
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

from .calendar_guard import lock_calendar
from .config import PROJECT_ROOT, get_settings
from .database import session_factory
from .models import (
    AttendanceEvent,
    AuditLog,
    AuthSession,
    Device,
    DevicePairing,
    Employee,
    FaceTemplate,
    ImportedFacePhoto,
    RecognitionPolicy,
    RecognitionSession,
)
from .private_storage import MAX_PLAINTEXT, protect_directory, recovery_key, seal, unseal
from .recovery_key import MAX_FILE_BYTES, unwrap_key
from .revocation_ledger import (
    apply_to_restored_database,
    merge_ledger,
    read_ledger,
    sync_from_audit,
    validate,
)
from .storage_probe import probe as probe_storage

RECOVERY_NAME = re.compile(r"ChamCong_Recovery(?:Check|New)_[0-9a-f]{8}\Z")
MARKER = "chamcong-face-local"


def recovery_counts(db):
    return {model.__tablename__: db.scalar(select(func.count()).select_from(model))
            for model in (Employee, FaceTemplate, ImportedFacePhoto, AttendanceEvent)}


def connection_string(database=None):
    url = make_url(get_settings().database_url)
    if url.get_backend_name() != "mssql" or not url.query.get("odbc_connect"):
        raise ValueError("Native backup requires the local project ODBC connection")
    value = url.query["odbc_connect"]
    if database is not None:
        value = re.sub(r"(?i)(?:^|;)\s*(?:database|initial catalog)\s*=\s*(?:\{[^}]*\}|[^;]*)", "", value)
        value = value.strip(";") + ";DATABASE=" + database
    return value


def drain(cursor):
    while cursor.nextset():
        pass


def marked_database(cursor):
    marker = cursor.execute("SELECT CAST(value AS nvarchar(100)) FROM sys.extended_properties "
                            "WHERE class=0 AND name=N'chamcong_project'").fetchval()
    if marker != MARKER:
        raise ValueError("Refusing a database without this project's ownership marker")
    return cursor.execute("SELECT DB_NAME()").fetchval()


def sql_staging_directory(cursor):
    directory = get_settings().runtime_dir / "sql-staging"
    if os.name != "nt":
        raise ValueError("Configure a shared SQL staging directory before using native recovery on this OS")
    if not directory.exists():
        protect_directory(directory)
    account = cursor.execute("SELECT service_account FROM sys.dm_server_services "
                             "WHERE process_id=CAST(SERVERPROPERTY('ProcessID') AS int)").fetchval()
    if not account:
        raise ValueError("Cannot identify this SQL Server service account")
    result = subprocess.run(["icacls", str(directory), "/grant:r", account + ":(OI)(CI)M"], capture_output=True)
    if result.returncode:
        raise ValueError("Cannot grant this SQL service access to its private staging directory")
    return directory


def source_files(root):
    root = Path(root).resolve()
    selected = {}
    for directory, suffixes in (("backend/app", {".py"}), ("backend/migrations", {".py"}),
                                 ("models", {".onnx", ".json", ".txt", ".md"}),
                                 ("frontend/dist", None), ("frontend/src", {".ts", ".tsx", ".css"}),
                                 ("frontend/public", None)):
        for path in (root / directory).rglob("*"):
            if path.is_file() and (suffixes is None or path.suffix in suffixes):
                if not path.resolve().is_relative_to(root):
                    raise ValueError("Recovery source escapes the project")
                selected[path.relative_to(root).as_posix()] = path
    for name in ("backend/alembic.ini", "backend/requirements.lock", "config/business.json", "THIRD_PARTY_NOTICES.md"):
        selected[name] = root / name
    for name in ("run_service.py", "start_service.ps1", "start_backend.ps1", "start_local.ps1",
                 "restart_backend.ps1", "install_autostart.ps1", "setup_release.ps1", "backup_local.py",
                 "enable_functional_trial.py", "verify_functional_trial.py", "migrate_local.py", "start_sqlserver.py",
                 "stage_upgrade.py", "configure_sql_telemetry_egress.ps1", "vscode_run.ps1",
                 "import_employee_photos.py", "import_employee_dataset.py", "prepare_profile_references.py", "configure_trial_shift.py"):
        selected["scripts/" + name] = root / "scripts" / name
    selected["HUONG_DAN_VAN_HANH.md"] = root / "HUONG_DAN_VAN_HANH.md"
    for optional in (".gitignore", "AGENTS.md", "KE_HOACH_TRIEN_KHAI.md", "README.md", "pyproject.toml",
                     "backend/requirements.in", "frontend/package.json", "frontend/package-lock.json",
                     "frontend/tsconfig.json", "frontend/tsconfig.app.json", "frontend/tsconfig.node.json",
                     "frontend/vite.config.ts", "frontend/index.html"):
        if (root / optional).is_file():
            selected[optional] = root / optional
    for optional in ("settings.json", "tasks.json", "launch.json", "extensions.json"):
        relative = ".vscode/"+optional
        if (root / relative).is_file():
            selected[relative] = root / relative
    if not (root / ".env").is_file():
        raise ValueError("Private server configuration is required for recovery")
    selected["server.env"] = root / ".env"
    return selected


def validate_payload(content):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(set(names)) != len(names) or sum(entry.file_size for entry in entries) > MAX_PLAINTEXT * 2:
            raise ValueError("Invalid or oversized recovery archive")
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name or not name:
                raise ValueError("Unsafe recovery archive path")
        manifest = json.loads(archive.read("recovery-manifest.json"))
        if manifest.get("format") not in {1, 2} or manifest.get("project") != MARKER:
            raise ValueError("Unknown recovery format or project")
        if set(names) != set(manifest["files"]) | {"recovery-manifest.json"}:
            raise ValueError("Recovery file list differs from manifest")
        if not {"database.bak", "server.env", "config/business.json", "privacy/revocations.fernet"} <= set(names):
            raise ValueError("Required recovery components missing")
        for name, digest in manifest["files"].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError("Recovery checksum mismatch")
        return manifest


def create_backup(destination=None):
    settings = get_settings()
    runtime = settings.runtime_dir
    destination = Path(destination) if destination else (settings.backup_directory or runtime / "backups")
    destination.mkdir(parents=True, exist_ok=True)
    key = recovery_key(runtime, create=True)
    native_path = None
    completed = datetime.now(UTC)
    with pyodbc.connect(connection_string(), autocommit=True) as native, session_factory()() as db:
        cursor = native.cursor()
        database = marked_database(cursor)
        storage = probe_storage(cursor, PROJECT_ROOT, destination)
        lock_calendar(db)
        sync_from_audit(db, runtime, mirror_directory=destination)
        directory = sql_staging_directory(cursor)
        native_path = directory / ("chamcong_encrypted_stage_" + uuid4().hex + ".bak")
        try:
            quoted = database.replace("]", "]]")
            cursor.execute(f"BACKUP DATABASE [{quoted}] TO DISK=? WITH COPY_ONLY,CHECKSUM", str(native_path))
            drain(cursor)
            cursor.execute("RESTORE VERIFYONLY FROM DISK=? WITH CHECKSUM", str(native_path))
            drain(cursor)
            files = source_files(PROJECT_ROOT) | {"database.bak": native_path,
                                                   "privacy/revocations.fernet": runtime / "privacy/revocations.fernet"}
            manifest = {"format": 2, "project": MARKER, "created_at": completed.isoformat(),
                        "schema_revision": db.scalar(text("SELECT version_num FROM alembic_version")),
                        "row_counts": recovery_counts(db),
                        "files": {}}
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=5) as archive:
                for name, path in sorted(files.items()):
                    with path.open("rb") as source:
                        manifest["files"][name] = hashlib.file_digest(source, "sha256").hexdigest()
                    archive.write(path, name)
                archive.writestr("recovery-manifest.json", json.dumps(manifest, sort_keys=True))
            content = output.getvalue()
            validate_payload(content)
            encrypted = seal(content, key)
            archive_path = destination / ("chamcong_" + completed.strftime("%Y%m%dT%H%M%SZ_") + uuid4().hex[:8] + ".ccbackup")
            with archive_path.open("xb") as target:
                target.write(encrypted)
                target.flush()
                os.fsync(target.fileno())
            validate_payload(unseal(archive_path.read_bytes(), key))
            native_path.unlink()
            native_path = None
            metadata = {"completed_at": datetime.now(UTC).isoformat(), "encrypted": True,
                        "checksum_verified": True, "archive_path": str(archive_path.resolve()),
                        "cipher_sha256": hashlib.sha256(encrypted).hexdigest(),
                        "archive_bytes": len(encrypted), "file_count": len(manifest["files"]),
                        "source_data_modified": False, "external_storage_confirmed": storage["confirmed"],
                        "storage_verification": storage}
            marker = runtime / "backups/last-backup.json"
            marker.parent.mkdir(parents=True, exist_ok=True)
            temporary = marker.with_suffix(".tmp")
            temporary.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            temporary.replace(marker)
            (marker.parent / "last-backup-error.json").unlink(missing_ok=True)
            db.rollback()  # Release the calendar gate without changing source data.
            return metadata
        finally:
            if native_path and native_path.is_relative_to(directory) and native_path.name.startswith("chamcong_encrypted_stage_"):
                try:
                    native_path.unlink(missing_ok=True)
                except PermissionError:
                    pass  # Preserve the original failure; no success marker is written before cleanup.


def recovery_guard(db, subjects):
    affected = apply_to_restored_database(db, subjects)
    db.execute(delete(AuthSession))
    db.execute(delete(DevicePairing))
    db.execute(update(Device).values(token_hash=None, token_expires_at=None))
    db.execute(update(RecognitionPolicy).values(enabled=False))
    db.execute(update(RecognitionSession).where(RecognitionSession.state.in_(["pending", "verified"]))
               .values(state="rejected"))
    db.add(AuditLog(action="database_recovery_guard", details={"revoked_subjects_applied": affected,
                                                              "sessions_and_kiosk_tokens_revoked": True}))
    return affected


def restore_new_database(archive_path, *, key_path=None, key_password=None, target_name=None):
    """Never replace/drop an existing DB or an existing app directory."""
    settings = get_settings()
    name = target_name or "ChamCong_RecoveryNew_" + uuid4().hex[:8]
    if not RECOVERY_NAME.fullmatch(name):
        raise ValueError("Restore target must be a new, isolated recovery database name")
    recovered_root = settings.runtime_dir / "recoveries" / name
    if recovered_root.exists():
        raise ValueError("Recovery app directory already exists")
    if key_path:
        if Path(key_path).stat().st_size > MAX_FILE_BYTES:
            raise ValueError("Recovery-key file is too large")
        key = Path(key_path).read_bytes()
        if Path(key_path).suffix.lower() == ".cckey":
            if key_password is None:
                raise ValueError("A recovery-key password is required")
            key = unwrap_key(key, key_password)
    else:
        key = recovery_key(settings.runtime_dir)
    if Path(archive_path).stat().st_size > MAX_PLAINTEXT * 4 // 3 + 1024:
        raise ValueError("Encrypted recovery file is too large")
    content = unseal(Path(archive_path).read_bytes(), key)
    manifest = validate_payload(content)
    subjects = read_ledger(settings.runtime_dir)
    mirror = Path(archive_path).parent / "chamcong_revocations.fernet"
    if mirror.is_file():
        if mirror.stat().st_size > 2_000_000:
            raise ValueError("Revocation mirror is unexpectedly large")
        external = validate(json.loads(unseal(mirror.read_bytes(), key)))
        for subject, revision in external.items():
            subjects[subject] = max(subjects.get(subject, 0), revision)
    elif manifest["format"] >= 2:
        raise ValueError("Latest external deletion ledger is required beside this backup")
    native_path = None
    with pyodbc.connect(connection_string("master"), autocommit=True) as native:
        cursor = native.cursor()
        if cursor.execute("SELECT DB_ID(?)", name).fetchval() is not None:
            raise ValueError("Refusing to replace an existing database")
        backup_directory = sql_staging_directory(cursor)
        data_directory = Path(cursor.execute("SELECT CAST(SERVERPROPERTY('InstanceDefaultDataPath') AS nvarchar(500))").fetchval())
        native_path = backup_directory / ("chamcong_restore_stage_" + uuid4().hex + ".bak")
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                with archive.open("database.bak") as source, native_path.open("xb") as target:
                    shutil.copyfileobj(source, target)
                cursor.execute("RESTORE VERIFYONLY FROM DISK=? WITH CHECKSUM", str(native_path))
                drain(cursor)
                file_rows = cursor.execute("RESTORE FILELISTONLY FROM DISK=?", str(native_path)).fetchall()
                moves = []
                for index, row in enumerate(file_rows):
                    logical = row[0].replace("'", "''")
                    filename = data_directory / f"{name}_{index}.{'ldf' if row[2] == 'L' else 'mdf'}"
                    moves.append(f"MOVE N'{logical}' TO N'{str(filename).replace(chr(39), chr(39)*2)}'")
                cursor.execute(f"RESTORE DATABASE [{name}] FROM DISK=? WITH CHECKSUM, " + ", ".join(moves), str(native_path))
                drain(cursor)
                # Current local deletion ledger always takes precedence over an older backup.
                archived_subjects = validate(json.loads(unseal(archive.read("privacy/revocations.fernet"), key)))
                for subject, revision in archived_subjects.items():
                    subjects[subject] = max(subjects.get(subject, 0), revision)
                url = URL.create("mssql+pyodbc", query={"odbc_connect": connection_string(name)}).render_as_string(hide_password=False)
                engine = create_engine(url, hide_parameters=True)
                try:
                    with Session(engine) as db:
                        marker = db.scalar(text("SELECT CAST(value AS nvarchar(100)) FROM sys.extended_properties "
                                                "WHERE class=0 AND name=N'chamcong_project'"))
                        if marker != MARKER or db.scalar(text("SELECT version_num FROM alembic_version")) != manifest["schema_revision"]:
                            raise ValueError("Restored database ownership or schema mismatch")
                        before = db.scalar(select(func.count()).select_from(AttendanceEvent))
                        snapshot_counts = recovery_counts(db)
                        if "row_counts" in manifest and snapshot_counts != manifest["row_counts"]:
                            raise ValueError("Restored database differs from its backup snapshot counts")
                        affected = recovery_guard(db, subjects)
                        db.commit()
                        if before != db.scalar(select(func.count()).select_from(AttendanceEvent)):
                            raise ValueError("Recovery guard changed attendance history")
                finally:
                    engine.dispose()
                protect_directory(recovered_root)
                for member in manifest["files"]:
                    if member in {"database.bak", "server.env", "privacy/revocations.fernet"}:
                        continue
                    target = recovered_root / member
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, target.open("xb") as output:
                        shutil.copyfileobj(source, output)
                lines = archive.read("server.env").decode("utf-8").splitlines()
                prefixes = ("CHAMCONG_DATABASE_URL=", "CHAMCONG_SESSION_SECRET=", "CHAMCONG_FUNCTIONAL_TRIAL_ENABLED=",
                            "CHAMCONG_FUNCTIONAL_TRIAL_POLICY_ID=", "CHAMCONG_RUNTIME_DIR=", "CHAMCONG_MODELS_DIR=",
                            "CHAMCONG_FRONTEND_DIST_PATH=", "CHAMCONG_BUSINESS_CONFIG_PATH=", "CHAMCONG_BACKUP_DIRECTORY=")
                lines = [line for line in lines if not line.startswith(prefixes)]
                lines += ["CHAMCONG_DATABASE_URL=" + url, "CHAMCONG_SESSION_SECRET=" + secrets.token_urlsafe(48),
                          "CHAMCONG_FUNCTIONAL_TRIAL_ENABLED=false",
                          "CHAMCONG_BACKUP_DIRECTORY=" + str(Path(archive_path).parent.resolve())]
                (recovered_root / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")
                restored_runtime = recovered_root / ".runtime"
                protect_directory(restored_runtime / "keys")
                (restored_runtime / "keys/backup.key").write_bytes(key)
                merge_ledger(restored_runtime, subjects)
                return {"database_name": name, "app_root": str(recovered_root), "attendance_events_preserved": before,
                        "revoked_subjects_applied": affected, "policies_disabled": True, "old_sessions_revoked": True,
                        "source_database_modified": False, "config_models_and_key_restored": True,
                        "backup_snapshot_counts_verified": "row_counts" in manifest}
        finally:
            if native_path and native_path.is_relative_to(backup_directory) and native_path.name.startswith("chamcong_restore_stage_"):
                native_path.unlink(missing_ok=True)
