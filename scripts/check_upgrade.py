"""Real isolated upgrade/fault/compatible-rollback drill; never changes the live service."""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from time import perf_counter

import pyodbc
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import get_settings  # noqa: E402
from app.database import session_factory  # noqa: E402
from app.native_backup import MARKER, RECOVERY_NAME, connection_string, recovery_counts  # noqa: E402
from app.upgrade import migrate, stage  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--release", required=True)
args = parser.parse_args()
release = (ROOT / ".runtime/releases" / args.release).resolve()
if not release.is_relative_to((ROOT / ".runtime/releases").resolve()):
    raise ValueError("Not a project release")
settings = get_settings()
metadata = json.loads((settings.runtime_dir / "backups/last-backup.json").read_text(encoding="utf-8"))
archive = Path(metadata["archive_path"])
before_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
assert before_hash == metadata["cipher_sha256"]
with session_factory()() as db:
    before = recovery_counts(db)
owned = []
began = perf_counter()


def fail_after_committed_ddl(root, python):
    migrate(root, python)
    # The fault deliberately commits test DDL to the candidate database, proving
    # rollback restores the compatible snapshot rather than reusing a damaged DB.
    import subprocess

    code = '''
import sys
sys.path.insert(0,"backend")
from sqlalchemy import text
from app.database import get_engine
with get_engine().begin() as db:
    db.execute(text("CREATE TABLE upgrade_failure_probe (id int NOT NULL PRIMARY KEY)"))
    db.execute(text("INSERT INTO upgrade_failure_probe (id) VALUES (1)"))
'''
    from app.upgrade import clean_env

    subprocess.run([str(python), "-c", code], cwd=root, env=clean_env(), check=True, capture_output=True)
    raise RuntimeError("Intentional isolated migration failure after committed DDL")


try:
    success = stage(archive, release)
    owned.append(success["candidate_database_name"])
    assert success["staged"] and success["candidate_smoke_passed"] and not success["traffic_switched"]
    failure = stage(archive, release, _migrate=fail_after_committed_ddl)
    owned.extend([failure["candidate_database_name"], failure["rollback_database_name"]])
    assert not failure["staged"] and failure["compatible_rollback_offline_install_and_smoke_passed"]
    assert failure["candidate_database_name"] != failure["rollback_database_name"]
    for name, probe_exists in ((failure["candidate_database_name"], True), (failure["rollback_database_name"], False)):
        url = URL.create("mssql+pyodbc", query={"odbc_connect": connection_string(name)})
        engine = create_engine(url, hide_parameters=True)
        try:
            with engine.connect() as db:
                assert bool(db.scalar(text("SELECT OBJECT_ID('upgrade_failure_probe','U')"))) == probe_exists
        finally:
            engine.dispose()
    with session_factory()() as db:
        assert recovery_counts(db) == before
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == before_hash
    report = {"release": args.release, "real_native_sqlserver": True,
              "prior_snapshot_app_and_candidate_fresh_offline_install_passed": True,
              "same_schema_app_upgrade_and_model_smoke_passed": True,
              "partial_committed_ddl_failure_injected": True,
              "compatible_rollback_restored_into_new_database": True,
              "rollback_contains_no_failed_ddl": True, "source_counts_unchanged": True,
              "encrypted_archive_unchanged": True, "live_service_switched": False,
              "business_config_preserved": True, "new_and_old_access_remain_disabled": True,
              "elapsed_seconds": round(perf_counter()-began, 2),
              "cross_schema_release_upgrade_tested": False, "physical_vm_tested": False,
              "personal_data_in_evidence": False}
    (ROOT / "evidence/m5/upgrade-rollback-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
finally:
    for name in owned:
        assert RECOVERY_NAME.fullmatch(name)
        with pyodbc.connect(connection_string("master"), autocommit=True) as admin:
            marker = admin.execute(f"SELECT CAST(value AS nvarchar(100)) FROM [{name}].sys.extended_properties "
                                   "WHERE class=0 AND name=N'chamcong_project'").fetchval()
            if marker != MARKER:
                raise RuntimeError("Refusing to drop a recovery database without project ownership")
            admin.execute(f"ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
            admin.execute(f"DROP DATABASE [{name}]")
