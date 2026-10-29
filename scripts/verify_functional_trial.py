"""Verify real trial receipts and local report/export data, without exporting identities."""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import get_settings  # noqa: E402
from app.database import session_factory  # noqa: E402
from app.devices import aware  # noqa: E402
from app.functional_trial import trial_gallery  # noqa: E402
from app.models import AttendanceEvent, RecognitionPolicy, RecognitionSession  # noqa: E402
from app.timesheet_exports import serialize_export  # noqa: E402
from app.timesheets import build_report  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--user-confirmed-name-and-audio", action="store_true")
args = parser.parse_args()
settings = get_settings()
with session_factory()() as db:
    policy = db.get(RecognitionPolicy, settings.functional_trial_policy_id)
    if not policy:
        raise RuntimeError("Trial policy not configured")
    trial_gallery(db, policy)
    participant = policy.evidence["participant_id"]
    sessions = db.scalars(select(RecognitionSession).where(RecognitionSession.policy_id == policy.id,
                         RecognitionSession.state == "used")).all()
    events = db.scalars(select(AttendanceEvent).where(AttendanceEvent.recognition_version == policy.id)
                       .order_by(AttendanceEvent.server_time)).all()
    if not sessions or not events:
        raise RuntimeError("No real recorded trial receipt yet")
    for row in sessions:
        if row.employee_id != participant or row.receipt.get("recording_scope") != "single_person_functional_trial":
            raise RuntimeError("Unexpected receipt scope")
    zone = ZoneInfo(settings.business().timezone)
    day = aware(events[-1].server_time).astimezone(zone).date()
    report = build_report(db, day, day, participant, as_of=datetime.now(UTC), unpaginated=True)
    report["finalized"] = False
    csv, _ = serialize_export(report, "csv")
    xlsx, _ = serialize_export(report, "xlsx")
    if report.get("functional_trial_event_count", 0) < 1:
        raise RuntimeError("Trial event missing from report")
    private = ROOT / ".runtime/trial-exports"
    private.mkdir(exist_ok=True)
    (private / "trial.csv").write_bytes(csv)
    (private / "trial.xlsx").write_bytes(xlsx)
    result = {"scope": "single-person-functional-v1", "participant_count": 1,
              "used_receipts": len(sessions), "recorded_events": len(events),
              "directions_observed": sorted({row.direction for row in events}),
              "all_receipts_bound_to_participant": True,
              "report_source_event_count": report["source_event_count"],
              "report_trial_event_count": report["functional_trial_event_count"],
              "report_assigned_rows": len(report["rows"]),
              "report_unassigned_events": len(report["unassigned_events"]),
              "local_csv_generated": bool(csv), "local_xlsx_generated": bool(xlsx),
              "identities_images_vectors_exported_in_evidence": False,
              "user_confirmed_correct_name_and_audio": args.user_confirmed_name_and_audio,
              "confirmation_source": "User reply in this session" if args.user_confirmed_name_and_audio else None,
              "pad_or_group_accuracy_validated": False}
    db.rollback()
(ROOT / "evidence/m3/single-person-live-flow.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(result, ensure_ascii=True))
