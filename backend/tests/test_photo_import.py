import hashlib
import json

import numpy as np
import pytest
from app.face_engine import FaceEngine, FaceInputError
from app.imported_photos import rank_references
from app.main import app
from app.models import CollectionSample, Employee, FaceCollection, FaceTemplate, ImportedFacePhoto
from app.photo_import import prepare_import, save_import
from fastapi import HTTPException
from PIL import Image
from sqlalchemy import func, select
from test_admin import setup


class Engine:
    model_id = "import-unit-test-model"
    dimensions = 4
    decode = staticmethod(FaceEngine.decode)

    def analyze(self, content, max_bytes=2_000_000):
        image = self.decode(content, max_bytes)
        if image.mean() < 100:
            raise FaceInputError("face_too_small", {"face_count": 1, "box": [10, 10, 70, 70]})
        return np.array([1, 0, 0, 0], dtype="<f4"), {"quality": {"accepted": True, "reason": "accepted"}}


def test_deferred_import_keeps_parent_transaction_rollback_atomic(client, manifest):
    _, factory = client
    path, _ = manifest
    records = prepare_import(path, Engine())
    with factory() as db:
        summary = save_import(db, records, Engine(), "Transaction rollback fixture", commit=False)
        assert summary["profiles_created"] == 2
        assert db.scalar(select(func.count()).select_from(ImportedFacePhoto)) == 2
        db.rollback()
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Employee)) == 0
        assert db.scalar(select(func.count()).select_from(ImportedFacePhoto)) == 0


@pytest.fixture
def manifest(tmp_path):
    rows = []
    for index, color in enumerate([150, 20]):
        local = tmp_path / f"test{index}.png"
        Image.new("RGB", (160, 160), (color, color, color)).save(local)
        rows.append(
            {
                "code": f"TEST{index}",
                "name": f"Hồ sơ thử {index}",
                "department": "Phòng thử",
                "localFile": local.name,
                "imageUrl": "https://invalid.example/never-accessed",
            }
        )
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return path, rows


def test_import_stores_rejected_original_and_one_sample_without_operational_templates(client, manifest):
    browser, factory = client
    path, _ = manifest
    records = prepare_import(path, Engine())
    assert records[0]["quality"]["accepted"]
    assert records[1]["vector"] is None
    with factory() as db:
        first = save_import(db, records, Engine(), "Người dùng cung cấp ảnh thử")
    assert first["profiles_created"] == 2 and first["photos_stored"] == 2 and first["samples_stored"] == 1
    assert first["operational_templates_created"] == 0
    with factory() as db:
        second = save_import(db, records, Engine(), "Thử lại sau mất phản hồi")
        assert second["photos_reused"] == 2 and second["profiles_created"] == 0
        assert db.scalar(select(func.count()).select_from(ImportedFacePhoto)) == 2
        assert db.scalar(select(func.count()).select_from(CollectionSample)) == 1
        assert db.scalar(select(func.count()).select_from(FaceTemplate)) == 0
        collection = db.scalar(select(FaceCollection))
        assert collection.sample_count == 1 and collection.status == "complete"
    headers = {"X-CSRF-Token": setup(browser)}
    photos = browser.get("/api/admin/imported-face-photos").json()["items"]
    assert len(photos) == 2 and sum(item["accepted"] for item in photos) == 1
    assert all(item["imported_photo_count"] == 1 for item in browser.get("/api/admin/employees").json()["items"])
    accepted = next(item for item in photos if item["accepted"])
    response = browser.get(f"/api/admin/imported-face-photos/{accepted['id']}/image")
    assert response.content == records[0]["image"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"] == "image/png"
    collections = browser.get(f"/api/admin/employees/{accepted['employee_id']}/collections").json()["items"]
    assert collections[0]["minimum_samples"] == 1 and not collections[0]["operational_enrollment"]
    endpoint = f"/api/admin/employees/{accepted['employee_id']}/biometrics"
    assert browser.get(endpoint).json()["images_stored"]
    purge = browser.post(
        endpoint + "/purge",
        headers=headers,
        json={
            "confirm_employee_code": accepted["employee_code"],
            "expected_revision": 0,
            "reason": "Xóa dữ liệu ảnh thử",
        },
    )
    assert purge.status_code == 200, purge.text
    assert purge.json()["imported_photos_deleted"] == 1
    assert browser.get(f"/api/admin/imported-face-photos/{accepted['id']}/image").status_code == 404
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(CollectionSample)) == 0
        assert db.scalar(select(func.count()).select_from(ImportedFacePhoto)) == 1
        assert db.scalar(select(func.count()).select_from(Employee)) == 2


