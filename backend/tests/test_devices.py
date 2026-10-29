from datetime import UTC, datetime, timedelta

from app.devices import KIOSK_COOKIE, pair_limiter
from app.models import Device, DevicePairing
from sqlalchemy import select
from test_admin import setup


def create(browser,csrf):
    response=browser.post("/api/admin/devices",json={"name":"Camera thử","direction":"in"},headers={"X-CSRF-Token":csrf})
    assert response.status_code==201,response.text
    return response.json()


def pair(browser,code):
    return browser.post("/api/kiosk/pair",json={"code":code},headers={"X-Kiosk-Intent":"pair-local-kiosk"})


def test_pair_once_and_kiosk_has_no_admin_privileges(client):
    browser,factory=client
    csrf=setup(browser)
    created=create(browser,csrf)
    with factory() as db:
        record=db.scalar(select(DevicePairing))
        assert record.code_hash!=created["pairing_code"]
    browser.cookies.clear()
    assert pair(browser,created["pairing_code"]).status_code==200
    assert browser.get("/api/kiosk/device").json()["name"]=="Camera thử"
    assert pair(browser,created["pairing_code"]).status_code==401
    assert browser.get("/api/admin/employees").status_code==401
    assert browser.get("/api/admin/devices").status_code==401
    assert browser.get("/api/auth/session").status_code==401
    with factory() as db:
        device=db.get(Device,created["device"]["id"])
        assert device.token_hash!=browser.cookies[KIOSK_COOKIE]


def test_revoke_immediately_removes_kiosk_access(client):
    browser,_=client
    csrf=setup(browser)
    created=create(browser,csrf)
    assert pair(browser,created["pairing_code"]).status_code==200
    assert browser.post(f"/api/admin/devices/{created['device']['id']}/revoke",headers={"X-CSRF-Token":csrf}).status_code==200
    assert browser.get("/api/kiosk/device").status_code==401
    assert "token_hash" not in browser.get("/api/admin/devices").text


def test_renew_pairing_invalidates_old_session_and_old_code(client):
    browser,_=client
    csrf=setup(browser)
    created=create(browser,csrf)
    assert pair(browser,created["pairing_code"]).status_code==200
    renewed=browser.post(f"/api/admin/devices/{created['device']['id']}/pairing",headers={"X-CSRF-Token":csrf}).json()
    assert browser.get("/api/kiosk/device").status_code==401
    assert pair(browser,created["pairing_code"]).status_code==401
    assert pair(browser,renewed["pairing_code"]).status_code==200


def test_expired_pairing_and_token_are_rejected(client):
    browser,factory=client
    csrf=setup(browser)
    created=create(browser,csrf)
    with factory() as db:
        record=db.scalar(select(DevicePairing))
        record.expires_at=datetime.now(UTC)-timedelta(seconds=1)
        db.commit()
    assert pair(browser,created["pairing_code"]).status_code==401
    renewed=browser.post(f"/api/admin/devices/{created['device']['id']}/pairing",headers={"X-CSRF-Token":csrf}).json()
    assert pair(browser,renewed["pairing_code"]).status_code==200
    with factory() as db:
        device=db.get(Device,created["device"]["id"])
        device.token_expires_at=datetime.now(UTC)-timedelta(seconds=1)
        db.commit()
    assert browser.get("/api/kiosk/device").status_code==401


def test_pairing_is_rate_limited_and_requires_explicit_intent(client):
    browser,_=client
    pair_limiter.items.clear()
    assert browser.post("/api/kiosk/pair",json={"code":"12345678"}).status_code==403
    for _ in range(5):
        assert pair(browser,"12345678").status_code==401
    assert pair(browser,"12345678").status_code==429
    pair_limiter.items.clear()
