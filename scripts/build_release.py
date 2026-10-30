"""Build a relocatable local Windows release from an explicit public allowlist."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(destination, *, download_wheels=False, wheelhouse=None):
    destination = Path(destination).resolve()
    releases = (ROOT / ".runtime/releases").resolve()
    if not destination.is_relative_to(releases) or destination == releases:
        raise ValueError("Release destination must be a new child of .runtime/releases")
    if destination.exists():
        raise ValueError("Never overwrite an existing release")
    if download_wheels and wheelhouse:
        raise ValueError("Choose an offline wheelhouse or download, not both")
    destination.mkdir(parents=True)
    for source_name in ("backend/app", "backend/migrations", "frontend/dist", "models/pad"):
        source = ROOT / source_name
        if not source.is_dir():
            raise ValueError("Missing release input: " + source_name)
        shutil.copytree(source, destination / source_name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.part", "*.tmp"))
    (destination / "models").mkdir(exist_ok=True)
    for source in (ROOT / "models").iterdir():
        if source.is_file() and source.suffix in {".onnx", ".json", ".md", ".txt"}:
            shutil.copy2(source, destination / "models" / source.name)
    speech = ROOT / "models/speech/faster-whisper-small"
    speech_included = (speech / "manifest.json").is_file()
    if speech_included:
        # Public, pinned weights are in the offline installer, never backups.
        sys.path.insert(0, str(ROOT / "backend"))
        from app.partner_speech import MODEL_FILES, validate_model
        validate_model(speech)
        speech_target = destination / "models/speech/faster-whisper-small"
        speech_target.mkdir(parents=True)
        for name in sorted(MODEL_FILES | {"manifest.json"}):
            shutil.copy2(speech / name, speech_target / name)
    public_files = ["backend/alembic.ini", "backend/requirements.lock", "backend/requirements.in",
                    "config/business.json", "pyproject.toml", "THIRD_PARTY_NOTICES.md", "README.md",
                    "HUONG_DAN_VAN_HANH.md", "scripts/start_backend.ps1", "scripts/setup_release.ps1",
                    "scripts/migrate_local.py", "scripts/enable_functional_trial.py",
                    "scripts/verify_functional_trial.py", "scripts/run_service.py", "scripts/start_service.ps1",
                    "scripts/install_autostart.ps1", "scripts/backup_local.py", "scripts/start_local.ps1",
                    "scripts/restart_backend.ps1", "scripts/start_sqlserver.py", "scripts/stage_upgrade.py",
                    "scripts/configure_sql_telemetry_egress.ps1"]
    public_files.extend(["scripts/vscode_run.ps1", "scripts/import_employee_photos.py", "scripts/import_employee_dataset.py", "scripts/prepare_profile_references.py", "scripts/configure_trial_shift.py"])
    public_files.extend(["models/speech/README.md", "models/speech/LICENSE_Whisper.txt", "models/speech/LICENSE_faster_whisper.txt"])
    public_files.append("docs/CHAM_CONG_DOI_TAC.md")
    for name in public_files:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    # No database, credentials, evidence, screenshots, photos, vectors or runtime state.
    (destination / "config/server.env.example").write_text(
        "CHAMCONG_DATABASE_URL=<local SQL Server SQLAlchemy ODBC URL>\n"
        "CHAMCONG_SESSION_SECRET=<generate a new random secret, minimum 32 characters>\n"
        "CHAMCONG_ENVIRONMENT=production\n"
        "CHAMCONG_FUNCTIONAL_TRIAL_ENABLED=false\n", encoding="utf-8")
    if download_wheels:
        subprocess.run([sys.executable, "-m", "pip", "download", "--only-binary=:all:",
                        "--requirement", str(ROOT / "backend/requirements.lock"),
                        "--dest", str(destination / "wheels"), "--disable-pip-version-check"], check=True,
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    elif wheelhouse:
        wheels = sorted(Path(wheelhouse).glob("*.whl"))
        if not wheels:
            raise ValueError("Offline wheelhouse is empty")
        (destination / "wheels").mkdir()
        for wheel in wheels:
            shutil.copy2(wheel, destination / "wheels" / wheel.name)
    manifest = {"schema": 1, "target": "Windows x64 / Python 3.12", "docker": False,
                "local_speech_model_included": speech_included,
                "frontend_served_by_backend": True, "private_data_included": False,
                "offline_wheels_included": bool(download_wheels or wheelhouse),
                "recovery_contract": "authenticated-v2-external-deletion-ledger", "files": {}}
    for path in sorted(destination.rglob("*")):
        if path.is_file():
            with path.open("rb") as stream:
                manifest["files"][path.relative_to(destination).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
    (destination / "release-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--download-wheels", action="store_true")
    parser.add_argument("--wheelhouse", type=Path)
    args = parser.parse_args()
    manifest = build(ROOT / ".runtime/releases" / args.name, download_wheels=args.download_wheels, wheelhouse=args.wheelhouse)
    print(json.dumps({key: value for key, value in manifest.items() if key != "files"}
                     | {"file_count": len(manifest["files"])}))
