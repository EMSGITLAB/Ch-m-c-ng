import importlib.util
import json
import zipfile
from pathlib import Path

import pytest
from test_upgrade import candidate

spec = importlib.util.spec_from_file_location(
    "archive_release_script", Path(__file__).resolve().parents[2] / "scripts/archive_release.py")
archiver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archiver)


def test_archive_contains_only_verified_manifest_not_private_unlisted_state(tmp_path):
    root = tmp_path / "release"
    root.mkdir()
    manifest = candidate(root)
    for name in (".env", ".runtime/keys/backup.key", ".venv/private.txt", "data/person.jpg"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"private unlisted fixture")
    output = tmp_path / "release.zip"
    report = archiver.archive_release(root, output)
    with zipfile.ZipFile(output) as archive:
        assert set(archive.namelist()) == set(manifest["files"]) | {"release-manifest.json"}
        assert json.loads(archive.read("release-manifest.json")) == manifest
        assert archive.testzip() is None
    assert report["archive_sha256"] == archiver.file_digest(output)
    assert report["all_members_checksum_verified"] is True


def test_archive_rejects_changed_input_without_publishing(tmp_path):
    root = tmp_path / "release"
    root.mkdir()
    candidate(root)
    (root / "backend/app/main.py").write_bytes(b"modified")
    output = tmp_path / "release.zip"
    with pytest.raises(ValueError, match="checksum"):
        archiver.archive_release(root, output)
    assert not output.exists()


def test_archive_preserves_existing_destination_and_rejects_input_destination(tmp_path):
    root = tmp_path / "release"
    root.mkdir()
    candidate(root)
    output = tmp_path / "release.zip"
    output.write_bytes(b"existing archive fixture")
    with pytest.raises(ValueError, match="never overwritten"):
        archiver.archive_release(root, output)
    assert output.read_bytes() == b"existing archive fixture"
    with pytest.raises(ValueError, match="outside"):
        archiver.archive_release(root, root / "nested.zip")


def test_archive_write_failure_removes_only_its_partial_output(tmp_path, monkeypatch):
    root = tmp_path / "release"
    root.mkdir()
    candidate(root)
    output = tmp_path / "release.zip"
    original_copy = archiver.shutil.copyfileobj

    def fail_copy(source, destination, length=0):
        if getattr(destination, "name", None) == str(output):
            destination.write(b"partial")
            raise OSError("simulated full destination")
        return original_copy(source, destination, length)

    monkeypatch.setattr(archiver.shutil, "copyfileobj", fail_copy)
    with pytest.raises(OSError, match="simulated"):
        archiver.archive_release(root, output)
    assert not output.exists()
    assert not list(tmp_path.glob(".release-*.part"))
