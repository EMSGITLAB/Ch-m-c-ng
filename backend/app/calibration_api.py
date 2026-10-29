import threading

from fastapi import APIRouter, HTTPException, Query, Request

from .auth import Admin, Db, MutationAdmin
from .calibration import calibrate, load_samples
from .calibration_coverage import coverage

router = APIRouter(prefix="/api/admin/recognition", tags=["calibration"])
slots = threading.BoundedSemaphore(1)


@router.get("/calibration/coverage")
def data_coverage(request: Request, db: Db, user: Admin,
                  offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=100)):
    engine = getattr(request.app.state, "face_engine", None)
    if engine is None:
        raise HTTPException(503, "Model local chưa sẵn sàng.")
    return coverage(db, engine, offset, limit)


@router.post("/calibration")
def inspect_calibration(request: Request, db: Db, user: MutationAdmin):
    engine = getattr(request.app.state, "face_engine", None)
    if not engine:
        raise HTTPException(503, "Model local chưa sẵn sàng.")
    if not slots.acquire(blocking=False):
        raise HTTPException(429, "Đang đánh giá dữ liệu. Hãy chờ kết quả hiện tại.")
    try:
        return calibrate(load_samples(db, engine.model_id, engine.dimensions), engine.model_id, engine.dimensions)
    except ValueError as error:
        raise HTTPException(409, "Bộ dữ liệu không nhất quán về model, vector hoặc phân chia phiên. Cần kiểm tra trước khi hiệu chỉnh.") from error
    finally:
        slots.release()
