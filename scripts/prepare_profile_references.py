"""Use existing current-revision portraits as one-photo references; preview by default."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import func, select, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.biometric_state import lock_employee  # noqa: E402
from app.calendar_guard import lock_calendar  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.database import session_factory  # noqa: E402
from app.face_engine import FaceEngine, FaceInputError  # noqa: E402
from app.matching import Gallery  # noqa: E402
from app.models import AttendanceEvent, AuditLog, CollectionSample, Employee, ImportedFacePhoto  # noqa: E402
from app.pilot_enrollment import current_config, membership, validate_controls  # noqa: E402
from app.pilot_gallery import gallery_from_pins  # noqa: E402
from app.profile_photos import add_reference_pin, analyze, auto_publish, reference_sample  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    engine = FaceEngine(get_settings().models_dir)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(face_engine=engine,
        attendance_policy_id=get_settings().functional_trial_policy_id)))
    with session_factory()() as db:
        if db.bind.dialect.name != "mssql" or db.scalar(text(
            "SELECT CAST(value AS nvarchar(100)) FROM sys.extended_properties WHERE class=0 AND name=N'chamcong_project'"
        )) != "chamcong-face-local":
            raise ValueError("Refusing an unmarked or non-SQL Server database")
        source = current_config(db, request)
        if not source or not source.enabled:
            raise ValueError("An enabled, tested local functional policy is required")
        baseline = gallery_from_pins(db, membership(source), engine.model_id, engine.dimensions)
        rows = db.execute(select(ImportedFacePhoto, Employee).join(Employee).where(
            Employee.active == True, ImportedFacePhoto.biometric_revision == Employee.biometric_revision,  # noqa: E712
            ImportedFacePhoto.model_id == engine.model_id).order_by(
                Employee.code, ImportedFacePhoto.created_at.desc(), ImportedFacePhoto.id.desc())).all()
        candidates, seen, reasons, rejected = [], set(), Counter(), []
        for photo, person in rows:
            if person.id in seen or person.id in baseline.samples:
                continue
            seen.add(person.id)
            if photo.sample_id:
                sample = db.get(CollectionSample, photo.sample_id)
                import numpy as np
                vector, quality = np.frombuffer(sample.vector, dtype="<f4"), sample.quality
            else:
                try:
                    vector, quality = analyze(engine, photo.image)
                except FaceInputError as error:
                    vector, quality = None, {"accepted": False, "reason": error.code}
            reasons[quality["reason"]] += 1
            candidates.append((photo.id, person.id, person.biometric_revision, vector, quality))
        samples = dict(baseline.samples)
        for _, identity, _, vector, _ in candidates:
            if vector is not None:
                samples[identity] = [vector]
        # Quarantine conflicting new identities, keeping every previously published person intact.
        gallery = Gallery(engine.model_id, samples, engine.dimensions)
        excluded = set()
        for identity, vectors in gallery.samples.items():
            for vector in vectors:
                rank = gallery.rank(vector, engine.model_id)
                if rank.first_id != identity or (rank.margin is not None and rank.margin <= source.minimum_margin):
                    if identity not in baseline.samples:
                        excluded.add(identity)
                    # A new reference can also make a previously tested member ambiguous.
                    for other, other_vectors in gallery.samples.items():
                        if other != identity and other not in baseline.samples:
                            candidate_rank = Gallery(engine.model_id, {other: other_vectors}, engine.dimensions).rank(vector, engine.model_id)
                            own_rank = Gallery(engine.model_id, {identity: vectors}, engine.dimensions).rank(vector, engine.model_id)
                            if candidate_rank.first_score >= own_rank.first_score - source.minimum_margin:
                                excluded.add(other)
        gallery = Gallery(engine.model_id, {key: value for key, value in samples.items() if key not in excluded}, engine.dimensions)
        controls = validate_controls(db, gallery, engine.model_id, engine.dimensions, source.threshold, source.minimum_margin)
        report = {"applied": args.apply, "portraits_reviewed": len(candidates), "quality_counts": dict(reasons),
            "existing_members_preserved": len(baseline.samples), "ambiguous_profiles_excluded": len(excluded),
            "profiles_to_enable": len(gallery.samples)-len(baseline.samples),
            "reference_minimum_pixels": 64, "live_minimum_pixels": 96, "image_upscaled_to_pass": False,
            "model_changed": False, "identity_threshold_changed": False,
            "group_accuracy_validated": False, "pad_validated": False, "controls": controls}
        if args.apply:
            expected_policy = source.id
            before = db.scalar(select(func.count()).select_from(AttendanceEvent))
            lock_calendar(db)
            if current_config(db, request).id != expected_policy:
                raise ValueError("Policy changed during analysis; preview again")
            additions = []
            for photo_id, identity, revision, vector, quality in candidates:
                lock_employee(db, identity, expected_revision=revision, active_only=True)
                photo, person = db.get(ImportedFacePhoto, photo_id), db.get(Employee, identity)
                sample = reference_sample(db, person, photo, vector, quality, engine)
                if sample and identity not in excluded:
                    additions.append(add_reference_pin(db, person, sample, engine))
                else:
                    rejected.append({"employee_id": identity, "photo_id": photo_id,
                        "reason": "ambiguous_reference" if identity in excluded else quality["reason"]})
            db.flush()
            if additions:
                report["publication"] = auto_publish(db, request, additions)
            db.add(AuditLog(action="profile_photos_auto_enrolled", reason="Dùng một ảnh hồ sơ theo yêu cầu người dùng",
                details={"summary": report, "excluded": rejected}))
            if db.scalar(select(func.count()).select_from(AttendanceEvent)) != before:
                raise ValueError("Unexpected attendance change inside reference transaction")
            db.commit()
        print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
