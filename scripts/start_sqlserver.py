"""Connect to the installed SQL Server; create only this project's database."""
import json
import secrets
from pathlib import Path

import pyodbc
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]
DATABASE = "ChamCongFaceLocal"
PROJECT_MARKER = "chamcong-face-local"
connection_string = "DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=master;Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=5"
with pyodbc.connect(connection_string, autocommit=True) as connection:
    cursor = connection.cursor()
    exists = cursor.execute("SELECT DB_ID(?)", DATABASE).fetchval() is not None
    if not exists:
        cursor.execute(f"CREATE DATABASE [{DATABASE}]")
        cursor.execute(f"USE [{DATABASE}]")
        cursor.execute("EXEC sys.sp_addextendedproperty @name=N'chamcong_project', @value=?", PROJECT_MARKER)
    else:
        cursor.execute(f"USE [{DATABASE}]")
        marker = cursor.execute("SELECT CAST(value AS nvarchar(100)) FROM sys.extended_properties WHERE class=0 AND name=N'chamcong_project'").fetchval()
        if marker != PROJECT_MARKER:
            raise RuntimeError("Existing database does not belong to this project; refusing to modify it")
    version = cursor.execute("SELECT CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(50)), CAST(SERVERPROPERTY('Edition') AS nvarchar(100))").fetchone()
app_connection = connection_string.replace("DATABASE=master", "DATABASE=" + DATABASE)
url = URL.create("mssql+pyodbc", query={"odbc_connect": app_connection}).render_as_string(hide_password=False)
env_path = ROOT / ".env"
lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
lines = [line for line in lines if not line.startswith("CHAMCONG_DATABASE_URL=")]
lines.append("CHAMCONG_DATABASE_URL=" + url)
if not any(line.startswith("CHAMCONG_SESSION_SECRET=") for line in lines):
    lines.append("CHAMCONG_SESSION_SECRET=" + secrets.token_urlsafe(48))
env_path.write_text("\n".join(lines)+"\n", encoding="utf-8")
report = {"provider": "SQL Server", "server": "localhost", "database": DATABASE,
          "version": version[0], "edition": version[1], "authentication": "Windows integrated (development)",
          "other_databases_modified": False, "postgresql": "stopped and deferred"}
(ROOT / "evidence/m0/sqlserver-environment.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
print("SQL Server application database ready: ChamCongFaceLocal; Windows authentication")
