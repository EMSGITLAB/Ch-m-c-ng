from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from app.face_engine import FaceInputError
from app.main import app
from app.models import AttendanceEvent, CollectionSample, FaceCollection, FaceTemplate
from sqlalchemy import func, select
from test_admin import setup


class SampleEngine:
    model_id="test-model"

    def analyze(self,content,max_bytes):
        if content==b"blurred":
            raise FaceInputError("blurred",{"accepted":False})
        vector=np.zeros(128,dtype=np.float32)
        vector[0]=1
        position=int(chr(content[-1])) % 5 if content[-1:].isdigit() else 0
        yaw,pitch=[(0,.5),(.09,.5),(-.09,.5),(0,.42),(0,.58)][position]
        return vector,{"quality":{"accepted":True,"face_count":1,"yaw_ratio":yaw,"pitch_ratio":pitch,"roll_degrees":0}}


@pytest.fixture
def collection_client(client):
    browser,factory=client
    app.state.face_engine=SampleEngine()
    csrf=setup(browser)
    headers={"X-CSRF-Token":csrf}
    employee=browser.post("/api/admin/employees",json={"code":"NV01","name":"Nhân viên thử"},headers=headers).json()
    return browser,factory,headers,employee["id"]


def create(browser,headers,employee,purpose="enrollment"):
    response=browser.post(f"/api/admin/employees/{employee}/collections",json={"purpose":purpose},headers=headers)
    assert response.status_code==201,response.text
    return response.json()


def capture(browser,headers,collection,content):
    return browser.post(f"/api/admin/collections/{collection}/samples",content=content,headers=headers)


def test_collect_five_distinct_samples_without_operational_enrollment(collection_client):
    browser,factory,headers,employee=collection_client
    session=create(browser,headers,employee)
    assert session["next_instruction"]["pose"]=="front"
    assert browser.post(f"/api/admin/collections/{session['id']}/complete",headers=headers).status_code==409
    for number in range(5):
        response=capture(browser,headers,session["id"],f"sample-{number}".encode())
        assert response.status_code==201,response.text
        assert response.json()["collection"]["sample_count"]==number+1
        assert response.json()["image_saved"] is False
        assert response.json()["feedback"].startswith("Đạt kiểm tra sơ bộ")
        assert "vector" not in response.json()
    assert capture(browser,headers,session["id"],b"sample-0").status_code==409
    completed=browser.post(f"/api/admin/collections/{session['id']}/complete",headers=headers)
    assert completed.status_code==200
    assert completed.json()["sample_count"]==5
    assert completed.json()["operational_enrollment"] is False
    assert browser.post(f"/api/admin/collections/{session['id']}/complete",headers=headers).status_code==200
    assert capture(browser,headers,session["id"],b"new-sample").status_code==409
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(CollectionSample))==5
        assert db.scalar(select(func.count()).select_from(FaceTemplate))==0
        assert db.scalar(select(func.count()).select_from(AttendanceEvent))==0
        assert len(db.scalar(select(CollectionSample)).vector)==512


def test_keep_dataset_splits_distinct_and_prevent_exact_frame_reuse(collection_client):
    browser,_,headers,employee=collection_client
    enrollment=create(browser,headers,employee,"enrollment")
    calibration=create(browser,headers,employee,"calibration")
    evaluation=create(browser,headers,employee,"evaluation")
    assert len({row["id"] for row in [enrollment,calibration,evaluation]})==3
    assert capture(browser,headers,enrollment["id"],b"same-frame").status_code==201
    assert capture(browser,headers,calibration["id"],b"same-frame").status_code==409
    sessions=browser.get(f"/api/admin/employees/{employee}/collections").json()["items"]
    assert {row["purpose"] for row in sessions}=={"enrollment","calibration","evaluation"}
    assert next(row for row in sessions if row["id"]==calibration["id"])["sample_count"]==0


