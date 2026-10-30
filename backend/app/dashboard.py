"""Read-only dashboard counts from the local database, using the configured workday."""
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from sqlalchemy import func, select

from .auth import Admin, Db
from .devices import aware
from .models import AttendanceEvent, Device, Employee
from .shifts import configured_timezone

router = APIRouter(prefix="/api/admin/dashboard", tags=["dashboard"])


@router.get("")
def overview(db: Db, user: Admin):
    now = datetime.now(UTC)
    timezone = configured_timezone()
    day = now.astimezone(ZoneInfo(timezone)).date()
    start = datetime.combine(day, time(), ZoneInfo(timezone)).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time(), ZoneInfo(timezone)).astimezone(UTC)
    today = (AttendanceEvent.server_time >= start, AttendanceEvent.server_time < end)
    paired = (Device.active == True, Device.token_hash.is_not(None), Device.token_expires_at > now)  # noqa: E712
    recent = db.execute(select(AttendanceEvent, Employee).join(Employee).where(*today)
        .order_by(AttendanceEvent.server_time.desc(), AttendanceEvent.id.desc()).limit(8)).all()
    return {"timezone": timezone, "date": day.isoformat(), "server_time": now.isoformat(),
        "employee_total": db.scalar(select(func.count()).select_from(Employee).where(Employee.deleted_at.is_(None))),
        "employee_active": db.scalar(select(func.count()).select_from(Employee).where(Employee.active == True)),  # noqa: E712
        "attendance_today": db.scalar(select(func.count()).select_from(AttendanceEvent).where(*today)),
        "paired_devices": db.scalar(select(func.count()).select_from(Device).where(*paired)),
        "online_devices": db.scalar(select(func.count()).select_from(Device).where(*paired,
            Device.last_seen_at >= now-timedelta(minutes=2))),
        "recent": [{"id": event.id, "employee_id": person.id, "employee_code": person.code,
                    "employee_name": person.name, "direction": event.direction,
                    "occurred_at": aware(event.server_time).isoformat(), "kind": "kiosk"} for event, person in recent]}
