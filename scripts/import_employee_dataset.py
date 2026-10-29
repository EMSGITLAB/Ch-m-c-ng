"""Import a local roster and local photos atomically; never fetch imageUrl or enable attendance."""

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.calendar_guard import lock_calendar  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.database import session_factory  # noqa: E402
from app.employee_dataset import canonical_roster  # noqa: E402
from app.employees import EmployeeInput  # noqa: E402
from app.face_engine import FaceEngine  # noqa: E402
from app.models import AttendanceEvent, AuditLog, Employee, FaceTemplate, ImportedFacePhoto, RecognitionPolicy  # noqa: E402
from app.photo_import import prepare_import, save_import  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("manifest", type=Path)
parser.add_argument("--apply", action="store_true")
args = parser.parse_args()
path = args.manifest.resolve(strict=True)
if path.stat().st_size > 1_000_000:
    raise ValueError("Roster metadata exceeds 1 MB")
raw = json.loads(path.read_text(encoding="utf-8-sig"))
roster, conflicts = canonical_roster(raw)
with_photos = [item for item in roster if item["localFile"]]
without_photos = [item for item in roster if not item["localFile"]]
settings = get_settings()
engine = FaceEngine(settings.models_dir)
records = prepare_import(path, engine, entries=with_photos, max_people=1000) if with_photos else []
report = {"manifest_rows": len(raw), "unique_employee_codes": len(roster),
          "duplicate_rows_merged": len(raw)-len(roster), "department_conflicts_left_blank": len(conflicts),
          "local_photo_records": len(records), "profiles_without_local_photo": len(without_photos),
          "quality_counts": dict(Counter(row["quality"]["reason"] for row in records)),
          "applied": args.apply, "remote_urls_accessed": False, "operational_policy_changed": False,
          "model_id": engine.model_id, "accuracy_or_pad_validation": False}
with session_factory()() as db:
    if db.bind.dialect.name != "mssql" or db.scalar(text(
            "SELECT CAST(value AS nvarchar(100)) FROM sys.extended_properties WHERE class=0 AND name=N'chamcong_project'"
            )) != "chamcong-face-local":
        raise ValueError("Refusing an unmarked or non-SQL Server database")
    if args.apply:
        lock_calendar(db)
    profiles = {person.code: person for person in db.scalars(select(Employee))}
    for item in roster:
        existing = profiles.get(item["code"])
        if existing and (existing.name != item["name"] or existing.department != item["department"] or not existing.active):
            raise ValueError("Existing profile metadata conflict; no source records were changed")
    report["profiles_to_add"] = sum(item["code"] not in profiles for item in roster)
    before_events = db.scalar(select(func.count()).select_from(AttendanceEvent))
    before_templates = db.scalar(select(func.count()).select_from(FaceTemplate))
    policies = sorted((row.id, row.enabled) for row in db.scalars(select(RecognitionPolicy)))
    if args.apply:
        only_created = 0
        for item in without_photos:
            if item["code"] not in profiles:
                db.add(Employee(**EmployeeInput(**{key: item[key] for key in ("code", "name", "department")}).model_dump()))
                only_created += 1
        if only_created:
            db.add(AuditLog(action="employee_roster_import", details={"profiles_without_photo_created": only_created,
                "remote_urls_accessed": False, "department_conflicts_left_blank": len(conflicts)}))
        imported = save_import(db, records, engine, "Bổ sung dữ liệu nhân viên và ảnh local do người dùng cung cấp", commit=False)
        report["import"] = imported | {"profiles_without_photo_created": only_created,
            "total_profiles_created": imported["profiles_created"]+only_created}
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == before_events
        assert db.scalar(select(func.count()).select_from(FaceTemplate)) == before_templates
        assert sorted((row.id, row.enabled) for row in db.scalars(select(RecognitionPolicy))) == policies
        for conflict in conflicts:
            person = db.scalar(select(Employee).where(Employee.code == conflict["code"]))
            previous = db.scalars(select(AuditLog).where(
                AuditLog.action == "employee_department_import_conflict", AuditLog.entity_id == person.id)).all()
            if not any(row.details.get("source_values") == conflict["source_values"] for row in previous):
                db.add(AuditLog(action="employee_department_import_conflict", entity_id=person.id,
                    details={"source_values": conflict["source_values"], "stored_value": "",
                             "source_record_count": len(conflict["source_ids"])}))
        report["totals"] = {"employees": db.scalar(select(func.count()).select_from(Employee)),
            "imported_photos": db.scalar(select(func.count()).select_from(ImportedFacePhoto)),
            "accepted_imported_photos": db.scalar(select(func.count()).select_from(ImportedFacePhoto).where(
                ImportedFacePhoto.sample_id.is_not(None)))}
        db.commit()
    report["attendance_events_unchanged"] = True
    report["operational_templates_unchanged"] = True
private = settings.runtime_dir / "photo-import"
private.mkdir(parents=True, exist_ok=True)
stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
(private / (stamp+"-roster-conflicts.json")).write_text(json.dumps(conflicts, ensure_ascii=False, indent=2), encoding="utf-8")
(private / (stamp+"-dataset-import.json")).write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report))