def test_quality_rejection_and_cancellation(collection_client):
    browser,factory,headers,employee=collection_client
    session=create(browser,headers,employee)
    rejected=capture(browser,headers,session["id"],b"blurred")
    assert rejected.status_code==422
    assert "Chưa đạt" in rejected.json()["feedback"]
    assert capture(browser,headers,session["id"],b"clear").status_code==201
    cancelled=browser.post(f"/api/admin/collections/{session['id']}/cancel",headers=headers)
    assert cancelled.status_code==200
    assert cancelled.json()["sample_count"]==0
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(CollectionSample))==0
    assert capture(browser,headers,session["id"],b"other").status_code==409


def test_wrong_direction_does_not_advance_and_correct_retry_succeeds(collection_client):
    browser,factory,headers,employee=collection_client
    session=create(browser,headers,employee)
    first=capture(browser,headers,session["id"],b"frame-0")
    assert first.json()["collection"]["next_instruction"]["pose"]=="left"
    wrong=capture(browser,headers,session["id"],b"wrong-2")
    assert wrong.status_code==422
    assert wrong.json()["reason"]=="wrong_pose"
    assert "Chưa đạt" in wrong.json()["feedback"]
    assert wrong.json()["next_instruction"]["position"]==2
    with factory() as db:
        assert db.get(FaceCollection,session["id"]).sample_count==1
        assert db.scalar(select(func.count()).select_from(CollectionSample))==1
    assert capture(browser,headers,session["id"],b"retry-1").status_code==201


def test_legacy_collection_is_not_relabelled_or_given_unverified_guidance(collection_client):
    browser,factory,headers,employee=collection_client
    session=create(browser,headers,employee)
    with factory() as db:
        row=db.get(FaceCollection,session["id"])
        row.guidance_protocol=None
        db.commit()
    assert capture(browser,headers,session["id"],b"fresh-0").status_code==409
    listed=browser.get(f"/api/admin/employees/{employee}/collections").json()["items"][0]
    assert listed["next_instruction"] is None
    assert listed["guidance_protocol"] is None


def test_expired_session_and_model_change_are_rejected(collection_client):
    browser,factory,headers,employee=collection_client
    session=create(browser,headers,employee)
    with factory() as db:
        row=db.get(FaceCollection,session["id"])
        row.expires_at=datetime.now(UTC)-timedelta(seconds=1)
        db.commit()
    assert capture(browser,headers,session["id"],b"new").status_code==409
    session=create(browser,headers,employee)
    app.state.face_engine.model_id="changed-model"
    assert capture(browser,headers,session["id"],b"new").status_code==409


def test_collection_permissions_and_ten_sample_limit(collection_client):
    browser,_,headers,employee=collection_client
    session=create(browser,headers,employee)
    assert capture(browser,{},session["id"],b"missing-csrf").status_code==403
    for number in range(10):
        assert capture(browser,headers,session["id"],f"image-{number}".encode()).status_code==201
    assert capture(browser,headers,session["id"],b"too-many").status_code==409
    browser.cookies.clear()
    assert browser.get(f"/api/admin/employees/{employee}/collections").status_code==401


def test_expired_capture_session_still_allows_finalizing_already_valid_samples(collection_client):
    browser,factory,headers,employee=collection_client
    session=create(browser,headers,employee)
    for number in range(5):
        assert capture(browser,headers,session["id"],f"kept-{number}".encode()).status_code==201
    with factory() as db:
        db.get(FaceCollection,session["id"]).expires_at=datetime.now(UTC)-timedelta(seconds=1)
        db.commit()
    assert capture(browser,headers,session["id"],b"after-expiry").status_code==409
    completed=browser.post(f"/api/admin/collections/{session['id']}/complete",headers=headers)
    assert completed.status_code==200
    assert completed.json()["sample_count"]==5
    assert completed.json()["status"]=="complete"
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(CollectionSample))==5
