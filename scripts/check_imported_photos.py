"""Anonymous plumbing check; reusing reference files is never an accuracy trial."""

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import get_settings  # noqa: E402
from app.database import session_factory  # noqa: E402
from app.face_engine import FaceEngine  # noqa: E402
from app.imported_photos import rank_references  # noqa: E402
from app.models import AttendanceEvent, CollectionSample, Employee, FaceTemplate, ImportedFacePhoto  # noqa: E402

engine = FaceEngine(get_settings().models_dir)
with session_factory()() as db:
    photos = db.scalars(select(ImportedFacePhoto)).all()
    counts = Counter(photo.quality.get("reason") for photo in photos)
    vectors, self_checks = [], 0
    for photo in photos:
        if not photo.sample_id:
            continue
        vector, _ = engine.analyze(photo.image)
        ranked = rank_references(db, engine, vector, photo.fingerprint)
        assert ranked["candidates"][0]["employee_id"] == photo.employee_id
        assert ranked["candidates"][0]["same_reference_file"]
        stored = db.get(CollectionSample, photo.sample_id)
        assert np.allclose(vector, np.frombuffer(stored.vector, dtype="<f4"), atol=1e-6)
        self_checks += 1
        vectors.append((photo.employee_id, vector))
    cross = [float(np.clip(left @ right, -1, 1)) for index, (person, left) in enumerate(vectors)
             for other, right in vectors[index+1:] if other != person]
    report = {"employee_count": db.scalar(select(func.count()).select_from(Employee)),
        "imported_photos": len(photos), "quality_counts": dict(counts), "valid_imported_samples": len(vectors),
        "model_id": engine.model_id, "dimensions": engine.dimensions, "self_file_plumbing_checks": self_checks,
        "different_person_pairs": len(cross), "highest_different_person_cosine": round(max(cross), 6) if cross else None,
        "independent_positive_trials": 0, "accuracy_or_pad_validated": False,
        "operational_templates": db.scalar(select(func.count()).select_from(FaceTemplate)),
        "attendance_events": db.scalar(select(func.count()).select_from(AttendanceEvent)),
        "identities_images_vectors_exported": False}
out = ROOT / "evidence/m1/imported-photos-check.json"
out.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report))
