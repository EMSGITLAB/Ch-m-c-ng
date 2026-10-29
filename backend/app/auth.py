import hashlib
import hmac
import secrets
import threading
import time
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_session
from .models import AdminUser, AuditLog, AuthSession

router=APIRouter(prefix="/api/auth",tags=["auth"])
Db=Annotated[Session,Depends(get_session)]
COOKIE="chamcong_session"
hasher=PasswordHasher()
dummy_hash=hasher.hash(secrets.token_urlsafe(20))


class Credentials(BaseModel):
    username: str=Field(min_length=1,max_length=80)
    password: str=Field(min_length=1,max_length=256)


class SetupCredentials(Credentials):
    password: str=Field(min_length=12,max_length=256)


class LoginLimiter:
    def __init__(self):
        self.items=OrderedDict()
        self.lock=threading.Lock()

    def check(self,key):
        now=time.monotonic()
        with self.lock:
            attempts=[t for t in self.items.get(key,[]) if now-t<300]
            self.items[key]=attempts
            self.items.move_to_end(key)
            while len(self.items)>1024:
                self.items.popitem(last=False)
            if len(attempts)>=5:
                raise HTTPException(429,"Thử đăng nhập quá nhiều. Vui lòng chờ 5 phút.")

    def failed(self,key):
        with self.lock:
            self.items.setdefault(key,[]).append(time.monotonic())

    def clear(self,key):
        with self.lock:
            self.items.pop(key,None)


limiter=LoginLimiter()


def same_origin(request: Request):
    origin=request.headers.get("origin")
    if origin and origin not in get_settings().allowed_origins:
        raise HTTPException(403,"Nguồn yêu cầu không được phép.")


def csrf_value(token: str) -> str:
    secret=get_settings().session_secret
    if len(secret)<32:
        raise HTTPException(503,"Chưa cấu hình khóa phiên an toàn.")
    return hmac.new(secret.encode(),token.encode(),hashlib.sha256).hexdigest()


def create_session(db:Session,user:AdminUser,response:Response):
    now=datetime.now(UTC)
    token=secrets.token_urlsafe(32)
    csrf=csrf_value(token)
    db.execute(delete(AuthSession).where(AuthSession.expires_at<now))
    db.add(AuthSession(token_hash=hashlib.sha256(token.encode()).hexdigest(),user_id=user.id,
                       expires_at=now+timedelta(hours=get_settings().session_hours)))
    db.commit()
    response.set_cookie(COOKIE,token,httponly=True,secure=get_settings().environment=="production",
                        samesite="strict",max_age=get_settings().session_hours*3600,path="/")
    return {"username":user.username,"csrf_token":csrf}


def current_admin(request:Request,db:Db) -> AdminUser:
    token=request.cookies.get(COOKIE,"")
    if not token or len(token)>100:
        raise HTTPException(401,"Cần đăng nhập quản trị.")
    record=db.get(AuthSession,hashlib.sha256(token.encode()).hexdigest())
    expires=record.expires_at if record else None
    if expires and expires.tzinfo is None:
        expires=expires.replace(tzinfo=UTC)
    if not record or expires<=datetime.now(UTC):
        raise HTTPException(401,"Phiên đã hết hạn hoặc bị thu hồi.")
    user=db.get(AdminUser,record.user_id)
    if not user:
        raise HTTPException(401,"Tài khoản không còn hoạt động.")
    return user


Admin=Annotated[AdminUser,Depends(current_admin)]


def require_csrf(request:Request,user:Admin):
    same_origin(request)
    expected=csrf_value(request.cookies.get(COOKIE,""))
    if not hmac.compare_digest(request.headers.get("x-csrf-token",""),expected):
        raise HTTPException(403,"Phiên thao tác không hợp lệ. Vui lòng tải lại trang.")
    return user


MutationAdmin=Annotated[AdminUser,Depends(require_csrf)]


@router.get("/setup")
def setup_status(db:Db):
    return {"requires_setup":db.get(AdminUser,1) is None,"local_setup_allowed":get_settings().environment=="development"}


@router.post("/setup",status_code=201)
def setup(payload:SetupCredentials,request:Request,response:Response,db:Db):
    same_origin(request)
    if get_settings().environment!="development" or not request.client or request.client.host not in {"127.0.0.1","::1","testclient"}:
        raise HTTPException(403,"Thiết lập lần đầu chỉ được phép trên máy phát triển local.")
    if request.headers.get("x-setup-intent")!="create-local-admin":
        raise HTTPException(403,"Thiếu yêu cầu thiết lập quản trị.")
    if db.get(AdminUser,1):
        raise HTTPException(409,"Quản trị đã được thiết lập.")
    username=payload.username.strip()
    if not username:
        raise HTTPException(422,"Tên đăng nhập không được trống.")
    user=AdminUser(id=1,username=username,password_hash=hasher.hash(payload.password))
    db.add(user)
    db.add(AuditLog(action="admin_setup",entity_id="1",details={"username":username}))
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409,"Quản trị đã được thiết lập.") from error
    return create_session(db,user,response)


@router.post("/login")
def login(payload:Credentials,request:Request,response:Response,db:Db):
    same_origin(request)
    if request.headers.get("x-login-intent")!="login-local-admin":
        raise HTTPException(403,"Thiếu yêu cầu đăng nhập.")
    key=request.client.host if request.client else "local"
    limiter.check(key)
    user=db.get(AdminUser,1)
    valid=False
    try:
        verified=hasher.verify(user.password_hash if user else dummy_hash,payload.password)
        valid=bool(verified and user and hmac.compare_digest(user.username.encode(),payload.username.strip().encode()))
    except VerificationError:
        pass
    if not valid:
        limiter.failed(key)
        raise HTTPException(401,"Tên đăng nhập hoặc mật khẩu không đúng.")
    limiter.clear(key)
    db.add(AuditLog(action="admin_login",entity_id="1",details={}))
    return create_session(db,user,response)


@router.get("/session")
def session_info(request:Request,user:Admin):
    return {"username":user.username,"csrf_token":csrf_value(request.cookies[COOKIE])}


@router.post("/logout")
def logout(request:Request,response:Response,db:Db,user:MutationAdmin):
    record=db.get(AuthSession,hashlib.sha256(request.cookies[COOKIE].encode()).hexdigest())
    if record:
        db.delete(record)
    db.commit()
    response.delete_cookie(COOKIE,path="/")
    return {"logged_out":True}
