"""Actionable admin metadata; final-evaluation samples are never queried."""

from collections import defaultdict

from sqlalchemy import distinct, func, select

from .calibration import MIN_ENROLLED_PEOPLE, MIN_OUTSIDE_PEOPLE, MIN_PROBE_SAMPLES
from .models import CollectionSample, Employee, FaceCollection


def coverage(db, engine, offset, limit):
    counts = defaultdict(dict)
    rows = db.execute(select(FaceCollection.employee_id, FaceCollection.purpose,
                             func.count(CollectionSample.id), func.count(distinct(FaceCollection.id)))
                      .join(CollectionSample, CollectionSample.collection_id == FaceCollection.id)
                      .join(Employee, Employee.id == FaceCollection.employee_id)
                      .where(Employee.active == True, FaceCollection.status == "complete",  # noqa: E712
                             FaceCollection.biometric_revision == Employee.biometric_revision,
                             FaceCollection.model_id == engine.model_id,
                             CollectionSample.model_id == engine.model_id,
                             CollectionSample.dimensions == engine.dimensions,
                             FaceCollection.purpose.in_(["enrollment", "calibration"]))
                      .group_by(FaceCollection.employee_id, FaceCollection.purpose)).all()
    for person, purpose, samples, collections in rows:
        counts[person][purpose] = (samples, collections)
    enrolled = {person: values for person, values in counts.items() if values.get("enrollment", (0, 0))[0] > 0}
    outside = {person: values for person, values in counts.items()
               if person not in enrolled and values.get("calibration", (0, 0))[0] > 0}
    missing = {person: max(0, MIN_PROBE_SAMPLES - values.get("calibration", (0, 0))[0])
               for person, values in enrolled.items()}
    outside_ready = sum(values["calibration"][0] >= MIN_PROBE_SAMPLES for values in outside.values())
    total = db.scalar(select(func.count()).select_from(Employee).where(Employee.active == True))  # noqa: E712
    people = db.scalars(select(Employee).where(Employee.active == True)  # noqa: E712
                        .order_by(Employee.code, Employee.id).offset(offset).limit(limit)).all()
    items = []
    for person in people:
        values = counts[person.id]
        reference_samples = values.get("enrollment", (0, 0))[0]
        probe_samples, probe_collections = values.get("calibration", (0, 0))
        role = "enrolled" if reference_samples else "outside_probe" if probe_samples else "no_samples"
        items.append({"employee_id": person.id, "employee_code": person.code, "employee_name": person.name,
                      "enrollment_samples": reference_samples, "calibration_samples": probe_samples,
                      "calibration_collections": probe_collections, "role": role,
                      "missing_calibration_samples": max(0, MIN_PROBE_SAMPLES - probe_samples)})
    return {"items": items, "total": total, "offset": offset, "limit": limit,
            "model_id": engine.model_id, "minimum_probe_samples": MIN_PROBE_SAMPLES,
            "summary": {"enrolled_people": len(enrolled), "known_people_missing_probes": sum(v > 0 for v in missing.values()),
                        "known_probe_samples_missing": sum(missing.values()),
                        "outside_probe_people": len(outside), "outside_people_meeting_minimum": outside_ready,
                        "outside_people_missing": max(0, MIN_OUTSIDE_PEOPLE - outside_ready),
                        "enrolled_people_missing": max(0, MIN_ENROLLED_PEOPLE - len(enrolled)),
                        "data_coverage_ready": len(enrolled) >= MIN_ENROLLED_PEOPLE and not any(missing.values())
                        and len(outside) >= MIN_OUTSIDE_PEOPLE and outside_ready == len(outside)},
            "operational_enabled": False, "final_evaluation_used": False}
