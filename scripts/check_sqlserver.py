"""Check SQL Server migration and backup/restore on newly created test DBs only."""
import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

import pyodbc
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]
suffix = secrets.token_hex(4)
names = [f"ChamCong_M0Check_{suffix}", f"ChamCong_M0Restore_{suffix}"]
base = "DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=master;Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=5"
created = []
engines = []


def url(name):
    return URL.create("mssql+pyodbc", query={"odbc_connect": base.replace("DATABASE=master", "DATABASE="+name)}).render_as_string(hide_password=False)


def migrate(name, action, target):
    result=subprocess.run([sys.executable,"-m","alembic","-c",str(ROOT/"backend/alembic.ini"),action,target],
                   env=dict(os.environ,CHAMCONG_DATABASE_URL=url(name),PYTHONIOENCODING="utf-8"),cwd=ROOT,check=False,
                   capture_output=True,text=True,encoding="utf-8",errors="replace")
    if result.returncode:
        diagnostic=result.stdout+result.stderr
        (ROOT/".runtime/check-sqlserver-error.log").write_text(diagnostic,encoding="utf-8")
        raise RuntimeError(diagnostic[-7000:])


with pyodbc.connect(base, autocommit=True) as admin:
    cursor=admin.cursor()
    backup_dir=cursor.execute("SELECT CAST(SERVERPROPERTY('InstanceDefaultBackupPath') AS nvarchar(500))").fetchval()
    data_dir=cursor.execute("SELECT CAST(SERVERPROPERTY('InstanceDefaultDataPath') AS nvarchar(500))").fetchval()
    backup_path=str(Path(backup_dir)/f"chamcong_m0_{suffix}.bak")
    try:
        for name in names:
            assert re.fullmatch(r"ChamCong_M0(?:Check|Restore)_[0-9a-f]{8}",name)
        cursor.execute(f"CREATE DATABASE [{names[0]}]")
        created.append(names[0])
        migrate(names[0],"upgrade","20261028_attendance_sessions")
        engine=create_engine(url(names[0]))
        engines.append(engine)
        tables=inspect(engine).get_table_names()
        assert len(tables)==15,tables
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO employees (id, code, name, department, active, created_at, updated_at) VALUES ('m0-test','M0-TEST',:name,N'',1,SYSDATETIMEOFFSET(),SYSDATETIMEOFFSET())"),{"name":"Nhân viên kiểm thử"})
            connection.execute(text("INSERT INTO shifts (id,name,start_minute,end_minute,rules) VALUES ('m0-shift',:name,480,1020,'{}')"),{"name":"Ca kiểm thử"})
            connection.execute(text("INSERT INTO shift_assignments (id,employee_id,shift_id,work_date) VALUES ('m0-assignment','m0-test','m0-shift','2026-10-28')"))
        migrate(names[0],"upgrade","head")
        tables=inspect(engine).get_table_names()
        assert len(tables)==21,tables
        with engine.connect() as connection:
            legacy=connection.execute(text("SELECT family_id,revision,timezone,start_minute,end_minute,rules FROM shifts WHERE id='m0-shift'")).one()
            assert tuple(legacy)==('m0-shift',1,'Asia/Ho_Chi_Minh',480,1020,'{}'),legacy
            assert connection.execute(text("SELECT cancelled_at FROM shift_assignments WHERE id='m0-assignment'")).scalar_one() is None
        with engine.begin() as connection:
            connection.execute(text("UPDATE shift_assignments SET cancelled_at=SYSUTCDATETIME(),cancel_reason=N'Thử giữ lịch sử' WHERE id='m0-assignment'"))
        try:
            migrate(names[0],"downgrade","20261028_attendance_sessions")
        except RuntimeError as error:
            assert "Cannot downgrade versioned or cancelled shift history" in str(error)
        else:
            raise AssertionError("Downgrade discarded assignment cancellation history")
        with engine.begin() as connection:
            assert connection.execute(text("SELECT cancelled_at FROM shift_assignments WHERE id='m0-assignment'")).scalar_one() is not None
            connection.execute(text("UPDATE shift_assignments SET cancelled_at=NULL,cancel_reason=NULL WHERE id='m0-assignment'"))
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO timesheet_periods (month,status,revision) VALUES ('2025-12','open',0)"))
        try:
            migrate(names[0],"downgrade","20261028_shift_revisions")
        except RuntimeError as error:
            assert "Cannot downgrade correction or period history" in str(error)
        else:
            raise AssertionError("Downgrade discarded period history")
        with engine.begin() as connection:
            assert connection.execute(text("SELECT COUNT(*) FROM timesheet_periods WHERE month='2025-12'")).scalar_one()==1
            connection.execute(text("DELETE FROM timesheet_periods WHERE month='2025-12'"))
        cursor.execute(f"BACKUP DATABASE [{names[0]}] TO DISK=? WITH INIT, COPY_ONLY, CHECKSUM",backup_path)
        while cursor.nextset():
            pass
        cursor.execute("RESTORE VERIFYONLY FROM DISK=? WITH CHECKSUM",backup_path)
        while cursor.nextset():
            pass
        file_rows=cursor.execute("RESTORE FILELISTONLY FROM DISK=?",backup_path).fetchall()
        moves=[]
        for index,row in enumerate(file_rows):
            logical=row[0].replace("'","''")
            extension="ldf" if row[2]=="L" else "mdf"
            path=str(Path(data_dir)/f"{names[1]}_{index}.{extension}").replace("'","''")
            moves.append(f"MOVE N'{logical}' TO N'{path}'")
        cursor.execute(f"RESTORE DATABASE [{names[1]}] FROM DISK=? WITH CHECKSUM, "+", ".join(moves),backup_path)
        while cursor.nextset():
            pass
        created.append(names[1])
        restored=create_engine(url(names[1]))
        engines.append(restored)
        with restored.connect() as connection:
            assert connection.execute(text("SELECT name FROM employees WHERE code='M0-TEST'")).scalar_one()=="Nhân viên kiểm thử"
        migrate(names[0],"downgrade","base")
        assert inspect(engine).get_table_names()==["alembic_version"]
        migrate(names[0],"upgrade","head")
        assert len(inspect(engine).get_table_names())==21
        report={"provider":"SQL Server 2025", "tables":tables, "upgrade":"passed", "downgrade_upgrade":"passed",
                "backup_checksum_verify":"passed", "restore_unicode":"passed", "legacy_shift_upgrade":"passed",
                "legacy_shift_rules_preserved":"passed", "rollback_guard_preserves_history":"passed",
                "period_rollback_guard":"passed",
                "isolated_databases":True, "live_database_test_data":False}
        (ROOT/"evidence/m0/sqlserver-check.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        print("SQL Server migrations, Unicode and native backup/restore passed on isolated databases")
    finally:
        for engine in engines:
            engine.dispose()
        for name in reversed(created):
            cursor.execute(f"ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
            cursor.execute(f"DROP DATABASE [{name}]")
        try:
            Path(backup_path).unlink(missing_ok=True)
        except PermissionError:
            print("Test-only backup retained in SQL Server backup folder")
