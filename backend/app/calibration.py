"""Offline calibration; never reads final-evaluation vectors or enables attendance."""
import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select

from .matching import SCORING_RULE, Gallery, normalized
from .models import CollectionSample, Employee, FaceCollection

MIN_ENROLLED_PEOPLE = 10
MIN_PROBE_SAMPLES = 5
MIN_OUTSIDE_PEOPLE = 2


@dataclass(frozen=True)
class Sample:
    person: str
    collection: str
    purpose: str
    fingerprint: str
    vector: np.ndarray


def load_samples(db, model_id, dimensions=128):
    # Final-evaluation vectors must not influence selection, even accidentally.
    rows = db.execute(select(CollectionSample, FaceCollection).join(FaceCollection)
                      .join(Employee, FaceCollection.employee_id == Employee.id)
                      .where(Employee.active == True, FaceCollection.status == "complete",  # noqa: E712
                             FaceCollection.biometric_revision == Employee.biometric_revision,
                             FaceCollection.purpose.in_(["enrollment", "calibration"]),
                             FaceCollection.model_id == model_id)).all()
    samples = []
    for row, collection in rows:
        if row.model_id != model_id or row.dimensions != dimensions or len(row.vector) != dimensions * 4:
            raise ValueError("dataset_model_or_dimensions_mismatch")
        samples.append(Sample(collection.employee_id, collection.id, collection.purpose,
                              row.fingerprint, normalized(np.frombuffer(row.vector, dtype="<f4"), dimensions)))
    return samples


def same_person_diagnostics(enrolled, probes, model_id, dimensions):
    galleries={person:Gallery(model_id,{person:vectors},dimensions) for person,vectors in enrolled.items() if len(vectors)>=1}
    scores=sorted(galleries[person].rank(vector,model_id).first_score for person,vector in probes if person in galleries)
    if not scores:
        return None
    return {"measurement":"same_person_cross_session_cosine","samples":len(scores),
            "minimum":round(float(min(scores)),6),"median":round(float(np.median(scores)),6),
            "maximum":round(float(max(scores)),6),"mean":round(float(np.mean(scores)),6),
            "is_accuracy_percentage":False,"acceptance_threshold_selected":False}


def score_summary(values):
    if not values:
        return None
    return {"minimum": round(float(min(values)), 6), "median": round(float(np.median(values)), 6),
            "maximum": round(float(max(values)), 6)}


def compare_reference_caps(enrollment_frames, probes, model_id, dimensions):
    """Hold the people/probes fixed; never select references using probe scores."""
    if not enrollment_frames:
        return []
    ordered = {person: [vector for _, vector in sorted(frames, key=lambda item: item[0])]
               for person, frames in enrollment_frames.items()}
    reports = []
    for cap in (1, 3, 5):
        selected = {person: frames[:cap] for person, frames in ordered.items()}
        gallery = Gallery(model_id, selected, dimensions)
        correct, known_scores, margins, outsider_scores, known_people = 0, [], [], [], set()
        for person, vector in probes:
            rank = gallery.rank(vector, model_id)
            if person in selected:
                known_people.add(person)
                correct += int(rank.first_id == person)
                same_person = np.clip(gallery.samples[person] @ vector, -1, 1)
                known_scores.append(float(np.sort(same_person)[-3:].mean()))
                if rank.margin is not None:
                    margins.append(rank.margin)
            else:
                outsider_scores.append(rank.first_score)
        reports.append({"reference_cap": cap, "enrolled_people": len(selected),
                        "reference_images_used": sum(map(len, selected.values())),
                        "people_below_reference_cap": sum(len(frames) < cap for frames in ordered.values()),
                        "known_probe_people": len(known_people), "known_probe_samples": len(known_scores),
                        "known_top1_correct_samples": correct, "known_expected_person_scores": score_summary(known_scores),
                        "known_top1_margins": score_summary(margins),
                        "unknown_probe_samples": len(outsider_scores), "unknown_top1_scores": score_summary(outsider_scores),
                        "gallery_sufficient_for_top2": len(selected) >= 2, "identity_confirmed": False,
                        "threshold_selected": False, "operational_enabled": False})
    return reports


