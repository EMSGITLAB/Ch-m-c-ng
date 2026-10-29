"""Encrypted deletion floor outside SQL backups, merged before any recovery."""

import json
import os
from pathlib import Path
from uuid import UUID

from cryptography.fernet import InvalidToken
from sqlalchemy import delete, select

from .models import AuditLog, CollectionSample, Employee, FaceCollection, FaceTemplate, ImportedFacePhoto
from .private_storage import protect_directory, recovery_key, seal, unseal
from .runtime_supervisor import FileLease


def validate(value):
    if not isinstance(value, dict) or value.get("schema") != 1 or not isinstance(value.get("subjects"), dict):
        raise ValueError("Invalid revocation ledger")
    for subject, revision in value["subjects"].items():
        if str(UUID(subject)) != subject or type(revision) is not int or revision < 1:
            raise ValueError("Invalid revocation entry")
    return value["subjects"]


def read_ledger(runtime):
    path = Path(runtime) / "privacy/revocations.fernet"
    if not path.exists():
        return {}
    if path.stat().st_size > 2_000_000:
        raise ValueError("Revocation ledger is unexpectedly large")
    try:
        return validate(json.loads(unseal(path.read_bytes(), recovery_key(runtime))))
    except InvalidToken as error:
        raise ValueError("Revocation ledger authentication failed") from error


def merge_ledger(runtime, subjects, *, mirror_directory=None):
    validate({"schema": 1, "subjects": subjects})
    runtime = Path(runtime)
    key = recovery_key(runtime, create=True)
    directory = runtime / "privacy"
    if not directory.exists():
        protect_directory(directory)
    lease = FileLease(directory / "revocations.lock")
    try:
        merged = read_ledger(runtime)
        mirror = None
        if mirror_directory is not None:
            destination = Path(mirror_directory)
            if not destination.is_dir():
                raise ValueError("Revocation mirror device is unavailable")
            mirror = destination / "chamcong_revocations.fernet"
            if mirror.exists():
                with mirror.open("rb") as source:
                    external = source.read(2_000_001)
                if len(external) > 2_000_000:
                    raise ValueError("Revocation mirror is unexpectedly large")
                try:
                    mirrored = validate(json.loads(unseal(external, key)))
                except InvalidToken as error:
                    raise ValueError("External revocation mirror authentication failed") from error
                for subject, revision in mirrored.items():
                    merged[subject] = max(merged.get(subject, 0), revision)
        for subject, revision in subjects.items():
            merged[subject] = max(merged.get(subject, 0), revision)
        payload = seal(json.dumps({"schema": 1, "subjects": merged}, sort_keys=True).encode(), key)
        if mirror is not None:
            staged = mirror.with_suffix(".tmp")
            with staged.open("wb") as target:
                target.write(payload)
                target.flush()
                os.fsync(target.fileno())
            staged.replace(mirror)
        temporary = directory / "revocations.tmp"
        temporary.write_bytes(payload)
        temporary.replace(directory / "revocations.fernet")
        return merged
    finally:
        lease.close()


def sync_from_audit(db, runtime, *, mirror_directory=None):
    subjects = {}
    for row in db.scalars(select(AuditLog).where(AuditLog.action == "biometrics_purge")).all():
        revision = row.details.get("revision")
        if row.entity_id and type(revision) is int and revision >= 1:
            subjects[row.entity_id] = max(subjects.get(row.entity_id, 0), revision)
    return merge_ledger(runtime, subjects, mirror_directory=mirror_directory)


def apply_to_restored_database(db, subjects):
    validate({"schema": 1, "subjects": subjects})
    affected = 0
    for subject, revision in subjects.items():
        employee = db.get(Employee, subject)
        if not employee:
            continue
        collection_ids = select(FaceCollection.id).where(FaceCollection.employee_id == subject,
                                                        FaceCollection.biometric_revision < revision)
        db.execute(delete(ImportedFacePhoto).where(ImportedFacePhoto.employee_id == subject,
                                                  ImportedFacePhoto.biometric_revision < revision))
        db.execute(delete(CollectionSample).where(CollectionSample.collection_id.in_(collection_ids)))
        db.execute(delete(FaceCollection).where(FaceCollection.id.in_(collection_ids)))
        db.execute(delete(FaceTemplate).where(FaceTemplate.employee_id == subject,
                                             FaceTemplate.biometric_revision < revision))
        if employee.biometric_revision < revision:
            employee.biometric_revision = revision
            affected += 1
    return affected
