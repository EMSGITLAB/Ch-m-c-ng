"""Start this project's portable PostgreSQL; keep credentials out of command lines."""
import json
import os
import secrets
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
native_file = ROOT / ".runtime/native-root.txt"
NATIVE_ROOT = Path(native_file.read_text(encoding="utf-8").strip()) if native_file.exists() else ROOT
BIN = NATIVE_ROOT / ".runtime/postgresql/pgsql/bin"
DATA = NATIVE_ROOT / "data/postgresql"
LOGS = NATIVE_ROOT / "logs"
LOGS.mkdir(exist_ok=True)
credentials_file = ROOT / ".runtime/credentials.json"
if not credentials_file.exists():
    credentials_file.write_text(json.dumps({"admin": secrets.token_urlsafe(32), "app": secrets.token_urlsafe(32), "session": secrets.token_urlsafe(48)}), encoding="utf-8")
credentials = json.loads(credentials_file.read_text(encoding="utf-8"))


def run(name, args, **kwargs):
    result = subprocess.run([str(BIN / (name + ".exe")), *args], check=False, capture_output=True, text=True, encoding="utf-8", errors="replace", **kwargs)
    if result.returncode:
        message = result.stderr + result.stdout
        for secret in credentials.values():
            message = message.replace(secret, "[redacted]")
        raise RuntimeError(name + " failed: " + message)
    return result


if not (DATA / "PG_VERSION").exists():
    DATA.parent.mkdir(exist_ok=True)
    pwfile = NATIVE_ROOT / ".runtime/initdb-password.txt"
    try:
        pwfile.write_text(credentials["admin"], encoding="ascii")
        run("initdb", ["-D", str(DATA), "-U", "postgres", "--encoding=UTF8", "--locale=C", "--auth=scram-sha-256", "--pwfile=" + str(pwfile)])
    finally:
        pwfile.unlink(missing_ok=True)
    with (DATA / "postgresql.conf").open("a", encoding="utf-8") as config:
        config.write("\nlisten_addresses = '127.0.0.1'\nport = 55432\n")

probe = subprocess.run([str(BIN / "pg_isready.exe"), "-h", "127.0.0.1", "-p", "55432"], check=False, capture_output=True)
if probe.returncode:
    # A server child can inherit pipe handles on Windows; use a file, not PIPE.
    with (LOGS / "postgresql-start.log").open("a", encoding="utf-8") as startup_log:
        subprocess.run([str(BIN / "pg_ctl.exe"), "-D", str(DATA), "-l", str(LOGS / "postgresql.log"), "-w", "start"],
                       stdout=startup_log, stderr=subprocess.STDOUT, check=True, timeout=60)
environment = dict(os.environ, PGPASSWORD=credentials["admin"])
query_args = ["-h", "127.0.0.1", "-p", "55432", "-U", "postgres", "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-At"]
exists = run("psql", query_args, input="SELECT 1 FROM pg_roles WHERE rolname='chamcong';", env=environment).stdout.strip()
if not exists:
    run("psql", query_args, input=f"CREATE ROLE chamcong LOGIN PASSWORD '{credentials['app']}';", env=environment)
exists = run("psql", query_args, input="SELECT 1 FROM pg_database WHERE datname='chamcong';", env=environment).stdout.strip()
if not exists:
    run("createdb", ["-h", "127.0.0.1", "-p", "55432", "-U", "postgres", "-O", "chamcong", "chamcong"], env=environment)
env_path = ROOT / ".env"
if not env_path.exists():
    env_path.write_text(f"CHAMCONG_DATABASE_URL=postgresql+psycopg://chamcong:{credentials['app']}@127.0.0.1:55432/chamcong\nCHAMCONG_SESSION_SECRET={credentials['session']}\n", encoding="utf-8")
print("PostgreSQL listening on 127.0.0.1:55432; application database ready")