def test_import_conflict_rolls_back_entire_batch_without_overwriting_existing_profile(client, manifest):
    _, factory = client
    path, _ = manifest
    records = prepare_import(path, Engine())
    with factory() as db:
        db.add(Employee(code="TEST1", name="Hồ sơ có trước", department="Phòng khác"))
        db.commit()
    with factory() as db, pytest.raises(HTTPException) as error:
        save_import(db, records, Engine(), "Thử kiểm tra xung đột")
    assert error.value.status_code == 409
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Employee)) == 1
        assert db.scalar(select(Employee.name)) == "Hồ sơ có trước"
        assert db.scalar(select(func.count()).select_from(ImportedFacePhoto)) == 0


@pytest.mark.parametrize("change", ["traversal", "absolute", "duplicate_code", "duplicate_photo"])
def test_manifest_rejects_unsafe_paths_or_duplicate_identity(manifest, change):
    path, rows = manifest
    if change == "traversal":
        outside = path.parent.parent / "outside.png"
        Image.new("RGB", (160, 160)).save(outside)
        rows[0]["localFile"] = "../outside.png"
    elif change == "absolute":
        rows[0]["localFile"] = str(path.parent / rows[0]["localFile"])
    elif change == "duplicate_code":
        rows[1]["code"] = rows[0]["code"]
    else:
        rows[1]["localFile"] = rows[0]["localFile"]
    path.write_text(json.dumps(rows), encoding="utf-8")
    with pytest.raises(ValueError):
        prepare_import(path, Engine())


def test_probe_is_explicit_diagnostic_no_write_and_self_file_is_labelled(client, manifest):
    browser, factory = client
    records = prepare_import(manifest[0], Engine())
    with factory() as db:
        save_import(db, records, Engine(), "Nhập dữ liệu bộ thử")
    headers = {"X-CSRF-Token": setup(browser), "Content-Type": "image/png"}
    engine_before = app.state.face_engine
    app.state.face_engine = Engine()
    try:
        assert (
            browser.post("/api/admin/imported-face-photos/probe", content=records[0]["image"]).status_code
            == 403
        )
        response = browser.post(
            "/api/admin/imported-face-photos/probe", headers=headers, content=records[0]["image"]
        )
        assert response.status_code == 200, response.text
        report = response.json()
        assert report["candidates"][0]["cosine"] == 1 and report["candidates"][0]["same_reference_file"]
        assert not report["identity_confirmed"] and not report["attendance_recorded"]
        assert (
            browser.post(
                "/api/admin/imported-face-photos/probe", headers=headers, content=records[1]["image"]
            ).status_code
            == 422
        )
        with factory() as db:
            person = db.scalar(select(Employee).where(Employee.code == "TEST0"))
            person.active = False
            db.commit()
            assert (
                rank_references(
                    db, Engine(), np.array([1, 0, 0, 0]), hashlib.sha256(records[0]["image"]).hexdigest()
                )["reference_count"]
                == 0
            )
        browser.cookies.clear()
        assert browser.get("/api/admin/imported-face-photos").status_code == 401
        assert (
            browser.post(
                "/api/admin/imported-face-photos/probe", headers=headers, content=records[0]["image"]
            ).status_code
            == 401
        )
    finally:
        app.state.face_engine = engine_before
