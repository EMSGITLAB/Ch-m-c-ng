import hashlib
import json

import pytest
from app.upgrade import CONTRACT, verify_candidate


def candidate(tmp_path):
    required = ["backend/app/main.py", "backend/app/native_backup.py", "backend/requirements.lock",
                "backend/alembic.ini", "models/manifest.json", "frontend/dist/index.html", "scripts/run_service.py",
                "wheels/test-fixture.whl"]
    manifest = {"schema": 1, "private_data_included": False, "recovery_contract": CONTRACT,
                "offline_wheels_included": True, "files": {}}
    for name in required:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"Verification fixture only; not an installable release")
        manifest["files"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "release-manifest.json").write_text(json.dumps(manifest))
    return manifest


def test_candidate_contract_and_checksum_reject_old_or_modified_release(tmp_path):
    manifest = candidate(tmp_path)
    assert verify_candidate(tmp_path)[0] == tmp_path
    (tmp_path / "backend/app/main.py").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        verify_candidate(tmp_path)
    manifest.pop("recovery_contract")
    (tmp_path / "release-manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="contracts"):
        verify_candidate(tmp_path)


@pytest.mark.parametrize("path", ["../outside", "/absolute", "C:/outside", "models\\outside", ".env",
                                      ".runtime/keys/backup.key", "data/photo.png", "backup.ccbackup", ""])
def test_candidate_rejects_private_and_escaping_paths_before_copy(tmp_path, path):
    manifest = candidate(tmp_path)
    manifest["files"][path] = "test-only"
    (tmp_path / "release-manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Unsafe/private"):
        verify_candidate(tmp_path)
