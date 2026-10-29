"""Explicit local-file import for diagnostic enrollment; never enables attendance."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
from fastapi import HTTPException
from sqlalchemy import select

from .biometric_state import lock_employee
from .employees import EmployeeInput
from .face_engine import FaceInputError
from .models import AuditLog, CollectionSample, Employee, FaceCollection, ImportedFacePhoto

IMPORT_PROTOCOL = "imported-photo-v1"


def prepare_import(manifest_path, engine, max_bytes=2_000_000, *, entries=None, max_people=100):
    path = Path(manifest_path).resolve(strict=True)
    if path.stat().st_size > 1_000_000:
        raise ValueError("manifest_too_large")
    manifest = json.loads(path.read_text(encoding="utf-8-sig")) if entries is None else entries
    if not 1 <= max_people <= 1000 or not isinstance(manifest, list) or not 1 <= len(manifest) <= max_people:
        raise ValueError("manifest_people_limit_exceeded")
    records, codes, fingerprints, total = [], set(), set(), 0
    for record in manifest:
        # Metadata is provided by the operator; identity is never inferred from pixels.
        person = EmployeeInput(
            code=record["code"], name=record["name"], department=record.get("department", "")
        )
        local = record["localFile"]
        if not isinstance(local, str) or Path(local).is_absolute():
            raise ValueError("local_file_must_be_relative")
        image_path = (path.parent / local).resolve(strict=True)
        if not image_path.is_relative_to(path.parent) or not image_path.is_file():
            raise ValueError("local_file_outside_manifest_directory")
        if image_path.stat().st_size > max_bytes:
            raise ValueError("image_too_large")
        content = image_path.read_bytes()
        total += len(content)
        if total > 100_000_000:
            raise ValueError("import_exceeds_100mb")
        engine.decode(content, max_bytes)
        content_type = (
            "image/png"
            if content.startswith(b"\x89PNG\r\n\x1a\n")
            else "image/jpeg"
            if content.startswith(b"\xff\xd8")
            else "image/webp"
        )
        fingerprint = hashlib.sha256(content).hexdigest()
        if person.code in codes or fingerprint in fingerprints:
            raise ValueError("duplicate_employee_or_image_in_manifest")
        codes.add(person.code)
        fingerprints.add(fingerprint)
        try:
            vector, metadata = engine.analyze(content, max_bytes)
            quality = metadata["quality"] | {
                "source": IMPORT_PROTOCOL,
                "capture_mode": "import",
                "model_id": engine.model_id,
            }
        except FaceInputError as error:
            vector = None
            quality = error.details | {
                "accepted": False,
                "reason": error.code,
                "source": IMPORT_PROTOCOL,
                "capture_mode": "import",
                "model_id": engine.model_id,
            }
        records.append(
            {
                "person": person,
                "image": content,
                "fingerprint": fingerprint,
                "content_type": content_type,
                "vector": vector,
                "quality": quality,
            }
        )
    return records


def save_import(db, records, engine, reason, *, commit=True):
    if not 5 <= len(reason.strip()) <= 500:
        raise ValueError("import_reason_required")
    batch = str(uuid4())
    now = datetime.now(UTC)
    created_people = created_photos = samples = reused = 0
    people = {}
    # Validate conflicts for the complete batch before changing an existing profile.
    for item in records:
        person = item["person"]
        existing = db.scalar(select(Employee).where(Employee.code == person.code))
        if existing and (
            existing.name != person.name or existing.department != person.department or not existing.active
        ):
            raise HTTPException(
                409, "Mã nhân viên đã có hồ sơ khác hoặc đã ngừng hoạt động; chưa nhập bộ ảnh."
            )
        if not existing:
            existing = Employee(**person.model_dump())
            db.add(existing)
            db.flush()
            created_people += 1
        people[person.code] = existing
    for person in sorted(people.values(), key=lambda row: row.id):
        lock_employee(db, person.id, active_only=True)
        db.refresh(person)
    for item in records:
        person = people[item["person"].code]
        photo = db.scalar(
            select(ImportedFacePhoto).where(ImportedFacePhoto.fingerprint == item["fingerprint"])
        )
        if photo:
            if (
                photo.employee_id != person.id
                or photo.model_id != engine.model_id
                or photo.biometric_revision != person.biometric_revision
            ):
                raise HTTPException(409, "Ảnh đã liên kết hồ sơ/model khác; chưa nhập bộ ảnh.")
            reused += 1
            continue
        if db.scalar(
            select(CollectionSample.id).where(
                CollectionSample.fingerprint == item["fingerprint"],
                CollectionSample.model_id == engine.model_id,
            )
        ):
            raise HTTPException(
                409, "Ảnh đã nằm trong một bộ mẫu khác; tránh dùng trùng bộ đăng ký/kiểm tra."
            )
        sample_id = None
        if item["vector"] is not None:
            vector = np.asarray(item["vector"], dtype="<f4")
            if (
                vector.shape != (engine.dimensions,)
                or not np.isfinite(vector).all()
                or not np.isclose(np.linalg.norm(vector), 1, atol=1e-4)
            ):
                raise ValueError("invalid_import_vector")
            collection = FaceCollection(
                employee_id=person.id,
                model_id=engine.model_id,
                biometric_revision=person.biometric_revision,
                purpose="enrollment",
                guidance_protocol=IMPORT_PROTOCOL,
                status="complete",
                sample_count=1,
                created_at=now,
                expires_at=now,
                completed_at=now,
            )
            db.add(collection)
            db.flush()
            sample = CollectionSample(
                collection_id=collection.id,
                position=1,
                fingerprint=item["fingerprint"],
                model_id=engine.model_id,
                vector=vector.tobytes(),
                dimensions=engine.dimensions,
                quality=item["quality"],
            )
            db.add(sample)
            db.flush()
            sample_id = sample.id
            samples += 1
        db.add(
            ImportedFacePhoto(
                employee_id=person.id,
                sample_id=sample_id,
                fingerprint=item["fingerprint"],
                batch_id=batch,
                image=item["image"],
                content_type=item["content_type"],
                model_id=engine.model_id,
                biometric_revision=person.biometric_revision,
                quality=item["quality"],
            )
        )
        created_photos += 1
    counts = {
        "profiles_created": created_people,
        "photos_stored": created_photos,
        "samples_stored": samples,
        "photos_reused": reused,
        "rejected_photos_stored_for_review": created_photos - samples,
    }
    if created_photos or created_people:
        db.add(
            AuditLog(
                action="employee_photo_import",
                entity_id=batch,
                reason=reason,
                details=counts
                | {
                    "model_id": engine.model_id,
                    "operational_enrollment": False,
                    "remote_urls_accessed": False,
                },
            )
        )
    if commit:
        db.commit()
    else:
        db.flush()
    return counts | {"batch_id": batch, "attendance_enabled": False, "operational_templates_created": 0}
