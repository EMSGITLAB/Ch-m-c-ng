import asyncio
import hashlib
import threading
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from .auth import Admin, Db, MutationAdmin
from .auto_capture import check_frame, tracker
from .biometric_state import lock_employee
from .capture_guidance import PROTOCOL, QUALITY_FEEDBACK, check_pose, instruction
from .config import get_settings
from .devices import aware
from .face_engine import FaceInputError
from .models import AuditLog, CollectionSample, Employee, FaceCollection

router=APIRouter(prefix="/api/admin",tags=["face-collection"])
slots=threading.BoundedSemaphore(2)


class CollectionInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    purpose:Literal["enrollment","calibration","evaluation"]="enrollment"


def describe(collection):
    return {"id":collection.id,"employee_id":collection.employee_id,"purpose":collection.purpose,"model_id":collection.model_id,
            "status":collection.status,"sample_count":collection.sample_count,"minimum_samples":1 if collection.guidance_protocol in {"imported-photo-v1", "profile-photo-v1"} else 5,"maximum_samples":10,
            "expires_at":collection.expires_at.isoformat(),"created_at":collection.created_at.isoformat(),
            "guidance_protocol":collection.guidance_protocol,"biometric_revision":collection.biometric_revision,
            "next_instruction":instruction(collection.sample_count) if collection.status=="open" and collection.guidance_protocol==PROTOCOL else None,
            "operational_enrollment":False}


def employee_or_404(db,employee_id):
    employee=db.get(Employee,employee_id)
    if not employee or not employee.active:
        raise HTTPException(404,"Không có hồ sơ nhân viên đang hoạt động.")
    return employee


@router.get("/employees/{employee_id}/collections")
def list_collections(employee_id:str,db:Db,user:Admin):
    if not db.get(Employee,employee_id):
        raise HTTPException(404,"Không có hồ sơ nhân viên.")
    rows=db.scalars(select(FaceCollection).where(FaceCollection.employee_id==employee_id).order_by(FaceCollection.created_at.desc())).all()
    return {"items":[describe(row) for row in rows]}


@router.post("/employees/{employee_id}/collections",status_code=201)
def create_collection(employee_id:str,payload:CollectionInput,request:Request,db:Db,user:MutationAdmin):
    employee_or_404(db,employee_id)
    engine=getattr(request.app.state,"face_engine",None)
    if not engine:
        raise HTTPException(503,"Model local chưa sẵn sàng.")
    revision=lock_employee(db,employee_id,active_only=True)
    row=FaceCollection(employee_id=employee_id,model_id=engine.model_id,purpose=payload.purpose,guidance_protocol=PROTOCOL,
                       biometric_revision=revision,
                       status="open",sample_count=0,expires_at=datetime.now(UTC)+timedelta(minutes=10))
    db.add(row)
    db.flush()
    db.add(AuditLog(action="face_collection_create",entity_id=row.id,details={"purpose":row.purpose,"employee_id":employee_id}))
    db.commit()
    return describe(row)


@router.post("/collections/{collection_id}/samples",status_code=201)
async def capture_sample(collection_id:str,request:Request,db:Db,user:MutationAdmin):
    if not slots.acquire(blocking=False):
        raise HTTPException(429,"Đang xử lý ảnh. Vui lòng chờ rồi thử lại.")
    try:
        return await process_sample(collection_id,request,db)
    finally:
        slots.release()


def open_collection(collection_id,request,db):
    row=db.get(FaceCollection,collection_id)
    if not row:
        raise HTTPException(404,"Không có phiên thu mẫu.")
    if row.status!="open" or aware(row.expires_at)<=datetime.now(UTC) or row.sample_count>=10:
        raise HTTPException(409,"Phiên đã kết thúc, hết hạn hoặc đã đủ 10 mẫu.")
    if row.guidance_protocol!=PROTOCOL:
        raise HTTPException(409,"Phiên cũ chưa có hướng dẫn tư thế. Hãy tạo phiên chụp mới.")
    employee=employee_or_404(db,row.employee_id)
    if employee.biometric_revision!=row.biometric_revision:
        raise HTTPException(409,"Bộ mẫu thuộc phiên dữ liệu cũ. Hãy tạo bộ mới sau khi xóa mẫu.")
    engine=getattr(request.app.state,"face_engine",None)
    if not engine or engine.model_id!=row.model_id:
        raise HTTPException(409,"Model đã thay đổi. Hãy tạo phiên thu mẫu mới.")
    return row,engine


