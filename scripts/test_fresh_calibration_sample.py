"""Read a genuinely new camera sample and compare it with completed references only."""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.calibration import load_samples  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.database import session_factory  # noqa: E402
from app.devices import aware  # noqa: E402
from app.matching import SCORING_RULE, Gallery, normalized  # noqa: E402
from app.models import CollectionSample, Employee, FaceCollection  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--employee-code", required=True)
    parser.add_argument("--since", required=True, help="Timezone-aware ISO timestamp before the camera trial")
    args = parser.parse_args()
    since = datetime.fromisoformat(args.since)
    if since.tzinfo is None:
        raise ValueError("Trial baseline requires an explicit timezone")
    manifest = json.loads((get_settings().models_dir / "manifest.json").read_text(encoding="utf-8"))
    model, dimensions = manifest["model_id"], manifest["embedding_dimensions"]
    with session_factory()() as db:
        person = db.scalar(select(Employee).where(Employee.code == args.employee_code, Employee.active == True))  # noqa: E712
        if not person:
            raise ValueError("Active employee code not found")
        rows = db.execute(select(CollectionSample, FaceCollection)
                          .join(FaceCollection, CollectionSample.collection_id == FaceCollection.id)
                          .where(FaceCollection.employee_id == person.id, FaceCollection.purpose == "calibration",
                                 FaceCollection.status.in_(["open", "complete"]), FaceCollection.model_id == model,
                                 FaceCollection.biometric_revision == person.biometric_revision,
                                 CollectionSample.created_at >= since)
                          .order_by(CollectionSample.created_at.desc(), CollectionSample.id).limit(1)).all()
        if not rows:
            print(json.dumps({"status": "waiting_for_new_camera_sample", "baseline": since.isoformat()}))
            return 2
        probe, collection = rows[0]
        if (probe.model_id != model or probe.dimensions != dimensions or len(probe.vector) != dimensions * 4
                or probe.quality.get("accepted") is not True or aware(probe.created_at) < since):
            raise ValueError("New probe failed metadata/model/quality validation")
        references = [row for row in load_samples(db, model, dimensions) if row.purpose == "enrollment"]
        if any(row.fingerprint == probe.fingerprint for row in references):
            raise ValueError("Probe is the same image as a reference")
        grouped = defaultdict(list)
        for row in sorted(references, key=lambda item: item.fingerprint):
            grouped[row.person].append(row.vector)
        if person.id not in grouped:
            raise ValueError("Employee has no completed reference collection")
        vector = normalized(np.frombuffer(probe.vector, dtype="<f4"), dimensions)
        variants = []
        for cap in (1, 3, 5, 10):
            gallery = Gallery(model, {identity: values[:cap] for identity, values in grouped.items()}, dimensions)
            ranking = gallery.rank(vector, model)
            best = db.get(Employee, ranking.first_id)
            expected_scores = np.clip(gallery.samples[person.id] @ vector, -1, 1)
            variants.append({"reference_cap": cap, "gallery_people": len(gallery.samples),
                             "expected_reference_images_used": len(gallery.samples[person.id]),
                             "best_employee_code": best.code if best else None,
                             "top1_is_expected": ranking.first_id == person.id,
                             "top1_cosine": ranking.first_score, "top2_cosine": ranking.second_score,
                             "top2_margin": ranking.margin,
                             "expected_person_cosine": float(np.sort(expected_scores)[-3:].mean())})
        report = {"status": "fresh_camera_probe_compared", "employee_code": person.code,
                  "trial_baseline": since.isoformat(), "probe_created_at": aware(probe.created_at).isoformat(),
                  "probe_collection_complete": collection.status == "complete", "model_id": model,
                  "scoring_rule": SCORING_RULE, "reference_experiments": variants,
                  "different_capture_from_reference": True, "threshold_selected": False,
                  "identity_confirmed": False, "attendance_recorded": False,
                  "live_database_modified": False, "images_vectors_exported": False}
    target = ROOT / ".runtime/calibration/fresh-probe.json"
    target.parent.mkdir(exist_ok=True, parents=True)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
