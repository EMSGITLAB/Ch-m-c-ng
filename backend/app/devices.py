import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select

from .auth import Admin, Db, LoginLimiter, MutationAdmin, same_origin
from .config import get_settings
from .employees import EmployeeInput
from .models import AuditLog, Device, DevicePairing

admin_router=APIRouter(prefix="/api/admin/devices",tags=["devices"])
kiosk_router=APIRouter(prefix="/api/kiosk",tags=["kiosk"])
KIOSK_COOKIE="chamcong_kiosk"
pair_limiter=LoginLimiter()


def aware(value):
    return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value


class DeviceInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    name:str=Field(min_length=2,max_length=100)
    direction:Literal["in","out"]="in"

    @field_validator("name",mode="before")
    @classmethod
    def clean_name(cls,value):
        return EmployeeInput.clean_text(value)


class PairingInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    code:str=Field(pattern=r"^[0-9]{8}$")


def pairing_hash(code):
    secret=get_settings().session_secret
    if len(secret)<32:
        raise HTTPException(503,"Chưa cấu hình khóa ghép thiết bị.")
    return hmac.new(secret.encode(),("kiosk-pair:"+code).encode(),hashlib.sha256).hexdigest()


def describe(device):
    expiry=aware(device.token_expires_at)
    return {"id":device.id,"name":device.name,"direction":device.direction,"active":device.active,
            "paired":bool(device.active and device.token_hash and expiry and expiry>datetime.now(UTC)),
            "last_seen_at":device.last_seen_at.isoformat() if device.last_seen_at else None,
            "token_expires_at":expiry.isoformat() if expiry else None}


def issue_pairing(device,db):
    now=datetime.now(UTC)
    db.execute(delete(DevicePairing).where((DevicePairing.device_id==device.id)|(DevicePairing.expires_at<=now)))
    for _ in range(10):
        code=f"{secrets.randbelow(100_000_000):08d}"
        digest=pairing_hash(code)
        if db.get(DevicePairing,digest) is None:
            break
    else:
        raise HTTPException(503,"Chưa tạo được mã ghép. Vui lòng thử lại.")
    expiry=now+timedelta(minutes=5)
    db.add(DevicePairing(code_hash=digest,device_id=device.id,expires_at=expiry))
    device.token_hash=None
    device.token_expires_at=None
    return {"device":describe(device),"pairing_code":code,"expires_at":expiry.isoformat()}


@admin_router.get("")
def devices(db:Db,user:Admin):
    return {"items":[describe(device) for device in db.scalars(select(Device).order_by(Device.name)).all()]}


@admin_router.post("",status_code=201)
def create_device(payload:DeviceInput,db:Db,user:MutationAdmin):
    device=Device(name=payload.name,direction=payload.direction,active=True)
    db.add(device)
    db.flush()
    result=issue_pairing(device,db)
    db.add(AuditLog(action="device_create",entity_id=device.id,details={"name":device.name,"direction":device.direction}))
    db.commit()
    return result


@admin_router.post("/{device_id}/pairing")
def renew_pairing(device_id:str,db:Db,user:MutationAdmin):
    device=db.get(Device,device_id)
    if not device or not device.active:
        raise HTTPException(404,"Không có thiết bị đang hoạt động.")
    result=issue_pairing(device,db)
    db.add(AuditLog(action="device_repair",entity_id=device.id,details={}))
    db.commit()
    return result


@admin_router.post("/{device_id}/revoke")
def revoke(device_id:str,db:Db,user:MutationAdmin):
    device=db.get(Device,device_id)
    if not device:
        raise HTTPException(404,"Không tìm thấy thiết bị.")
    device.active=False
    device.token_hash=None
    device.token_expires_at=None
    db.execute(delete(DevicePairing).where(DevicePairing.device_id==device.id))
    db.add(AuditLog(action="device_revoke",entity_id=device.id,details={}))
    db.commit()
    return describe(device)


@kiosk_router.post("/pair")
def pair(payload:PairingInput,request:Request,response:Response,db:Db):
    same_origin(request)
    if request.headers.get("x-kiosk-intent")!="pair-local-kiosk":
        raise HTTPException(403,"Thiếu yêu cầu ghép thiết bị.")
    key=request.client.host if request.client else "local"
    pair_limiter.check(key)
    digest=pairing_hash(payload.code)
    record=db.get(DevicePairing,digest)
    now=datetime.now(UTC)
    device=db.get(Device,record.device_id) if record else None
    if not record or aware(record.expires_at)<=now or not device or not device.active:
        pair_limiter.failed(key)
        raise HTTPException(401,"Mã ghép sai, hết hạn hoặc đã dùng.")
    consumed=db.execute(delete(DevicePairing).where(DevicePairing.code_hash==digest,DevicePairing.expires_at>now).execution_options(synchronize_session=False))
    if consumed.rowcount!=1:
        db.rollback()
        pair_limiter.failed(key)
        raise HTTPException(401,"Mã ghép đã dùng hoặc hết hạn.")
    token=secrets.token_urlsafe(32)
    device.token_hash=hashlib.sha256(token.encode()).hexdigest()
    device.token_expires_at=now+timedelta(days=30)
    device.last_seen_at=now
    db.add(AuditLog(action="device_paired",entity_id=device.id,details={}))
    db.commit()
    pair_limiter.clear(key)
    response.set_cookie(KIOSK_COOKIE,token,httponly=True,secure=get_settings().environment=="production",samesite="strict",max_age=30*86400,path="/")
    return describe(device)


def current_device(request:Request,db:Db) -> Device:
    token=request.cookies.get(KIOSK_COOKIE,"")
    if not token or len(token)>100:
        raise HTTPException(401,"Thiết bị chưa được ghép quyền.")
    device=db.scalar(select(Device).where(Device.token_hash==hashlib.sha256(token.encode()).hexdigest()))
    now=datetime.now(UTC)
    if not device or not device.active or not device.token_expires_at or aware(device.token_expires_at)<=now:
        raise HTTPException(401,"Quyền thiết bị hết hạn hoặc đã thu hồi.")
    if not device.last_seen_at or (now-aware(device.last_seen_at)).total_seconds()>60:
        device.last_seen_at=now
        db.commit()
    return device


Kiosk=Annotated[Device,Depends(current_device)]


@kiosk_router.get("/device")
def kiosk_status(device:Kiosk):
    return describe(device)
