"""Fetch OpenCV Zoo models with Git LFS SHA256 verification and local licenses."""
import hashlib
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
MODELS.mkdir(exist_ok=True)
HEADERS = {"User-Agent": "ChamCongLocalSetup/0.1"}


def read(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=90) as response:
        return response.read()


manifest_path = MODELS / "manifest.json"
if manifest_path.exists():
    commit = json.loads(manifest_path.read_text())["source_commit"]
else:
    commit = json.loads(read("https://api.github.com/repos/opencv/opencv_zoo/commits/main"))["sha"]
assert re.fullmatch("[0-9a-f]{40}", commit)
specs = [
    ("detector", "face_detection_yunet", "face_detection_yunet_2023mar.onnx", "MIT"),
    ("recognizer", "face_recognition_sface", "face_recognition_sface_2021dec.onnx", "Apache-2.0"),
]
entries = []
for kind, directory, filename, license_id in specs:
    relative = f"models/{directory}/{filename}"
    raw_url = f"https://raw.githubusercontent.com/opencv/opencv_zoo/{commit}/{relative}"
    pointer = read(raw_url)
    oid = re.search(rb"oid sha256:([0-9a-f]{64})", pointer)
    expected = oid.group(1).decode() if oid else hashlib.sha256(pointer).hexdigest()
    destination = MODELS / filename
    if not destination.exists() or hashlib.sha256(destination.read_bytes()).hexdigest() != expected:
        content = read(f"https://media.githubusercontent.com/media/opencv/opencv_zoo/{commit}/{relative}") if oid else pointer
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f"Model checksum mismatch: {kind}")
        temporary = destination.with_suffix(".tmp")
        temporary.write_bytes(content)
        temporary.replace(destination)
    license_url = f"https://raw.githubusercontent.com/opencv/opencv_zoo/{commit}/models/{directory}/LICENSE"
    (MODELS / f"LICENSE_{directory}.txt").write_bytes(read(license_url))
    entries.append({"kind": kind, "filename": filename, "sha256": expected, "bytes": destination.stat().st_size,
                    "source": raw_url, "license": license_id, "license_source": license_url})
    print(f"Verified {kind}: {destination.stat().st_size} bytes", flush=True)
manifest = {"model_id": f"yunet2023mar-sface2021dec-{commit[:12]}", "source_commit": commit,
            "embedding_dimensions": 128, "runtime": "OpenCV 4.x CPU", "models": entries}
manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
fixtures = ROOT / ".runtime/fixtures"
fixtures.mkdir(exist_ok=True)
fixture_url = f"https://raw.githubusercontent.com/opencv/opencv_zoo/{commit}/models/face_recognition_sface/example_outputs/demo.jpg"
fixture = read(fixture_url)
fixture_oid = re.search(rb"oid sha256:([0-9a-f]{64})", fixture)
if fixture_oid:
    fixture = read(f"https://media.githubusercontent.com/media/opencv/opencv_zoo/{commit}/models/face_recognition_sface/example_outputs/demo.jpg")
    if hashlib.sha256(fixture).hexdigest() != fixture_oid.group(1).decode():
        raise ValueError("Fixture checksum mismatch")
(fixtures / "sface_demo.jpg").write_bytes(fixture)
(fixtures / "source.json").write_text(json.dumps({"source": fixture_url, "license": "Apache-2.0 (OpenCV Zoo directory license)", "use": "Technical smoke test only, not an accuracy dataset"}, indent=2), encoding="utf-8")
print("Model manifest and licenses saved; no external API is used for inference")