def calibrate(samples, model_id, dimensions=128):
    enrolled, probes = defaultdict(list), []
    enrollment_frames = defaultdict(list)
    fingerprints, collections, digest_records = set(), {}, []
    for sample in samples:
        if sample.purpose not in {"enrollment", "calibration"}:
            raise ValueError("final_evaluation_must_remain_unseen")
        if sample.fingerprint in fingerprints:
            raise ValueError("duplicate_frame_in_dataset")
        fingerprints.add(sample.fingerprint)
        membership = (sample.person, sample.purpose)
        if sample.collection in collections and collections[sample.collection] != membership:
            raise ValueError("collection_leakage")
        collections[sample.collection] = membership
        vector = normalized(sample.vector, dimensions)
        digest_records.append("|".join([sample.person, sample.collection, sample.purpose,
                                      sample.fingerprint, hashlib.sha256(vector.tobytes()).hexdigest()]))
        if sample.purpose == "enrollment":
            enrolled[sample.person].append(vector)
            enrollment_frames[sample.person].append((sample.fingerprint, vector))
        else:
            probes.append((sample.person, vector))
    digest = hashlib.sha256((model_id + SCORING_RULE + "\n".join(sorted(digest_records))).encode()).hexdigest()
    known = Counter(person for person, _ in probes if person in enrolled)
    unknown = Counter(person for person, _ in probes if person not in enrolled)
    reasons = []
    if len(enrolled) < MIN_ENROLLED_PEOPLE:
        reasons.append("Mốc kiểm chứng M1 theo kế hoạch cần ít nhất 10 người đăng ký. Với 1 người vẫn xem được điểm so khớp thử giữa các phiên.")
    if any(len(vectors) < 1 for vectors in enrolled.values()):
        reasons.append("Mỗi người cần ít nhất 1 mẫu đăng ký đạt chất lượng.")
    if any(known[person] < MIN_PROBE_SAMPLES for person in enrolled):
        reasons.append("Mỗi người đã đăng ký cần ít nhất 5 mẫu hiệu chỉnh ở phiên riêng.")
    if len(unknown) < MIN_OUTSIDE_PEOPLE or any(count < MIN_PROBE_SAMPLES for count in unknown.values()):
        reasons.append("Cần tối thiểu 2 người ngoài bộ đăng ký, mỗi người 5 mẫu hiệu chỉnh; đây chỉ là mức khởi đầu M1.")
    report = {"model_id": model_id, "scoring_rule": SCORING_RULE, "dataset_digest": digest,
              "coverage": {"enrolled_people": len(enrolled), "enrollment_samples": sum(map(len, enrolled.values())),
                           "known_probe_people": len(known), "known_probes": sum(known.values()),
                           "unknown_probe_people": len(unknown), "unknown_probes": sum(unknown.values()),
                           "completed_collections": len(collections)},
              "status": "insufficient_data", "reasons": reasons, "candidate": None,
              "same_person_diagnostics":same_person_diagnostics(enrolled,probes,model_id,dimensions),
              "reference_experiments": compare_reference_caps(enrollment_frames, probes, model_id, dimensions),
              "operational_enabled": False, "final_evaluation_used": False,
              "measurement_unit": "individual_sample_not_attendance_session",
              "identities_exported": False, "vectors_exported": False}
    if reasons:
        return report
    gallery = Gallery(model_id, enrolled, dimensions)
    rankings = [(person, gallery.rank(vector, model_id)) for person, vector in probes]
    score = np.array([rank.first_score for _, rank in rankings])
    margin = np.array([rank.margin for _, rank in rankings])
    is_known = np.array([person in enrolled for person, _ in rankings])
    correct = np.array([person == rank.first_id for person, rank in rankings]) & is_known
    unsafe = ~correct  # Includes both wrong identity and outsiders.
    best = None
    # Fixed, reproducible grid. Strict inequalities match the runtime decision.
    for threshold in np.arange(0, 101) / 100:
        for gap in np.arange(0, 201) / 100:
            accepted = (score > threshold) & (margin > gap)
            if np.any(accepted & unsafe):
                continue
            accepted_correct = int(np.count_nonzero(accepted & correct))
            if accepted_correct / sum(known.values()) < .98:
                continue
            choice = (accepted_correct, float(threshold), float(gap))
            if best is None or choice > best:
                best = choice
    if best is None:
        report.update(status="no_safe_candidate", reasons=["Chưa có cặp ngưỡng/khoảng cách đạt ≥98% mẫu đúng và không nhận nhầm trong tập hiệu chỉnh. Cần kiểm tra dữ liệu/ánh sáng, không tự hạ tiêu chí."])
        return report
    accepted_correct, threshold, gap = best
    report.update(status="candidate_requires_independent_evaluation", candidate={
        "threshold": threshold, "minimum_margin": gap, "correct_samples": accepted_correct,
        "known_samples": sum(known.values()), "wrong_identity_samples": 0, "accepted_unknown_samples": 0,
        "single_sample_correct_rate": accepted_correct / sum(known.values()),
        "empirical_only": True, "calibration_dataset_digest": digest})
    return report
