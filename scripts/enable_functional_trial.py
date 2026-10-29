"""Enable an explicit one-person local functional trial from existing real samples."""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from uuid import uuid4

import numpy as np
from sqlalchemy import select, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.biometric_state import lock_employee  # noqa: E402
from app.calendar_guard import lock_calendar  # noqa: E402
from app.calibration import load_samples  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.database import session_factory  # noqa: E402
from app.functional_trial import MODE, SCOPE  # noqa: E402
from app.matching import SCORING_RULE, normalized  # noqa: E402
from app.models import (  # noqa: E402
    AuditLog,
    CollectionSample,
    Employee,
    FaceCollection,
    FaceTemplate,
    RecognitionPolicy,
    utcnow,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--employee-code", required=True)
    args = parser.parse_args()
    manifest = json.loads((get_settings().models_dir / "manifest.json").read_text(encoding="utf-8"))
    model, dimensions = manifest["model_id"], manifest["embedding_dimensions"]
    with session_factory()() as db:
        if db.bind.dialect.name != "mssql":
            raise RuntimeError("This activation script requires the marked local SQL Server database")
        marker = db.scalar(text("SELECT CAST(value AS nvarchar(100)) FROM sys.extended_properties "
                                "WHERE class=0 AND name=N'chamcong_project'"))
        if marker != "chamcong-face-local":
            raise RuntimeError("Refusing an unmarked database")
        lock_calendar(db)
        person = db.scalar(select(Employee).where(Employee.code == args.employee_code))
        if not person:
            raise ValueError("Employee not found")
        lock_employee(db, person.id, expected_revision=person.biometric_revision, active_only=True)
        if db.scalar(select(RecognitionPolicy.id).where(RecognitionPolicy.enabled == True)):  # noqa: E712
            raise ValueError("An enabled policy already exists; inspect it before replacing")
        references = sorted([s for s in load_samples(db, model, dimensions) if s.purpose == "enrollment"],
                            key=lambda s: s.fingerprint)
        own = [s for s in references if s.person == person.id]
        if not own:
            raise ValueError("No completed reference enrollment")
        reference = own[0]
        rows = db.scalars(select(CollectionSample).join(FaceCollection)
                          .where(FaceCollection.employee_id == person.id,
                                 FaceCollection.purpose == "calibration",
                                 FaceCollection.status.in_(["open", "complete"]),
                                 FaceCollection.biometric_revision == person.biometric_revision,
                                 FaceCollection.model_id == model)).all()
        probes = []
        for row in rows:
            if (row.fingerprint == reference.fingerprint or row.model_id != model
                    or row.dimensions != dimensions or len(row.vector) != dimensions * 4
                    or row.quality.get("accepted") is not True):
                raise ValueError("Invalid or reused probe")
            probes.append(normalized(np.frombuffer(row.vector, dtype="<f4"), dimensions))
        if not probes:
            raise ValueError("At least one independent camera probe is required")
        positive = [float(np.clip(reference.vector @ v, -1, 1)) for v in probes]
        negative = [float(np.clip(reference.vector @ s.vector, -1, 1))
                    for s in references if s.person != person.id]
        highest_negative = max(negative, default=-1)
        threshold = max(0.5, (min(positive) + highest_negative) / 2)
        if min(positive) <= threshold or highest_negative >= threshold:
            raise ValueError("Existing controls overlap; cannot provision this trial threshold")
        vector = np.asarray(reference.vector, dtype="<f4").tobytes()
        template = FaceTemplate(employee_id=person.id, model_id=model, dimensions=dimensions,
                                biometric_revision=person.biometric_revision, vector=vector,
                                quality={"scope": SCOPE, "source_fingerprint": reference.fingerprint})
        db.add(template)
        db.flush()
        policy_id = "trial-" + uuid4().hex
        metrics = {"reference_images": 1, "probe_people": 1, "independent_probe_images": len(probes),
                   "minimum_positive_cosine": min(positive), "existing_negative_images": len(negative),
                   "maximum_existing_negative_cosine": highest_negative, "provisional_threshold": threshold,
                   "group_accuracy_validated": False, "pad_validated": False}
        db.add(RecognitionPolicy(id=policy_id, model_id=model, scoring_rule=SCORING_RULE,
                                 threshold=threshold, minimum_margin=0, enabled=True, mode=MODE,
                                 pad_verified=False, validated_at=utcnow(), evidence={
                                     "scope": SCOPE, "sequence_protocol": "stable-three-v1",
                                     "participant_id": person.id, "biometric_revision": person.biometric_revision,
                                     "template_id": template.id, "template_sha256": hashlib.sha256(vector).hexdigest(),
                                     "metrics": metrics}))
        db.add(AuditLog(action="functional_trial_enabled", entity_id=policy_id,
                        details={"participant_id": person.id, "scope": SCOPE, "metrics": metrics}))
        db.commit()
    env_path = ROOT / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines()
    keys = ("CHAMCONG_FUNCTIONAL_TRIAL_ENABLED=", "CHAMCONG_FUNCTIONAL_TRIAL_POLICY_ID=")
    lines = [line for line in lines if not line.startswith(keys)]
    lines.extend([keys[0] + "true", keys[1] + policy_id])
    temporary = env_path.with_suffix(".env.tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.replace(env_path)
    report = {"scope": SCOPE, "mode": MODE, "metrics": metrics,
              "reference_and_probe_different_images": True, "participant_count": 1,
              "images_vectors_exported": False, "model_id": model,
              "automatic_commit_in_trial": True, "restart_required": True}
    path = ROOT / "evidence/m3/single-person-trial-activation.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
