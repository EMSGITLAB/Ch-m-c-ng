"""Report dataset coverage without exporting identities, images or vectors."""
import json
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import func, select

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.database import session_factory  # noqa: E402
from app.models import AttendanceEvent, CollectionSample, FaceCollection, FaceTemplate, utcnow  # noqa: E402

with session_factory()() as db:
    rows=db.execute(select(FaceCollection.purpose,FaceCollection.status,func.count(),func.sum(FaceCollection.sample_count))
                    .group_by(FaceCollection.purpose,FaceCollection.status)).all()
    qualities=db.scalars(select(CollectionSample.quality).join(FaceCollection)
                        .where(FaceCollection.status=="complete")).all()
    poses=Counter(quality["required_pose"] for quality in qualities
                  if quality.get("pose_check")=="relative_landmarks_provisional")
    all_qualities=db.scalars(select(CollectionSample.quality)).all()
    auto_count=sum(quality.get("capture_mode")=="auto" for quality in all_qualities)
    summary={"collections":[{"purpose":purpose,"status":status,"sessions":sessions,"samples":samples}
                           for purpose,status,sessions,samples in rows],
             "operational_templates":db.scalar(select(func.count()).select_from(FaceTemplate)),
             "attendance_events":db.scalar(select(func.count()).select_from(AttendanceEvent)),
             "guided_completed_samples":sum(poses.values()),"guided_pose_counts":dict(poses),
             "auto_captured_samples":auto_count,
             "expired_open_with_minimum_samples":db.scalar(select(func.count()).select_from(FaceCollection)
                  .where(FaceCollection.status=="open",FaceCollection.expires_at<=utcnow(),FaceCollection.sample_count>=5)),
             "calibration_verified":False,"identities_exported":False,"vectors_exported":False}
    print(json.dumps(summary,ensure_ascii=True))
