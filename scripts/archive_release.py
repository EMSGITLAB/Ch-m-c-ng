"""Create a deployable ZIP from verified manifest entries, never a recursive directory copy."""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.upgrade import verify_candidate  # noqa: E402


def file_digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def archive_release(directory, output):
    directory, manifest = verify_candidate(directory)
    output = Path(output).resolve()
    if output.suffix.lower() != ".zip" or output.exists():
        raise ValueError("Use a new ZIP path; existing archives are never overwritten")
    if output.is_relative_to(directory):
        raise ValueError("Store the archive outside its input release")
    if "release-manifest.json" in manifest["files"]:
        raise ValueError("Manifest cannot include itself")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".release-", suffix=".part", dir=output.parent)
    os.close(descriptor)
    temporary = Path(temporary)
    expected = dict(manifest["files"])
    expected["release-manifest.json"] = file_digest(directory / "release-manifest.json")
    destination_created = False
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
            for name in sorted(expected):
                archive.write(directory / name, arcname=name)
        # Re-read every member: verifies its CRC and the manifest SHA, including
        # source files changed between candidate validation and archive creation.
        with zipfile.ZipFile(temporary) as archive:
            if len(archive.namelist()) != len(expected) or set(archive.namelist()) != set(expected):
                raise ValueError("Archive member list differs from the public manifest")
            for name, digest in expected.items():
                with archive.open(name) as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                        raise ValueError("Archive checksum mismatch")
        # Exclusive destination creation also handles another publisher racing us.
        with output.open("xb") as destination:
            destination_created = True
            with temporary.open("rb") as source:
                shutil.copyfileobj(source, destination)
                destination.flush()
                os.fsync(destination.fileno())
    except BaseException:
        if destination_created:
            output.unlink(missing_ok=True)
        raise
    finally:
        temporary.unlink(missing_ok=True)
    return {"release": directory.name, "archive": output.name, "manifest_files": len(manifest["files"]),
            "zip_members": len(expected), "archive_sha256": file_digest(output), "archive_bytes": output.stat().st_size,
            "all_members_checksum_verified": True, "manifest_entries_only": True,
            "unlisted_runtime_or_venv_included": False, "private_data_included": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    releases = (ROOT / ".runtime/releases").resolve()
    directory = (releases / args.name).resolve()
    if directory == releases or not directory.is_relative_to(releases):
        raise ValueError("Not a project release")
    report = archive_release(directory, directory.with_suffix(".zip"))
    (ROOT / "evidence/m5/release-archive-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