async def read_photo(request):
    content=bytearray()
    try:
        async with asyncio.timeout(10):
            async for chunk in request.stream():
                content.extend(chunk)
                if len(content)>get_settings().max_upload_bytes:
                    raise HTTPException(413,"Ảnh vượt dung lượng cho phép.")
    except TimeoutError as error:
        raise HTTPException(408,"Truyền ảnh quá lâu.") from error
    return bytes(content)


def signature(row):
    return row.id,row.sample_count,row.biometric_revision,row.model_id


@router.post("/collections/{collection_id}/preview")
async def preview_sample(collection_id:str,request:Request,db:Db,user:MutationAdmin):
    if not slots.acquire(blocking=False):
        raise HTTPException(429,"Đang xử lý ảnh. Vui lòng chờ một chút.")
    try:
        row,engine=open_collection(collection_id,request,db)
        content=await read_photo(request)
        try:
            _,_,metadata=await run_in_threadpool(engine.inspect,content,get_settings().max_upload_bytes)
        except FaceInputError as error:
            tracker.discard(collection_id)
            return {"ready":False,"aligned":False,"stable_frames":0,"required_frames":3,
                    "feedback":QUALITY_FEEDBACK.get(error.code,"Chưa đọc được ảnh camera. Hãy thử lại."),"reason":error.code,"collection":describe(row)}
        aligned,feedback=check_frame(metadata["quality"])
        anchor=db.scalar(select(CollectionSample).where(CollectionSample.collection_id==collection_id,CollectionSample.position==1))
        accepted,pose_feedback=check_pose(row.sample_count,metadata["quality"],anchor.quality if anchor else None)
        if not aligned or not accepted:
            tracker.discard(collection_id)
            return {"ready":False,"aligned":aligned,"stable_frames":0,"required_frames":3,
                    "feedback":feedback if not aligned else pose_feedback,"reason":"outside_frame" if not aligned else "wrong_pose","collection":describe(row)}
        state=tracker.observe(signature(row),metadata["quality"],hashlib.sha256(content).hexdigest())
        return state | {"aligned":True,"feedback":"Đã ổn định, đang chụp…" if state["ready"] else "Đúng tư thế. Giữ yên khoảng một giây để tự chụp.",
                        "image_saved":False,"vector_saved":False,"collection":describe(row)}
    finally:
        slots.release()


async def process_sample(collection_id,request,db):
    row,engine=open_collection(collection_id,request,db)
    expected_count=row.sample_count
    required=instruction(expected_count)
    content=await read_photo(request)
    automatic=request.headers.get("x-capture-mode")=="auto"
    if automatic and not tracker.consume(signature(row),hashlib.sha256(content).hexdigest(),request.headers.get("x-capture-token")):
        raise HTTPException(409,"Lượt tự chụp đã hết hạn hoặc chưa ổn định. Camera cần rà soát lại.")
    try:
        vector,metadata=await run_in_threadpool(engine.analyze,bytes(content),get_settings().max_upload_bytes)
    except FaceInputError as error:
        feedback=QUALITY_FEEDBACK.get(error.code,"Không đọc được ảnh. Hãy chụp lại bằng camera.")
        return JSONResponse(status_code=422,content={"accepted":False,"reason":error.code,"quality":error.details,
                            "feedback":f"Chưa đạt — mẫu {expected_count+1} chưa được lưu. {feedback}","next_instruction":required})
    fingerprint=hashlib.sha256(content).hexdigest()
    if db.scalar(select(CollectionSample.id).where(CollectionSample.model_id==row.model_id,CollectionSample.fingerprint==fingerprint)):
        raise HTTPException(409,"Chưa đạt — ảnh này đã có trong một bộ mẫu. Hãy chụp ảnh mới; số mẫu không tăng.")
    anchor=db.scalar(select(CollectionSample).where(CollectionSample.collection_id==collection_id,CollectionSample.position==1))
    accepted,feedback=check_pose(expected_count,metadata["quality"],anchor.quality if anchor else None)
    if automatic:
        aligned,frame_feedback=check_frame(metadata["quality"])
        if not aligned:
            accepted,feedback=False,frame_feedback
    if not accepted:
        return JSONResponse(status_code=422,content={"accepted":False,"reason":"wrong_pose","quality":metadata["quality"],
                            "feedback":f"Chưa đạt — mẫu {expected_count+1} chưa được lưu. {feedback}","next_instruction":required})
    quality=metadata["quality"] | {"required_pose":required["pose"],"pose_check":"relative_landmarks_provisional","guidance_protocol":PROTOCOL,
                                  "capture_mode":"auto" if automatic else "manual"}
    lock_employee(db,row.employee_id,expected_revision=row.biometric_revision,active_only=True)
    position=db.execute(update(FaceCollection).where(FaceCollection.id==collection_id,FaceCollection.status=="open",
                         FaceCollection.expires_at>datetime.now(UTC),FaceCollection.sample_count==expected_count)
                         .values(sample_count=FaceCollection.sample_count+1).returning(FaceCollection.sample_count)
                         .execution_options(synchronize_session=False)).scalar_one_or_none()
    if position is None:
        db.rollback()
        raise HTTPException(409,"Phiên không còn nhận mẫu. Hãy tải lại trạng thái.")
    db.add(CollectionSample(collection_id=collection_id,position=position,fingerprint=fingerprint,model_id=row.model_id,
                           vector=vector.astype("<f4").tobytes(),dimensions=int(vector.size),quality=quality))
    try:
        db.flush()
        db.refresh(row)
        state=describe(row)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409,"Ảnh này đã có trong một bộ mẫu. Hãy chụp ảnh mới để tránh trùng dữ liệu.") from error
    return {"accepted":True,"feedback":f"Đạt kiểm tra sơ bộ — đã lưu mẫu {position}: {required['title']}. Ảnh đủ chất lượng và hướng mặt phù hợp.",
            "collection":state,"quality":quality,"image_saved":False,"vector_saved":True}


