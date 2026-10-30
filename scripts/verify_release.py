"""Install a release offline in a fresh venv and smoke-test its relocated app."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--name", required=True)
args = parser.parse_args()
release = (ROOT / ".runtime/releases" / args.name).resolve()
if not release.is_relative_to((ROOT / ".runtime/releases").resolve()):
    raise ValueError("Not a project release")
manifest = json.loads((release / "release-manifest.json").read_text(encoding="utf-8"))
for name, expected in manifest["files"].items():
    path = (release / name).resolve()
    if not path.is_relative_to(release):
        raise ValueError("Release path escapes its root")
    with path.open("rb") as source:
        actual = hashlib.file_digest(source, "sha256").hexdigest()
    if actual != expected:
        raise ValueError("Release checksum mismatch")
    if path.name == ".env" or path.suffix in {".bak", ".dump"} or name.startswith(("data/", "evidence/", "logs/")):
        raise ValueError("Private state found in release")
verification = ROOT / ".runtime/release-verification" / (release.name + "-" + uuid4().hex[:8])
verification.mkdir(parents=True)
venv = verification / ".venv"
subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
python = venv / "Scripts/python.exe"
env = {key: value for key, value in os.environ.items() if not key.startswith("CHAMCONG_")}
env.update(PYTHONIOENCODING="utf-8", CHAMCONG_FUNCTIONAL_TRIAL_ENABLED="false", CHAMCONG_DATABASE_URL="sqlite://")
commands = [
    [str(python), "-m", "pip", "install", "--no-index", "--find-links", "wheels",
     "--requirement", "backend/requirements.lock", "--disable-pip-version-check"],
    [str(python), "-c", '''
import ipaddress, json, socket, sys
from pathlib import Path
connect=socket.socket.connect
def local_only(sock, address):
    if not ipaddress.ip_address(address[0]).is_loopback:
        raise RuntimeError("External network access forbidden during offline check")
    return connect(sock,address)
socket.socket.connect=local_only
sys.path.insert(0,"backend")
from app.main import app
from app.database import Base, get_session
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
# This smoke check must never resolve a default URL to the real local SQL DB.
# Vendor-specific behavior is covered separately by the native SQL Server suite.
isolated=create_engine("sqlite://",poolclass=StaticPool,connect_args={"check_same_thread":False})
Base.metadata.create_all(isolated)
def sessions():
    with Session(isolated) as db:
        yield db
app.dependency_overrides[get_session]=sessions
with TestClient(app) as client:
    response=client.get("/")
    assert response.status_code==200 and "<html" in response.text
    assert app.state.face_engine is not None and app.state.pad_engine is not None
    for path in Path("frontend/dist").rglob("*"):
        if path.is_file():
            assert client.get("/"+path.relative_to("frontend/dist").as_posix()).status_code==200
    for path in ("/.env","/models/manifest.json","/backend/app/models.py","/models/speech/faster-whisper-small/model.bin"):
        assert client.get(path).status_code==404
    assert client.get("/health/live").status_code==200
    status=client.get("/api/system/status").json()
    assert status["attendance_enabled"] is False
    if Path('models/speech/faster-whisper-small/manifest.json').is_file():
        from app.partner_speech import validate_model
        validate_model(Path('models/speech/faster-whisper-small'))
        app.state.partner_speech.timeout=60
        draft=app.state.partner_speech.transcribe(Path('frontend/dist/audio/hop-le-user-fast-135.wav').read_bytes())
        assert draft and len(draft)<=160
app.dependency_overrides.clear()
isolated.dispose()
from app.native_backup import source_files
private_config=Path(".env")
assert not private_config.exists()
try:
    private_config.write_text("CHAMCONG_FUNCTIONAL_TRIAL_ENABLED=false",encoding="utf-8")
    assert all(path.is_file() for path in source_files(Path.cwd()).values())
finally:
    private_config.unlink(missing_ok=True)
print(json.dumps({"relocated_models_ready":True,"compiled_frontend_and_audio_ready":True,"external_network_blocked":True,"private_paths_denied":True}))
'''],
]
for index, command in enumerate(commands):
    result = subprocess.run(command, cwd=release, env=env, capture_output=True, text=True, encoding="utf-8")
    (verification / f"step-{index}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        print((result.stdout + result.stderr)[-5000:])
        raise SystemExit(result.returncode)
report = {"release": args.name, "manifest_files_verified": len(manifest["files"]),
          "fresh_venv_offline_install": True, "relocated_cpu_models_ready": True,
          "compiled_frontend_and_audio_served_by_backend": True,
          "private_paths_denied": True, "external_python_network_blocked": True,
          "native_backup_source_helpers_present": True,
          "relocated_offline_speech_pipeline": manifest.get("local_speech_model_included",False),
          "isolated_smoke_database": True, "verification_venv_outside_public_release": True,
          "live_database_opened": False,
          "private_data_bundled": False, "live_database_modified": False}
(ROOT / "evidence/m5").mkdir(exist_ok=True)
(ROOT / "evidence/m5/native-release-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report))
