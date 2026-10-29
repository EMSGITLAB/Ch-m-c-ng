"""Read-only preview of current reference expansion; no publication or accuracy claim."""

import json
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.calibration import load_samples  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.database import session_factory  # noqa: E402
from app.functional_trial import trial_gallery  # noqa: E402
from app.matching import Gallery  # noqa: E402
from app.models import RecognitionPolicy  # noqa: E402
from app.pilot_enrollment import validate_controls  # noqa: E402
from app.policy_selection import selected_policy  # noqa: E402

settings = get_settings()
manifest = json.loads((settings.models_dir / "manifest.json").read_text(encoding="utf-8"))
model, dimensions = manifest["model_id"], manifest["embedding_dimensions"]
with session_factory()() as db:
    identity = selected_policy(db, settings.functional_trial_policy_id)
    policy = db.scalar(select(RecognitionPolicy).where(RecognitionPolicy.id == identity))
    if not policy or not policy.enabled:
        raise ValueError("No current enabled trial to preview; never invent a threshold")
    active = trial_gallery(db, policy, dimensions)
    references = {person: list(vectors) for person, vectors in active.samples.items()}
    for sample in sorted(load_samples(db, model, dimensions), key=lambda row: (row.collection, row.fingerprint)):
        if sample.purpose == "enrollment" and sample.person not in references:
            references[sample.person] = [sample.vector]
    prospective = Gallery(model, references, dimensions)
    controls = validate_controls(db, prospective, model, dimensions, policy.threshold, policy.minimum_margin)
    report = {"read_only": True, "active_people_unchanged": len(active.samples),
              "prospective_reference_people": len(prospective.samples), "existing_controls_passed": True,
              "controls": controls, "threshold_changed": False, "model_changed": False,
              "policy_published": False, "images_vectors_or_identities_exported": False,
              "group_accuracy_or_pad_validation": False}
(ROOT / "evidence/m5/pilot-reference-preview.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report))
