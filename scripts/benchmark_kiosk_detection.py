"""Compare a proposed detector input cap without changing any operational setting or threshold."""

import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import get_settings  # noqa: E402
from app.database import session_factory  # noqa: E402
from app.face_engine import FaceEngine  # noqa: E402
from app.models import ImportedFacePhoto  # noqa: E402
from app.quality import assess_quality  # noqa: E402


def detect(engine, image, edge):
    height, width = image.shape[:2]
    if edge and max(width, height) > edge:
        scale = edge / max(width, height)
        small = cv2.resize(image, (round(width*scale), round(height*scale)), interpolation=cv2.INTER_AREA)
        faces = engine.detect(small).copy()
        faces[:, :14:2] *= width / small.shape[1]
        faces[:, 1:14:2] *= height / small.shape[0]
        return faces
    return engine.detect(image)


def run(engine, content, edge):
    start = perf_counter()
    image = engine.decode(content)
    faces = detect(engine, image, edge)
    quality = assess_quality(image, faces)
    vector = engine.extract(image, faces[0])[0] if quality["accepted"] else None
    return vector, quality, perf_counter()-start


def scene(image):
    height, width = image.shape[:2]
    scale = min(1, 600/height, 1200/width)
    photo = cv2.resize(image, (round(width*scale), round(height*scale)), interpolation=cv2.INTER_AREA)
    result = np.full((720, 1280, 3), 140, dtype=np.uint8)
    top, left = (720-photo.shape[0])//2, (1280-photo.shape[1])//2
    result[top:top+photo.shape[0], left:left+photo.shape[1]] = photo
    valid, encoded = cv2.imencode(".jpg", result, [cv2.IMWRITE_JPEG_QUALITY, 88])
    assert valid
    return encoded.tobytes()


def main():
    engine = FaceEngine(get_settings().models_dir)
    public = cv2.imdecode(np.frombuffer((ROOT/".runtime/fixtures/sface_demo.jpg").read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    x, y, width, height = engine.detect(public)[0][:4]
    crop = public[max(0, int(y-height*.15)):min(public.shape[0], int(y+height*1.15)),
                  max(0, int(x-width*.15)):min(public.shape[1], int(x+width*1.15))]
    content = scene(cv2.resize(crop, (480, 480)))
    original = run(engine, content, None)[0]
    timing = []
    for edge in (None, 960, 640):
        samples, cosines = [], []
        with ThreadPoolExecutor(max_workers=2) as pool:
            for vector, quality, duration in pool.map(lambda _, limit=edge: run(engine, content, limit), range(20)):
                assert quality["accepted"]
                samples.append(duration)
                cosines.append(float(original @ vector))
        timing.append({"detector_max_edge": edge, "two_workers": True, "samples": len(samples),
                       "p95_ms": round(float(np.percentile(samples, 95))*1000, 3),
                       "minimum_cosine_to_original_same_public_image": round(min(cosines), 6)})
    with session_factory()() as db:
        photos = [bytes(row.image) for row in db.scalars(select(ImportedFacePhoto).where(
            ImportedFacePhoto.sample_id.is_not(None) | (ImportedFacePhoto.quality["reason"].as_string() == "multiple_faces")))]
    transitions, cosines, both = Counter(), [], 0
    for photo in photos:
        content = scene(engine.decode(photo))
        baseline, before, _ = run(engine, content, None)
        proposed, after, _ = run(engine, content, 640)
        transitions[before["reason"]+" -> "+after["reason"]] += 1
        if baseline is not None and proposed is not None:
            both += 1
            cosines.append(float(baseline @ proposed))
    report = {"production_configuration_modified": False, "model_or_threshold_modified": False,
              "licensed_public_fixture_timings": timing, "local_photo_comparisons": len(photos),
              "comparison_canvas_pixels": [1280, 720], "candidate_detector_max_edge": 640,
              "quality_transitions": dict(transitions), "both_accepted": both,
              "same_image_embedding_cosine_min": round(min(cosines), 6) if cosines else None,
              "same_image_embedding_cosine_median": round(float(np.median(cosines)), 6) if cosines else None,
              "independent_accuracy_or_pad_validation": False,
              "real_camera_controls_reprocessed": False, "images_vectors_or_identities_exported": False}
    (ROOT/"evidence/m5/kiosk-detector-proposal.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
