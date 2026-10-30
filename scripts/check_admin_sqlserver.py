"""Run the admin API scenarios against a throwaway migrated SQL Server DB."""
import argparse
import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

import pyodbc
from sqlalchemy.engine import URL

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--offline",action="store_true")
parser.add_argument("--test-file",action="append",choices=sorted(path.relative_to(ROOT).as_posix() for path in (ROOT/"backend/tests").glob("test_*.py")))
args=parser.parse_args()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
name="ChamCong_AdminCheck_"+secrets.token_hex(4)
assert re.fullmatch(r"ChamCong_AdminCheck_[0-9a-f]{8}",name)
base="DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=master;Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=5"
url=URL.create("mssql+pyodbc",query={"odbc_connect":base.replace("DATABASE=master","DATABASE="+name)}).render_as_string(hide_password=False)
env=dict(os.environ,CHAMCONG_TEST_DATABASE_URL=url,CHAMCONG_TEST_DB_NAME=name,CHAMCONG_DATABASE_URL=url,PYTHONIOENCODING="utf-8")
if args.offline:
    env["PYTHONPATH"]=str(ROOT/"backend/tests")+os.pathsep+env.get("PYTHONPATH","")
with pyodbc.connect(base,autocommit=True) as admin:
    cursor=admin.cursor()
    cursor.execute(f"CREATE DATABASE [{name}]")
    try:
        migration=subprocess.run([sys.executable,"-m","alembic","-c","backend/alembic.ini","upgrade","head"],cwd=ROOT,env=env,capture_output=True,text=True,encoding="utf-8",check=False)
        if migration.returncode:
            raise RuntimeError((migration.stdout+ migration.stderr)[-9000:])
        files=["backend/tests/test_admin.py","backend/tests/test_devices.py","backend/tests/test_collections.py","backend/tests/test_calibration.py","backend/tests/test_calibration_api.py","backend/tests/test_biometrics.py","backend/tests/test_auto_capture.py","backend/tests/test_attendance.py","backend/tests/test_shifts.py","backend/tests/test_timesheets.py","backend/tests/test_periods_adjustments.py","backend/tests/test_photo_import.py","backend/tests/test_timesheet_exports.py","backend/tests/test_recognition_sequence.py"]
        files.append("backend/tests/test_pad.py")
        files.append("backend/tests/test_functional_trial.py")
        files.extend(["backend/tests/test_operations.py", "backend/tests/test_runtime_supervisor.py",
                      "backend/tests/test_recovery_privacy.py", "backend/tests/test_native_backup.py"])
        files.extend(["backend/tests/test_recovery_key.py", "backend/tests/test_recovery_key_api.py"])
        files.append("backend/tests/test_pilot_enrollment.py")
        files.append("backend/tests/test_profile_photos.py")
        files.append("backend/tests/test_dashboard_direction.py")
        files.append("backend/tests/test_attendance_scope.py")
        files.append("backend/tests/test_partner_admin.py")
        files.append("backend/tests/test_partner_attendance.py")
        files.append("backend/tests/test_partner_speech.py")
        files.append("backend/tests/test_partner_reports.py")
        files.append("backend/tests/test_partner_face_store.py")
        if args.test_file:
            files=args.test_file
        plugin=["-p","network_guard"] if args.offline else []
        result=subprocess.run([sys.executable,"-m","pytest",*plugin,*files,"-q"],cwd=ROOT,env=env,capture_output=True,text=True,encoding="utf-8",check=False)
        evidence=ROOT/"evidence/m2"
        evidence.mkdir(exist_ok=True)
        prefix="offline-sqlserver" if args.offline else "admin-sqlserver"
        if args.test_file:
            prefix+="-targeted"
        (evidence/(prefix+"-tests.log")).write_text(result.stdout+result.stderr,encoding="utf-8")
        if result.returncode:
            print((result.stdout+result.stderr)[-9000:])
            raise SystemExit(result.returncode)
        if args.offline and "Offline guard: 0 nonlocal network attempts" not in result.stdout:
            raise RuntimeError("Offline guard did not report a clean session")
        (evidence/(prefix+"-check.json")).write_text(json.dumps({"provider":"SQL Server 2025","migration":"head","isolated_database":True,"test_files":files,"result":"passed","offline_network_guard":args.offline,"live_database_modified":False,"accuracy_or_pad_validation":False},indent=2),encoding="utf-8")
        print(result.stdout.split("warnings summary")[0][-1500:])
        print("Admin API checks passed on an isolated SQL Server database")
    finally:
        cursor.execute(f"ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
        cursor.execute(f"DROP DATABASE [{name}]")
