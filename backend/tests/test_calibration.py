from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from app.calibration import Sample, calibrate, load_samples
from app.models import CollectionSample, Employee, FaceCollection


def dataset():
    samples = []
    for person in range(12):
        for purpose in (["enrollment", "calibration"] if person < 10 else ["calibration"]):
            for number in range(5):
                vector = np.eye(12, dtype=np.float32)[person]
                samples.append(Sample(str(person), f"{person}-{purpose}", purpose,
                                      f"{person}-{purpose}-{number}", vector))
    return samples


def test_no_threshold_with_single_person_or_missing_outsiders():
    report = calibrate([], "m", 12)
    assert report["status"] == "insufficient_data"
    assert report["candidate"] is None
    assert report["operational_enabled"] is False
    samples = [sample for sample in dataset() if sample.person == "0"]
    assert calibrate(samples, "m", 12)["candidate"] is None
    assert calibrate([s for s in dataset() if int(s.person) < 10], "m", 12)["candidate"] is None


def test_reference_experiments_run_before_coverage_is_sufficient_and_do_not_select_threshold():
    def vector(x, y):
        return np.array([x, y], dtype=np.float32)
    samples = [Sample("a", "a-enroll", "enrollment", "a0", vector(1, 1)),
               *[Sample("a", "a-enroll", "enrollment", f"a{i}", vector(1, 0)) for i in range(1, 4)],
               Sample("b", "b-enroll", "enrollment", "b0", vector(0, 1)),
               Sample("a", "a-probe", "calibration", "probe", vector(1, 0))]
    report = calibrate(samples, "m", 2)
    assert report["status"] == "insufficient_data" and report["candidate"] is None
    assert not report["operational_enabled"]
    variants = report["reference_experiments"]
    assert [row["reference_cap"] for row in variants] == [1, 3, 5]
    assert [row["reference_images_used"] for row in variants] == [2, 4, 5]
    assert [row["people_below_reference_cap"] for row in variants] == [0, 1, 2]
    assert variants[0]["known_expected_person_scores"]["minimum"] == pytest.approx(.707107)
    assert variants[-1]["known_expected_person_scores"]["minimum"] == 1
    assert all(row["known_probe_samples"] == 1 and row["known_probe_people"] == 1
               and not row["threshold_selected"] for row in variants)
    assert calibrate(list(reversed(samples)), "m", 2)["reference_experiments"] == variants


def test_reference_experiments_without_probe_do_not_fabricate_accuracy():
    samples = [s for s in dataset() if s.purpose == "enrollment"]
    report = calibrate(samples, "m", 12)
    assert all(row["known_probe_samples"] == 0 and row["known_expected_person_scores"] is None
               for row in report["reference_experiments"])
    assert report["candidate"] is None


def test_single_person_has_cross_session_scores_without_implying_calibration():
    samples=[sample for sample in dataset() if sample.person=="0"]
    report=calibrate(samples,"m",12)
    diagnostics=report["same_person_diagnostics"]
    assert diagnostics["samples"]==5
    assert diagnostics["minimum"]==1
    assert diagnostics["median"]==1
    assert diagnostics["is_accuracy_percentage"] is False
    assert report["status"]=="insufficient_data"
    assert report["candidate"] is None
    assert report["operational_enabled"] is False


def test_candidate_is_reproducible_private_and_never_enables_operation():
    report = calibrate(dataset(), "m", 12)
    reverse = calibrate(list(reversed(dataset())), "m", 12)
    assert report == reverse
    assert report["status"] == "candidate_requires_independent_evaluation"
    assert report["candidate"]["correct_samples"] == 50
    assert report["candidate"]["wrong_identity_samples"] == 0
    assert report["coverage"]["unknown_probes"] == 10
    assert report["operational_enabled"] is False
    assert report["final_evaluation_used"] is False
    assert report["identities_exported"] is False
    modified = dataset()
    first = modified[0]
    modified[0] = Sample(first.person, first.collection, first.purpose, "changed", first.vector)
    assert calibrate(modified, "m", 12)["dataset_digest"] != report["dataset_digest"]


def test_indistinguishable_people_produce_no_safe_candidate():
    samples = [Sample(s.person, s.collection, s.purpose, s.fingerprint, np.eye(12)[0]) for s in dataset()]
    report = calibrate(samples, "m", 12)
    assert report["status"] == "no_safe_candidate"
    assert report["candidate"] is None


def test_single_reference_still_requires_independent_known_and_outsider_probes():
    samples = [s for s in dataset() if s.purpose != "enrollment" or s.fingerprint.endswith("-0")]
    report = calibrate(samples, "m", 12)
    assert report["coverage"]["enrollment_samples"] == 10
    assert report["status"] == "candidate_requires_independent_evaluation"
    assert report["candidate"]["known_samples"] == 50
    assert report["same_person_diagnostics"]["samples"] == 50
    assert not report["operational_enabled"]
    references_only = [s for s in samples if s.purpose == "enrollment"]
    missing = calibrate(references_only, "m", 12)
    assert missing["candidate"] is None
    assert missing["coverage"]["known_probes"] == 0
    assert missing["status"] == "insufficient_data"


def test_final_set_duplicate_frame_and_collection_leakage_are_rejected():
    samples = dataset()
    first = samples[0]
    with pytest.raises(ValueError, match="final_evaluation_must_remain_unseen"):
        calibrate([Sample("a", "c", "evaluation", "f", first.vector)], "m", 12)
    with pytest.raises(ValueError, match="duplicate_frame"):
        calibrate([first, first], "m", 12)
    with pytest.raises(ValueError, match="collection_leakage"):
        calibrate([first, Sample("other", first.collection, "calibration", "unique", first.vector)], "m", 12)


def test_sql_loader_excludes_final_evaluation_inactive_and_other_models(client):
    _, factory = client
    with factory() as db:
        active = Employee(code="A", name="Test")
        inactive = Employee(code="B", name="Inactive", active=False)
        db.add_all([active, inactive])
        db.flush()
        for index, (employee, purpose, model, status) in enumerate([
            (active, "enrollment", "m", "complete"), (active, "calibration", "m", "complete"),
            (active, "evaluation", "m", "complete"), (inactive, "calibration", "m", "complete"),
            (active, "calibration", "old", "complete"), (active, "calibration", "m", "open"),
        ]):
            collection = FaceCollection(employee_id=employee.id, purpose=purpose, model_id=model, status=status,
                                        sample_count=1, expires_at=datetime.now(UTC)+timedelta(minutes=1))
            db.add(collection)
            db.flush()
            # Invalid vectors in the final set must never even be decoded.
            vector = b"unreadable" if purpose == "evaluation" else np.eye(128, dtype="<f4")[0].tobytes()
            db.add(CollectionSample(collection_id=collection.id, position=1, fingerprint=str(index),
                                    model_id=model, dimensions=128, vector=vector, quality={}))
        db.commit()
        loaded = load_samples(db, "m")
        assert len(loaded) == 2
        assert {sample.purpose for sample in loaded} == {"enrollment", "calibration"}
