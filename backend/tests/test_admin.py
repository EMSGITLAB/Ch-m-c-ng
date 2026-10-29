from datetime import UTC, datetime, timedelta

from app.auth import COOKIE
from app.config import get_settings
from app.models import AdminUser, AuditLog, AuthSession
from sqlalchemy import select


def setup(browser):
    response=browser.post("/api/auth/setup",json={"username":"admin","password":"testing-password-123!"},headers={"X-Setup-Intent":"create-local-admin"})
    assert response.status_code==201,response.text
    return response.json()["csrf_token"]


def test_setup_cannot_be_repeated_and_hashes_password(client):
    browser,factory=client
    assert browser.get("/api/auth/setup").json()["requires_setup"]
    csrf=setup(browser)
    assert csrf
    with factory() as db:
        user=db.get(AdminUser,1)
        assert user.password_hash.startswith("$argon2id$")
        assert "testing-password" not in user.password_hash
        session=db.scalar(select(AuthSession))
        assert session.token_hash!=browser.cookies[COOKIE]
    again=browser.post("/api/auth/setup",json={"username":"other","password":"another-password-123"},headers={"X-Setup-Intent":"create-local-admin"})
    assert again.status_code==409


def test_employee_access_requires_session_and_csrf(client):
    browser,_=client
    assert browser.get("/api/admin/employees").status_code==401
    csrf=setup(browser)
    body={"code":"nv01","name":"Nguyễn Văn An","department":"Kỹ thuật"}
    assert browser.post("/api/admin/employees",json=body).status_code==403
    response=browser.post("/api/admin/employees",json=body,headers={"X-CSRF-Token":csrf})
    assert response.status_code==201
    assert response.json()["code"]=="NV01"
    assert "vector" not in response.text
    assert browser.post("/api/admin/employees",json=body,headers={"X-CSRF-Token":csrf}).status_code==409


def test_search_edit_deactivate_and_audit(client):
    browser,factory=client
    csrf=setup(browser)
    headers={"X-CSRF-Token":csrf}
    employee=browser.post("/api/admin/employees",json={"code":"NV01","name":"Nguyễn Văn An","department":"Kỹ thuật"},headers=headers).json()
    assert browser.get("/api/admin/employees",params={"q":"Nguyễn"}).json()["total"]==1
    assert browser.get("/api/admin/employees",params={"q":"%"}).json()["total"]==0
    result=browser.patch("/api/admin/employees/"+employee["id"],json={"active":False,"department":"Văn phòng"},headers=headers)
    assert result.status_code==200
    assert not result.json()["active"]
    assert browser.get("/api/admin/employees",params={"active":True}).json()["total"]==0
    with factory() as db:
        audit=db.scalar(select(AuditLog).where(AuditLog.action=="employee_update"))
        assert audit.details["before"]["active"] is True
        assert audit.details["after"]["department"]=="Văn phòng"


def test_import_is_atomic_and_supports_bom_unicode(client):
    browser,_=client
    csrf=setup(browser)
    headers={"X-CSRF-Token":csrf,"Content-Type":"text/csv"}
    invalid="code,name\nNV01,Nguyễn Văn An\nNV01,Lê Bình\n"
    assert browser.post("/api/admin/employees/import-csv",content=invalid.encode(),headers=headers).status_code==422
    assert browser.get("/api/admin/employees").json()["total"]==0
    valid="\ufeffcode,name,department\nNV01,Nguyễn Văn An,Kỹ thuật\nNV02,Lê Bình,Văn phòng\n"
    assert browser.post("/api/admin/employees/import-csv",content=valid.encode(),headers=headers).json()["imported"]==2
    duplicate="code,name\nNV03,Hồ Minh\nNV01,Nguyễn Văn An\n"
    assert browser.post("/api/admin/employees/import-csv",content=duplicate.encode(),headers=headers).status_code==409
    assert browser.get("/api/admin/employees").json()["total"]==2


def test_revoke_and_expire_sessions(client):
    browser,factory=client
    csrf=setup(browser)
    token=browser.cookies[COOKIE]
    assert browser.post("/api/auth/logout",headers={"X-CSRF-Token":csrf}).status_code==200
    browser.cookies.set(COOKIE,token)
    assert browser.get("/api/auth/session").status_code==401
    login=browser.post("/api/auth/login",json={"username":"admin","password":"testing-password-123!"},headers={"X-Login-Intent":"login-local-admin"})
    assert login.status_code==200
    with factory() as db:
        for record in db.scalars(select(AuthSession)):
            record.expires_at=datetime.now(UTC)-timedelta(seconds=1)
        db.commit()
    assert browser.get("/api/auth/session").status_code==401


def test_reject_wrong_origin_and_throttle_login(client):
    browser,_=client
    setup(browser)
    body={"username":"admin","password":"wrong-password"}
    assert browser.post("/api/auth/login",json=body,headers={"Origin":"https://other.invalid","X-Login-Intent":"login-local-admin"}).status_code==403
    for _ in range(5):
        assert browser.post("/api/auth/login",json=body,headers={"X-Login-Intent":"login-local-admin"}).status_code==401
    assert browser.post("/api/auth/login",json=body,headers={"X-Login-Intent":"login-local-admin"}).status_code==429


def test_no_unknown_fields_and_no_control_characters(client):
    browser,_=client
    csrf=setup(browser)
    assert browser.post("/api/admin/employees",json={"code":"NV01","name":"A\u0000B"},headers={"X-CSRF-Token":csrf}).status_code==422
    assert browser.post("/api/admin/employees",json={"code":"NV01","name":"Nhân viên","role":"admin"},headers={"X-CSRF-Token":csrf}).status_code==422


def test_setup_is_local_only_and_sessions_have_cookie_protection(client):
    browser,_=client
    body={"username":"admin","password":"testing-password-123!"}
    assert browser.post("/api/auth/setup",json=body).status_code==403
    settings=get_settings()
    original=settings.environment
    settings.environment="production"
    try:
        assert browser.post("/api/auth/setup",json=body,headers={"X-Setup-Intent":"create-local-admin"}).status_code==403
    finally:
        settings.environment=original
    response=browser.post("/api/auth/setup",json=body,headers={"X-Setup-Intent":"create-local-admin"})
    assert response.status_code==201
    cookie=response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert browser.get("/api/auth/session",headers={"Host":"untrusted.invalid"}).status_code==400
