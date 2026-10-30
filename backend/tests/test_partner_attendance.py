"""Synthetic identity vectors verify transactions, never recognition accuracy/PAD."""

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import numpy as np
import pytest
from app import partner_attendance as service
from app.attendance import live_device
from app.devices import KIOSK_COOKIE
from app.face_engine import FaceInputError
from app.main import app
from app.models import (
    Device,
    Employee,
    PartnerBatch,
    PartnerCapture,
    PartnerDeviceBinding,
    PartnerEvent,
    PartnerWorker,
)
from fastapi import HTTPException
from sqlalchemy import func, select
from test_partner_admin import partner_setup as partner_setup

ROOT = "/api/kiosk/partners"
QUALITY = {"accepted": True, "frame_width": 640, "frame_height": 480, "box": [100, 100, 150, 150]}


class SyntheticEngine:
    model_id = "test-only-model"
    dimensions = 128

    def analyze(self, content):
        if content.startswith(b"bad"):
            raise FaceInputError("blurred", {"accepted": False})
        vector = np.zeros(128, dtype=np.float32)
        vector[0 if content.startswith(b"A") else 1] = 1
        return vector, {"quality": dict(QUALITY), "model_id": self.model_id}

    def inspect(self, content):
        _, metadata = self.analyze(content)
        return None, None, metadata


@pytest.fixture
def partner_kiosk(partner_setup, monkeypatch):
    browser, factory, admin_headers, _, create, activate, transition = partner_setup
    batch_id = create()[0].json()["id"]
    activate()
    # partner_setup already owns the state restoration for this attribute.
    # Assign the concrete fake within that lifetime instead of stacking two
    # monkeypatch attribute deletions on Starlette's dynamic State object.
    app.state.face_engine = SyntheticEngine()
    assert transition(batch_id, "draft", "open").status_code == 200
    clock = [datetime.now(UTC)]
    monkeypatch.setattr(service, "utcnow", lambda: clock[0])
    tokens = ["partner-test-token-"+str(index) for index in range(2)]
    ids = []
    with factory() as db:
        batch = db.get(PartnerBatch, batch_id)
        batch.starts_at = clock[0]-timedelta(hours=1)
        batch.ends_at = clock[0]+timedelta(hours=4)
        batch.admission_from = clock[0]-timedelta(hours=2)
        batch.checkout_until = clock[0]+timedelta(hours=6)
        for token in tokens:
            device = Device(name="Test partner kiosk", direction="in", active=True,
                token_hash=hashlib.sha256(token.encode()).hexdigest(), token_expires_at=clock[0]+timedelta(days=1))
            db.add(device)
            db.flush()
            ids.append(device.id)
            db.add(PartnerDeviceBinding(device_id=device.id, batch_id=batch_id))
        db.commit()

    def actor(index=0):
        browser.cookies.set(KIOSK_COOKIE, tokens[index])

    def start(index=0):
        actor(index)
        identity = str(uuid4())
        response = browser.post(ROOT+"/captures", json={"request_id": identity},
                                headers={"X-Kiosk-Intent": "start-partner-capture"})
        assert response.status_code == 201, response.text
        return identity, response.json()

    def frame(identity, state, person, number):
        clock[0] += timedelta(seconds=.5)
        content = f"{person}:{identity}:{number}".encode()
        response = browser.post(ROOT+f"/captures/{identity}/frames/{number}", content=content,
            headers={"Content-Type": "image/jpeg", "X-Kiosk-Intent": "capture-partner-face", "X-Capture-Nonce": state["capture_nonce"]})
        assert response.status_code == 200, response.text
        return response.json()

    def capture(person="A", index=0):
        identity, state = start(index)
        for number in range(1, 4):
            state = frame(identity, state, person, number)
        return identity, state

    def name(identity, worker, value="Nguyễn Văn Thử"):
        return browser.put(ROOT+f"/workers/{worker['id']}/name", json={"name": value,
            "source": "manual", "expected_revision": worker["name_revision"], "proof_id": identity},
            headers={"X-Kiosk-Intent": "confirm-partner-name"})

    def commit(identity):
        return browser.post(ROOT+f"/captures/{identity}/commit", json={},
                             headers={"X-Kiosk-Intent": "record-partner-attendance"})

    def admitted():
        identity, state = capture()
        worker = state["worker"]
        result = name(identity, worker)
        assert result.status_code == 200, result.text
        assert result.json()["admission_approved"]
        identity, state = capture()
        result = commit(identity)
        assert result.status_code == 200, result.text
        return state["worker"], result.json()

    return {"browser": browser, "factory": factory, "headers": admin_headers, "batch_id": batch_id,
            "clock": clock, "tokens": tokens, "ids": ids, "actor": actor, "start": start,
            "frame": frame, "capture": capture, "name": name, "commit": commit, "admitted": admitted}