@router.post("/collections/{collection_id}/complete")
def complete_collection(collection_id:str,db:Db,user:MutationAdmin):
    row=db.get(FaceCollection,collection_id)
    if not row:
        raise HTTPException(404,"Không có phiên thu mẫu.")
    employee_or_404(db,row.employee_id)
    lock_employee(db,row.employee_id,expected_revision=row.biometric_revision,active_only=True)
    row=db.scalar(select(FaceCollection).where(FaceCollection.id==collection_id).execution_options(populate_existing=True))
    if row is None:
        raise HTTPException(404,"Bộ mẫu đã bị xóa.")
    if row.status=="complete":
        return describe(row)
    changed=db.execute(update(FaceCollection).where(FaceCollection.id==collection_id,FaceCollection.status=="open",
                        FaceCollection.sample_count>=5)
                        .values(status="complete",completed_at=datetime.now(UTC)).execution_options(synchronize_session=False))
    if changed.rowcount!=1:
        db.rollback()
        raise HTTPException(409,"Cần ít nhất 5 mẫu đạt chất lượng trong bộ mẫu chưa hoàn tất hoặc hủy.")
    db.add(AuditLog(action="face_collection_complete",entity_id=collection_id,details={"employee_id":row.employee_id,"purpose":row.purpose}))
    db.refresh(row)
    state=describe(row)
    db.commit()
    return state


@router.post("/collections/{collection_id}/cancel")
def cancel_collection(collection_id:str,db:Db,user:MutationAdmin):
    row=db.get(FaceCollection,collection_id)
    if not row:
        raise HTTPException(404,"Không có phiên thu mẫu.")
    if row.status=="complete":
        raise HTTPException(409,"Bộ mẫu đã hoàn tất; dùng chức năng quản lý dữ liệu để xóa.")
    lock_employee(db,row.employee_id)
    row=db.scalar(select(FaceCollection).where(FaceCollection.id==collection_id).execution_options(populate_existing=True))
    if row is None:
        raise HTTPException(404,"Bộ mẫu đã bị xóa.")
    if row.status=="complete":
        raise HTTPException(409,"Bộ mẫu đã hoàn tất; dùng chức năng quản lý dữ liệu để xóa.")
    db.execute(delete(CollectionSample).where(CollectionSample.collection_id==collection_id))
    row.status="cancelled"
    row.sample_count=0
    db.add(AuditLog(action="face_collection_cancel",entity_id=collection_id,details={}))
    db.flush()
    state=describe(row)
    db.commit()
    return state
