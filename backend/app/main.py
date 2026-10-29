import asyncio
import threading
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import cv2
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .access_logging import configure_access_logging
from .adjustments import router as adjustment_router
from .attendance_api import router as attendance_router
from .auth import Db, same_origin
from .auth import router as auth_router
from .biometrics import router as biometrics_router
from .calibration_api import router as calibration_router
from .collections import router as collections_router
from .config import get_settings
from .database import get_engine
from .devices import admin_router as device_admin_router
from .devices import kiosk_router
from .employees import router as employee_router
from .face_engine import FaceEngine, FaceInputError
from .frontend import install_frontend
from .imported_photos import router as imported_photo_router
from .operations import router as operations_router
from .pad_api import router as pad_router
from .pad_engine import PadEngine
from .periods import router as period_router
from .pilot_enrollment import router as pilot_router
from .profile_photos import router as profile_photo_router
from .recognition_api import admin_router as recognition_admin_router
from .recognition_api import router as recognition_router
from .runtime_status import attendance_state
from .shifts import router as shift_router
from .timesheet_exports import router as export_router
from .timesheets import router as timesheet_router


@asynccontextmanager
async def lifespan(application:FastAPI):
    configure_access_logging()
    application.state.face_engine=None
    application.state.face_error="model_not_initialized"
    settings=get_settings()
    application.state.attendance_policy_id=(
        settings.functional_trial_policy_id if settings.functional_trial_enabled else None
    )
    application.state.pad_engine=None
    application.state.pad_error="model_not_initialized"
    try:
        application.state.face_engine=await run_in_threadpool(FaceEngine,get_settings().models_dir)
        application.state.face_error=None
    except (OSError,ValueError,RuntimeError,cv2.error):
        application.state.face_error="model_load_failed"
    try:
        application.state.pad_engine=await run_in_threadpool(PadEngine,get_settings().models_dir / "pad")
        application.state.pad_error=None
    except (OSError,ValueError,RuntimeError,cv2.error):
        application.state.pad_error="experimental_pad_load_failed"
    try:
        yield
    finally:
        application.state.face_engine=None
        application.state.pad_engine=None


capture_slots=threading.BoundedSemaphore(2)

app = FastAPI(title="Chấm công local", version="0.2.0", docs_url="/api/docs", openapi_url="/api/openapi.json",lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=get_settings().allowed_hosts)
app.include_router(auth_router)
app.include_router(employee_router)
app.include_router(device_admin_router)
app.include_router(kiosk_router)
app.include_router(collections_router)
app.include_router(calibration_router)
app.include_router(biometrics_router)
app.include_router(attendance_router)
app.include_router(shift_router)
app.include_router(timesheet_router)
app.include_router(adjustment_router)
app.include_router(period_router)
app.include_router(imported_photo_router)
app.include_router(profile_photo_router)
app.include_router(export_router)
app.include_router(recognition_router)
app.include_router(recognition_admin_router)
app.include_router(pad_router)
app.include_router(pilot_router)
app.include_router(operations_router)


@app.exception_handler(SQLAlchemyError)
async def database_unavailable(request: Request, error: SQLAlchemyError):
    # Do not return driver messages, connection URLs, SQL parameters or vectors.
    return JSONResponse(status_code=503, content={"detail": "Chưa truy cập được dữ liệu. Vui lòng thử lại sau."})


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=()"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health/live")
def live():
    return {"status": "alive", "version": app.version}


@app.get("/health/ready")
def ready(db: Db):
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        database = True
    except SQLAlchemyError:
        database = False
    recognition=getattr(app.state,"face_engine",None) is not None
    state=attendance_state(db,getattr(app.state,"face_engine",None),getattr(app.state,"attendance_policy_id",None)) if database else {"attendance_enabled":False}
    available=database and recognition and state["attendance_enabled"]
    return JSONResponse(status_code=200 if available else 503, content={"ready": available, "database": database, "recognition": recognition, "attendance_enabled":state["attendance_enabled"],"reason": None if available else "attendance_not_initialized"})


@app.get("/api/system/status")
def status(db: Db):
    settings = get_settings()
    business = settings.business()
    recognition=getattr(app.state,"face_engine",None) is not None
    return {"app_name": settings.app_name, "version": app.version, "mode": "local", "stage": "M3", "timezone": business.timezone,
            "server_time": datetime.now(UTC).isoformat(), "recognition_ready": recognition,
            "experimental_pad_ready": recognition and getattr(app.state,"pad_engine",None) is not None,
            "pad_validated_for_attendance": False,
            "capture_max_edge": settings.capture_max_edge,
            **attendance_state(db,getattr(app.state,"face_engine",None),getattr(app.state,"attendance_policy_id",None))}


@app.post("/api/diagnostics/face")
async def check_capture(request:Request):
    same_origin(request)
    if get_settings().environment!="development" or not request.client or request.client.host not in {"127.0.0.1","::1","testclient"}:
        raise HTTPException(403,"Chụp thử chỉ được mở trên laptop phát triển.")
    if request.headers.get("x-local-capture")!="quality-test":
        raise HTTPException(403,"Thiếu yêu cầu chụp thử.")
    engine=getattr(app.state,"face_engine",None)
    if engine is None:
        raise HTTPException(503,"Model local chưa sẵn sàng.")
    if not capture_slots.acquire(blocking=False):
        raise HTTPException(429,"Máy chủ đang xử lý ảnh. Vui lòng thử lại.")
    try:
        content=bytearray()
        try:
            async with asyncio.timeout(10):
                async for chunk in request.stream():
                    content.extend(chunk)
                    if len(content)>get_settings().max_upload_bytes:
                        raise HTTPException(413,"Ảnh vượt dung lượng cho phép.")
        except TimeoutError as error:
            raise HTTPException(408,"Truyền ảnh quá lâu. Vui lòng thử lại.") from error
        try:
            vector,metadata=await run_in_threadpool(engine.analyze,bytes(content),get_settings().max_upload_bytes)
        except FaceInputError as error:
            return JSONResponse(status_code=422,content={"accepted":False,"reason":error.code,"quality":error.details,"stored":False,"attendance_recorded":False})
        del vector
        return {"accepted":True,**metadata,"stored":False,"attendance_recorded":False}
    finally:
        capture_slots.release()


if get_settings().serve_frontend:
    install_frontend(app, get_settings().frontend_dist_path)