def test_name_and_same_face_automatically_admit_worker_without_admin_approval(partner_kiosk):
    k = partner_kiosk
    from app.auth import COOKIE
    k["browser"].cookies.delete(COOKIE)
    identity, state = k["capture"]()
    assert state["state"] == "verified" and state["action"] == "name_required"
    context = k["browser"].get(ROOT+"/context").json()
    assert context["admission_mode"] == context["batch"]["admission_mode"] == "automatic"
    worker = state["worker"]
    assert worker["state"] == "pending" and worker["code"].endswith("-C0001-00001")
    assert k["commit"](identity).status_code == 409
    with k["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(Employee)) == 0
        assert db.scalar(select(func.count()).select_from(PartnerWorker)) == 1
        assert db.scalar(select(func.count()).select_from(PartnerEvent)) == 0
    named = k["name"](identity, worker)
    assert named.status_code == 200 and named.json()["name_confirmed"]
    assert named.json()["admission_approved"] and named.json()["admission_mode"] == "automatic"
    with k["factory"]() as db:
        saved = db.get(PartnerWorker, worker["id"])
        assert saved.approved_by is None and saved.approved_at is not None
        assert db.scalar(select(func.count()).select_from(PartnerEvent)) == 0
    # Confirmation retired its proof; a fresh current face is still required.
    assert k["commit"](identity).status_code == 409
    fresh, after = k["capture"]()
    assert after["worker"]["id"] == worker["id"] and after["action"] == "record_in"
    recorded = k["commit"](fresh)
    assert recorded.status_code == 200 and recorded.json()["status"] == "recorded"
    assert recorded.json()["worker_name"] == "Nguyễn Văn Thử"
    assert k["commit"](fresh).json() == recorded.json()


def test_previously_named_pending_session_finishes_automatically_with_fresh_proof(partner_kiosk):
    k = partner_kiosk
    identity, state = k["capture"]()
    worker = state["worker"]
    assert k["name"](identity, worker).status_code == 200
    with k["factory"]() as db:
        saved = db.get(PartnerWorker, worker["id"])
        saved.approved_at = saved.approved_by = None
        db.commit()
    fresh, current = k["capture"]()
    assert current["action"] == "record_in" and not current["worker"]["admission_approved"]
    assert k["commit"](fresh).status_code == 200
    with k["factory"]() as db:
        saved = db.get(PartnerWorker, worker["id"])
        assert saved.state == "active" and saved.approved_at and saved.approved_by is None
        assert db.scalar(select(func.count()).select_from(PartnerEvent)) == 1


def test_automatic_admission_cannot_revive_an_expired_named_session(partner_kiosk):
    k = partner_kiosk
    identity, state = k["capture"]()
    worker = state["worker"]
    assert k["name"](identity, worker).status_code == 200
    fresh, _ = k["capture"]()
    with k["factory"]() as db:
        saved = db.get(PartnerWorker, worker["id"])
        saved.pending_expires_at = k["clock"][0]
        saved.approved_at = saved.approved_by = None
        db.commit()
    assert k["commit"](fresh).status_code == 410
    with k["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(PartnerEvent)) == 0


def test_popup_confirmation_proof_never_reserves_a_new_code_for_a_different_face(partner_kiosk):
    k=partner_kiosk
    _,state=k['capture']()
    worker=state['worker']
    assert (datetime.fromisoformat(worker['pending_expires_at'])-k['clock'][0]).total_seconds()==300
    proof=str(uuid4())
    result=k['browser'].post(ROOT+'/captures',json={'request_id':proof,'expected_worker_id':worker['id']},headers={'X-Kiosk-Intent':'start-partner-capture'})
    assert result.status_code==201,result.text
    failed=k['frame'](proof,result.json(),'B',1)
    assert failed['state']=='rejected' and failed['worker']['id']==worker['id']
    with k['factory']() as db:
        assert db.scalar(select(func.count()).select_from(PartnerWorker))==1
        assert db.get(PartnerBatch,k['batch_id']).next_number==1
        assert db.scalar(select(func.count()).select_from(PartnerEvent))==0
    proof=str(uuid4())
    result=k['browser'].post(ROOT+'/captures',json={'request_id':proof,'expected_worker_id':worker['id']},headers={'X-Kiosk-Intent':'start-partner-capture'})
    current=result.json()
    for index in range(1,4):
        current=k['frame'](proof,current,'A',index)
    assert current['state']=='verified' and current['worker']['code']==worker['code']
    assert k['name'](proof,worker).status_code==200
    k['actor'](1)
    assert k['browser'].post(ROOT+'/captures',json={'request_id':str(uuid4()),'expected_worker_id':worker['id']},headers={'X-Kiosk-Intent':'start-partner-capture'}).status_code==409


def test_partner_device_direction_api_and_stale_proof_do_not_create_punch(partner_kiosk):
    k = partner_kiosk
    _, _ = k["admitted"]()
    device = k["browser"].get("/api/kiosk/device").json()
    assert device["workflow"] == "partner" and device["partner_batch_id"] == k["batch_id"]
    changed = k["browser"].patch("/api/kiosk/device", json={"direction": "out"},
        headers={"X-Kiosk-Intent": "change-direction"})
    assert changed.status_code == 200 and changed.json()["workflow"] == "partner"
    proof, _ = k["capture"]()
    k["clock"][0] += timedelta(seconds=11)
    assert k["commit"](proof).status_code == 409
    with k["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(PartnerEvent)) == 1


def test_overnight_batch_keeps_start_workdate_code_and_same_worker_after_midnight(partner_kiosk):
    k = partner_kiosk
    with k["factory"]() as db:
        batch = db.get(PartnerBatch, k["batch_id"])
        start = datetime(2026, 10, 30, 15, tzinfo=UTC)  # 22:00 Vietnam
        batch.starts_at, batch.ends_at = start, start+timedelta(hours=8)
        batch.admission_from, batch.checkout_until = start-timedelta(hours=1), start+timedelta(hours=10)
        db.commit()
    k["clock"][0] = datetime(2026, 10, 30, 17, 30, tzinfo=UTC)  # 00:30 next local day
    worker, first = k["admitted"]()
    assert "-20261030-" in first["worker_code"]
    with k["factory"]() as db:
        db.get(Device, k["ids"][0]).direction = "out"
        db.commit()
    k["clock"][0] += timedelta(hours=3)
    proof, state = k["capture"]()
    result = k["commit"](proof)
    assert result.status_code == 200 and result.json()["direction"] == "out"
    assert result.json()["worker_code"] == first["worker_code"]
    with k["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(PartnerWorker)) == 1
        assert db.scalar(select(func.count()).select_from(PartnerEvent)) == 2


def test_same_person_keeps_code_on_both_devices_before_and_after_checkout(partner_kiosk):
    k = partner_kiosk
    worker, first = k["admitted"]()
    identity, state = k["capture"](index=1)
    assert state["worker"]["code"] == worker["code"]
    duplicate_in = k["commit"](identity).json()
    assert duplicate_in["status"] == "duplicate" and duplicate_in["event_id"] == first["event_id"]
    with k["factory"]() as db:
        db.get(Device, k["ids"][1]).direction = "out"
        db.commit()
    identity, state = k["capture"](index=1)
    result = k["commit"](identity)
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "recorded" and result.json()["direction"] == "out"
    identity, state = k["capture"](index=1)
    assert k["commit"](identity).json()["status"] == "duplicate"
    identity, state = k["capture"](index=0)
    done = k["commit"](identity).json()
    assert done["status"] == "duplicate" and done["already_completed"]
    with k["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(PartnerWorker)) == 1
        assert db.scalar(select(func.count()).select_from(PartnerEvent)) == 2
        assert db.get(PartnerBatch, k["batch_id"]).next_number == 1


def test_pending_face_at_another_device_cannot_get_a_second_code_or_change_name(partner_kiosk):
    k = partner_kiosk
    _, first = k["capture"]()
    identity, second = k["capture"](index=1)
    assert first["worker"]["code"] == second["worker"]["code"]
    assert not second["owned_enrollment"]
    assert k["name"](identity, second["worker"]).status_code == 409


def test_partner_binding_cannot_be_used_for_employee_recognition(partner_kiosk):
    k = partner_kiosk
    digest = hashlib.sha256(k["tokens"][0].encode()).hexdigest()
    with k["factory"]() as db:
        with pytest.raises(HTTPException) as error:
            live_device(db, k["ids"][0], digest, k["clock"][0])
        assert error.value.status_code == 409
        assert live_device(db, k["ids"][0], digest, k["clock"][0], workflow="partner").id == k["ids"][0]


def test_final_frame_retry_after_response_loss_returns_same_code_and_old_request_is_device_owned(partner_kiosk):
    k = partner_kiosk
    identity, final = k["capture"]()
    with k["factory"]() as db:
        row = db.get(PartnerCapture, identity)
        supplied = service.nonce(row, 3)
    retry = k["browser"].post(ROOT+f"/captures/{identity}/frames/3", content=f"A:{identity}:3".encode(),
        headers={"Content-Type": "image/jpeg", "X-Kiosk-Intent": "capture-partner-face", "X-Capture-Nonce": supplied})
    assert retry.status_code == 200 and retry.json() == final
    k["actor"](1)
    assert k["browser"].get(ROOT+f"/captures/{identity}").status_code == 404
    with k["factory"]() as db:
        assert db.get(PartnerBatch, k["batch_id"]).next_number == 1


def test_pending_name_expiry_and_clock_regression_never_commit_attendance(partner_kiosk):
    k = partner_kiosk
    identity, final = k["capture"]()
    original = k["clock"][0]
    k["clock"][0] -= timedelta(seconds=2)
    assert k["commit"](identity).status_code == 503
    k["clock"][0] = original+timedelta(seconds=service.PENDING_TTL+1)
    assert k["name"](identity, final["worker"]).status_code == 410
    with k["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(PartnerEvent)) == 0


def test_capacity_counts_pending_people_and_cancellation_never_reuses_the_number(partner_kiosk):
    k = partner_kiosk
    with k["factory"]() as db:
        db.get(PartnerBatch, k["batch_id"]).capacity = 1
        db.commit()
    _, first = k["capture"]()
    _, second = k["capture"]("B", index=1)
    assert second["state"] == "rejected" and "worker" not in second
    k["actor"](0)
    cancelled = k["browser"].post(ROOT+f"/workers/{first['worker']['id']}/cancel", json={},
                                   headers={"X-Kiosk-Intent": "cancel-partner-admission"})
    assert cancelled.status_code == 200
    _, second = k["capture"]("B", index=1)
    assert second["worker"]["code"].endswith("-00002")
    assert second["worker"]["code"] != first["worker"]["code"]


def test_name_requires_recent_same_face_and_late_revisions_cannot_overwrite(partner_kiosk):
    k = partner_kiosk
    identity, state = k["capture"]()
    worker = state["worker"]
    k["clock"][0] += timedelta(seconds=11)
    assert k["name"](identity, worker).status_code == 409
    fresh, same = k["capture"]()
    named = k["name"](fresh, same["worker"])
    assert named.status_code == 200
    # Retry after response loss does not advance the revision again.
    assert k["name"](fresh, same["worker"]).json() == named.json()
    stale = k["name"](fresh, same["worker"], "Tên từ kết quả giọng nói cũ")
    assert stale.status_code == 409
    assert k["browser"].get(ROOT+f"/workers/{worker['id']}").json()["name"] == "Nguyễn Văn Thử"


def test_unknown_out_never_reserves_a_code_and_wrong_direction_cannot_commit(partner_kiosk):
    k = partner_kiosk
    with k["factory"]() as db:
        db.get(Device, k["ids"][0]).direction = "out"
        db.commit()
    _, state = k["capture"]()
    assert state["state"] == "rejected" and "worker" not in state
    with k["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(PartnerWorker)) == 0
        db.get(Device, k["ids"][0]).direction = "in"
        db.commit()
    identity, _ = k["capture"]()
    with k["factory"]() as db:
        db.get(Device, k["ids"][0]).direction = "out"
        db.commit()
    assert k["commit"](identity).status_code == 409


def test_bad_quality_nonce_and_identity_change_never_allocate_worker(partner_kiosk):
    k = partner_kiosk
    identity, state = k["start"]()
    invalid = k["browser"].post(ROOT+f"/captures/{identity}/frames/1", content=b"A:bad-nonce",
        headers={"Content-Type": "image/jpeg", "X-Kiosk-Intent": "capture-partner-face", "X-Capture-Nonce": "0"*64})
    assert invalid.status_code == 403
    state = k["frame"](identity, state, "bad", 1)
    assert state["stable_frames"] == 0
    state = k["frame"](identity, state, "A", 2)
    state = k["frame"](identity, state, "B", 3)
    assert state["state"] == "rejected"
    with k["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(PartnerWorker)) == 0


def test_lost_receipt_recovers_after_batch_closes_but_revoked_device_does_not(partner_kiosk):
    k = partner_kiosk
    _, first = k["admitted"]()
    identity = first["request_id"]
    with k["factory"]() as db:
        db.get(PartnerBatch, k["batch_id"]).state = "closed"
        db.commit()
    assert k["browser"].get(ROOT+f"/captures/{identity}").json()["receipt"] == first
    assert k["commit"](identity).json() == first
    with k["factory"]() as db:
        db.get(Device, k["ids"][0]).active = False
        db.commit()
    assert k["browser"].get(ROOT+f"/captures/{identity}").status_code == 401


def test_missing_face_store_blocks_new_identity_instead_of_silently_reenrolling(partner_kiosk):
    k = partner_kiosk
    _, state = k["capture"]()
    with k["factory"]() as db:
        worker = db.get(PartnerWorker, state["worker"]["id"])
        service.store_for().remove(worker.face_reference)
    identity, state = k["start"](index=1)
    k["clock"][0] += timedelta(seconds=.5)
    failed = k["browser"].post(ROOT+f"/captures/{identity}/frames/1", content=b"B:store-missing",
        headers={"Content-Type": "image/jpeg", "X-Kiosk-Intent": "capture-partner-face", "X-Capture-Nonce": state["capture_nonce"]})
    assert failed.status_code == 503
    with k["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(PartnerWorker)) == 1


@pytest.mark.skipif(not os.environ.get("CHAMCONG_TEST_DATABASE_URL"), reason="Requires SQL Server row locks")
@pytest.mark.parametrize("same_face", [False, True])
def test_native_concurrent_final_frames_never_overallocate_or_duplicate_the_person(partner_kiosk, same_face):
    k = partner_kiosk
    with k["factory"]() as db:
        db.get(PartnerBatch, k["batch_id"]).capacity = 1
        db.commit()
    requests = []
    for index in range(2):
        identity, state = k["start"](index)
        for number in (1, 2):
            state = k["frame"](identity, state, "A" if same_face or index == 0 else "B", number)
        requests.append(identity)
    k["clock"][0] += timedelta(seconds=1)
    barrier = Barrier(2)

    def final(index):
        vector = np.zeros(128, dtype=np.float32)
        vector[0 if same_face or index == 0 else 1] = 1
        token_hash = hashlib.sha256(k["tokens"][index].encode()).hexdigest()
        barrier.wait(timeout=15)
        with k["factory"]() as db:
            return service.append_frame(db, requests[index], k["ids"][index], token_hash,
                SyntheticEngine.model_id, 128, 3, hashlib.sha256(f"final:{index}".encode()).hexdigest(),
                vector, QUALITY, k["clock"][0])

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(final, range(2)))
    with k["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(PartnerWorker)) == 1
        assert db.get(PartnerBatch, k["batch_id"]).next_number == 1
    if same_face:
        assert results[0]["worker"]["code"] == results[1]["worker"]["code"]
    else:
        assert sorted(result["state"] for result in results) == ["rejected", "verified"]
