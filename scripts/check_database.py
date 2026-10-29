"""Verify migrations and restore using only isolated databases created by this run."""
import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[1]
native_file = ROOT / ".runtime/native-root.txt"
native = Path(native_file.read_text().strip()) if native_file.exists() else ROOT
pg = native / ".runtime/postgresql/pgsql/bin"
credentials = json.loads((ROOT / ".runtime/credentials.json").read_text())
suffix = secrets.token_hex(4)
names = [f"chamcong_m0check_{suffix}", f"chamcong_m0restore_{suffix}"]
env_admin = dict(os.environ, PGPASSWORD=credentials["admin"])
common = ["-h", "127.0.0.1", "-p", "55432", "-U", "postgres"]
dump = native / f".runtime/m0-{suffix}.dump"
created = []
engines = []


def command(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, encoding="utf-8", errors="replace", **kwargs)


def database_url(name):
    return f"postgresql+psycopg://chamcong:{credentials['app']}@127.0.0.1:55432/{name}"


def migrate(name, action, target):
    env = dict(os.environ, CHAMCONG_DATABASE_URL=database_url(name))
    command([sys.executable, "-m", "alembic", "-c", str(ROOT / "backend/alembic.ini"), action, target], cwd=ROOT, env=env)


try:
    for name in names:
        assert re.fullmatch(r"chamcong_m0(?:check|restore)_[0-9a-f]{8}", name)
        command([str(pg / "createdb.exe"), *common, "-O", "chamcong", name], env=env_admin)
        created.append(name)
    migrate(names[0], "upgrade", "head")
    engine = create_engine(database_url(names[0]))
    engines.append(engine)
    tables = inspect(engine).get_table_names()
    assert len(tables) == 8, tables
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO employees (id, code, name, department, active, created_at, updated_at) VALUES ('m0-test', 'M0-TEST', :name, '', true, now(), now())"), {"name": "Nhân viên kiểm thử"})
    command([str(pg / "pg_dump.exe"), *common, "-Fc", "-f", str(dump), names[0]], env=env_admin)
    command([str(pg / "pg_restore.exe"), *common, "-d", names[1], "--exit-on-error", str(dump)], env=env_admin)
    restored = create_engine(database_url(names[1]))
    engines.append(restored)
    with restored.connect() as connection:
        assert connection.execute(text("SELECT name FROM employees WHERE code='M0-TEST'")).scalar_one() == "Nhân viên kiểm thử"
    migrate(names[0], "downgrade", "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]
    migrate(names[0], "upgrade", "head")
    assert len(inspect(engine).get_table_names()) == 8
    report = {"postgresql": "17.11", "schema_tables": tables, "upgrade": "passed", "downgrade_and_upgrade": "passed", "pg_dump_restore_unicode": "passed", "isolated_databases": True, "live_database_test_data": False}
    (ROOT / "evidence/m0/database-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("PostgreSQL migrations, downgrade/upgrade and pg_dump/restore passed on isolated databases")
finally:
    for engine in engines:
        engine.dispose()
    for name in created:
        command([str(pg / "dropdb.exe"), *common, "--if-exists", name], env=env_admin)
    dump.unlink(missing_ok=True)
