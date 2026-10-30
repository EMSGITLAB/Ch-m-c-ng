"""Isolated business-rule checks; no real biometric accuracy/PAD claims."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.main import app
from app.matching import SCORING_RULE
from app.models import AuditLog, Device, Employee, PartnerBatch, RecognitionPolicy
from sqlalchemy import func, select
from test_admin import setup

ROOT = "/api/admin/partners"


def test_requested_count_breaks_and_capacity_are_independent(partner_setup):
    browser, _, headers, _, create, _, _=partner_setup
    response,_=create(start="08:00",end="17:00",requested_count=8,capacity=10,
        breaks=[{"start":"12:00","end":"13:00","paid":False}])
    assert response.status_code==201,response.text
    batch=response.json()
    assert batch['requested_count']==8 and batch['capacity']==10
    assert batch['rules']['breaks']==[{"start_offset":240,"end_offset":300,"paid":False}]
    changed=browser.post(ROOT+f"/batches/{batch['id']}/capacity",headers=headers,
        json={"expected_capacity":10,"capacity":12,"reason":"Điều chỉnh hạn mức ca thử"})
    assert changed.status_code==200 and changed.json()['requested_count']==8


@pytest.fixture
def partner_setup(client, monkeypatch):
    browser, factory = client
    headers = {"X-CSRF-Token": setup(browser)}
    response = browser.post(ROOT, json={"code": " dt01 ", "name": "Đối tác thử nghiệm"}, headers=headers)
    assert response.status_code == 201, response.text
    vendor = response.json()

    def create(**changes):
        payload = {"request_id": str(uuid4()), "partner_id": vendor["id"], "work_date": "2026-10-30",
                   "name": "Ca thời vụ", "site": "Sàn thử", "start": "22:00", "end": "06:00", "capacity": 30}
        payload.update(changes)
        return browser.post(ROOT+"/batches", json=payload, headers=headers), payload

    def activate_policy():
        with factory() as db:
            policy = RecognitionPolicy(id="partner-test-"+uuid4().hex, model_id="test-only-model",
                scoring_rule=SCORING_RULE, threshold=.61, minimum_margin=.07, enabled=True,
                mode="supervised", pad_verified=False, validated_at=datetime.now(UTC)-timedelta(minutes=1),
                evidence={"sequence_protocol": "stable-three-v1", "test_only": True})
            db.add(policy)
            db.commit()
            identity = policy.id
        monkeypatch.setattr(app.state, "attendance_policy_id", identity)
        monkeypatch.setattr(app.state, "face_engine", SimpleNamespace(model_id="test-only-model"))
        return identity

    def transition(identity, old, new):
        return browser.post(ROOT+f"/batches/{identity}/state", json={
            "expected_state": old, "state": new, "reason": "Kiểm tra luồng cô lập"}, headers=headers)

    return browser, factory, headers, vendor, create, activate_policy, transition


def test_partner_mutations_require_admin_session_csrf_and_no_client_thresholds(client):
    browser, _ = client
    assert browser.get(ROOT).status_code == 401
    assert browser.post(ROOT, json={"code": "DT01", "name": "Đối tác thử"}).status_code == 401
    headers = {"X-CSRF-Token": setup(browser)}
    assert browser.post(ROOT, json={"code": "DT01", "name": "Đối tác thử"}).status_code == 403
    assert browser.post(ROOT, json={"code": "DT01", "name": "Đối tác thử", "threshold": .1}, headers=headers).status_code == 422


def test_vendor_code_is_normalized_unique_and_never_creates_an_employee(partner_setup):
    browser, factory, headers, vendor, *_ = partner_setup
    assert vendor["code"] == "DT01"
    assert browser.post(ROOT, json={"code": "dt01", "name": "Đối tác khác"}, headers=headers).status_code == 409
    assert browser.get(ROOT).json()["items"] == [vendor]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Employee)) == 0


def test_batch_overnight_windows_retention_and_idempotent_retry(partner_setup):
    browser, factory, headers, vendor, create, *_ = partner_setup
    result, payload = create()
    assert result.status_code == 201, result.text
    row = result.json()
    assert row["starts_at"] == "2026-10-30T15:00:00+00:00"
    assert row["ends_at"] == "2026-10-30T23:00:00+00:00"
    assert row["work_date"] == "2026-10-30" and row["retention_hours"] == 48
    assert row["admission_mode"] == "automatic" and row["state"] == "draft"
    assert browser.post(ROOT+"/batches", json=payload, headers=headers).json() == row
    assert browser.post(ROOT+"/batches", json=payload | {"capacity": 31}, headers=headers).status_code == 409
    query = {"date_from": "2026-10-30", "date_to": "2026-10-30", "partner_id": vendor["id"]}
    assert browser.get(ROOT+"/batches/list", params=query).json()["items"] == [row]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(PartnerBatch)) == 1
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "partner_batch_create")) == 1


@pytest.mark.parametrize("changes", [{"start": "22:00", "end": "22:00"}, {"capacity": 0},
    {"capacity": 5001}, {"retention_hours": 1000}, {"threshold": .1}, {"site": "Sàn\u0000thử"}])
def test_invalid_or_client_owned_recognition_configuration_is_rejected(partner_setup, changes):
    *_, create, _, _ = partner_setup
    response, _ = create(**changes)
    assert response.status_code == 422


def test_batch_open_requires_server_policy_and_snapshots_it_once(partner_setup):
    browser, factory, headers, vendor, create, activate, transition = partner_setup
    result, _ = create()
    identity = result.json()["id"]
    assert transition(identity, "draft", "open").status_code == 503
    policy = activate()
    opened = transition(identity, "draft", "open")
    assert opened.status_code == 200, opened.text
    assert opened.json()["threshold"] == .61 and opened.json()["minimum_margin"] == .07
    assert opened.json()["policy_id"] == policy
    assert not opened.json()["pad_validated"]
    assert transition(identity, "draft", "open").json() == opened.json()
    assert browser.patch(ROOT+"/"+vendor["id"], json={"name": vendor["name"], "active": False}, headers=headers).status_code == 409
    assert transition(identity, "draft", "review").status_code == 409
    assert transition(identity, "open", "running").status_code == 200
    assert transition(identity, "running", "review").status_code == 200
    assert transition(identity, "review", "closed").status_code == 409
    report = browser.get(ROOT+f"/batches/{identity}/report").json()
    assert browser.post(ROOT+f"/batches/{identity}/close", json={"request_id":str(uuid4()),
        "expected_source":report["source_hash"],"reason":"Đã kiểm tra bản đối soát"}, headers=headers).status_code == 200
    assert transition(identity, "closed", "open").status_code == 409
    with factory() as db:
        row = db.get(PartnerBatch, identity)
        assert row.threshold == .61 and row.minimum_margin == .07


def test_capacity_changes_are_audited_optimistic_and_cannot_shrink_an_open_batch(partner_setup):
    browser, _, headers, _, create, activate, transition = partner_setup
    identity = create()[0].json()["id"]
    activate()
    assert transition(identity, "draft", "open").status_code == 200
    endpoint = ROOT+f"/batches/{identity}/capacity"
    payload = {"expected_capacity": 30, "capacity": 40, "reason": "Tăng số người được phép"}
    assert browser.post(endpoint, json=payload, headers=headers).json()["capacity"] == 40
    assert browser.post(endpoint, json=payload, headers=headers).status_code == 409
    assert browser.post(endpoint, json=payload | {"expected_capacity": 40, "capacity": 20}, headers=headers).status_code == 409


def test_device_binding_is_admin_only_and_scoped_to_one_batch(partner_setup):
    browser, factory, headers, _, create, *_ = partner_setup
    first = create()[0].json()["id"]
    second = create()[0].json()["id"]
    with factory() as db:
        device = Device(name="Thiết bị thử riêng")
        db.add(device)
        db.commit()
        device_id = device.id
    endpoint = ROOT+"/devices/"+device_id
    body = {"batch_id": first, "reason": "Gán điểm quét thử nghiệm"}
    assert browser.put(endpoint, json=body).status_code == 403
    assert browser.put(endpoint, json=body, headers=headers).json()["batch_id"] == first
    assert browser.put(endpoint, json=body | {"batch_id": second}, headers=headers).json()["batch_id"] == second
    rows = browser.get(ROOT+"/devices/list").json()["items"]
    assert rows == [{"device_id": device_id, "batch_id": second, "active": True}]
    assert browser.post(endpoint+"/unbind", json={"reason": body["reason"]}, headers=headers).json()["active"] is False


def test_batch_list_has_bounded_date_ranges(partner_setup):
    browser, *_ = partner_setup
    assert browser.get(ROOT+"/batches/list", params={"date_from": "2026-10-30", "date_to": "2026-10-29"}).status_code == 422
    assert browser.get(ROOT+"/batches/list", params={"date_from": "2026-01-01", "date_to": "2026-12-31"}).status_code == 422
