"""Read-only T07 readiness check; export counts, never identities/images/vectors."""

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.database import session_factory  # noqa: E402
from app.models import CollectionSample, Employee, FaceCollection, ImportedFacePhoto  # noqa: E402


def main():
    manifest = json.loads((ROOT / "models/manifest.json").read_text(encoding="utf-8"))
    model_id = manifest["model_id"]
    dimensions = manifest["embedding_dimensions"]
    people, valid_images, invalid_rows = set(), 0, 0
    with session_factory()() as db:
        total_images = db.scalar(select(func.count()).select_from(ImportedFacePhoto))
        rows = db.execute(select(ImportedFacePhoto, CollectionSample, FaceCollection, Employee)
                          .join(CollectionSample, ImportedFacePhoto.sample_id == CollectionSample.id)
                          .join(FaceCollection, CollectionSample.collection_id == FaceCollection.id)
                          .join(Employee, FaceCollection.employee_id == Employee.id)
                          .where(Employee.active == True)).all()  # noqa: E712
        for photo, sample, collection, employee in rows:
            valid = (photo.employee_id == employee.id and collection.status == "complete"
                     and collection.purpose == "enrollment"
                     and photo.quality.get("accepted") and sample.quality.get("accepted")
                     and photo.model_id == sample.model_id == collection.model_id == model_id
                     and photo.biometric_revision == collection.biometric_revision == employee.biometric_revision
                     and sample.dimensions == dimensions and len(sample.vector) == dimensions * 4
                     and photo.fingerprint == sample.fingerprint == hashlib.sha256(photo.image).hexdigest())
            if valid:
                vector = np.frombuffer(sample.vector, dtype="<f4")
                valid = bool(np.isfinite(vector).all() and abs(float(np.linalg.norm(vector)) - 1) < .001)
            if valid:
                people.add(employee.id)
                valid_images += 1
            else:
                invalid_rows += 1
        probes = db.execute(select(FaceCollection.employee_id, FaceCollection.purpose,
                                   func.count(CollectionSample.id))
                            .join(CollectionSample, CollectionSample.collection_id == FaceCollection.id)
                            .where(FaceCollection.status == "complete", FaceCollection.model_id == model_id,
                                   FaceCollection.employee_id.in_(people),
                                   FaceCollection.purpose.in_(["calibration", "evaluation"]))
                            .group_by(FaceCollection.employee_id, FaceCollection.purpose)).all()
    report = {
        "checked_at": datetime.now(UTC).isoformat(), "model_id": model_id,
        "scope": "initial_reference_dataset_only", "minimum_people": 10,
        "minimum_reference_images_per_person": 1, "stored_imported_images": total_images,
        "eligible_reference_people": len(people), "eligible_reference_images": valid_images,
        "invalid_linked_rows": invalid_rows, "initial_dataset_ready": len(people) >= 10,
        "imported_cohort_independent_calibration_people": len({r[0] for r in probes if r[1] == "calibration"}),
        "imported_cohort_independent_evaluation_people": len({r[0] for r in probes if r[1] == "evaluation"}),
        "identity_accuracy_validated": False, "attendance_enabled_by_this_check": False,
        "live_database_modified": False, "identities_images_vectors_exported": False,
    }
    (ROOT / "evidence/m1/initial-dataset-readiness.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    return 0 if report["initial_dataset_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
