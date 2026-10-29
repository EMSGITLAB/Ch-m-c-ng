"""Versioned shift rules, independent of attendance recognition."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .employees import EmployeeInput

CLOCK = r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$"


def minute(value):
    hours, minutes = map(int, value.split(":"))
    return hours * 60 + minutes


def clock(value):
    return f"{value % 1440 // 60:02d}:{value % 60:02d}"


class BreakInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: str = Field(pattern=CLOCK)
    end: str = Field(pattern=CLOCK)
    paid: bool = False


class ShiftInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=100)
    start: str = Field(pattern=CLOCK)
    end: str = Field(pattern=CLOCK)
    breaks: list[BreakInput] = Field(default_factory=list, max_length=8)
    late_grace_minutes: int = Field(default=0, ge=0, le=180)
    early_grace_minutes: int = Field(default=0, ge=0, le=180)
    capture_before_minutes: int = Field(default=120, ge=0, le=720)
    capture_after_minutes: int = Field(default=120, ge=0, le=720)

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value):
        return EmployeeInput.clean_text(value)

    @model_validator(mode="after")
    def validate_intervals(self):
        self.normalized_rules()
        return self

    def normalized_rules(self):
        start = minute(self.start)
        duration = (minute(self.end) - start) % 1440
        if not duration:
            raise ValueError("Giờ vào và ra không được trùng nhau; ca phải ngắn hơn 24 giờ.")
        breaks = []
        for item in self.breaks:
            begin, end = (minute(item.start) - start) % 1440, (minute(item.end) - start) % 1440
            if end <= begin:
                end += 1440
            if end > duration:
                raise ValueError("Khoảng nghỉ phải nằm trong ca, kể cả khi qua nửa đêm.")
            breaks.append({"start_offset": begin, "end_offset": end, "paid": item.paid})
        breaks.sort(key=lambda row: row["start_offset"])
        if any(
            left["end_offset"] > right["start_offset"]
            for left, right in zip(breaks, breaks[1:], strict=False)
        ):
            raise ValueError("Các khoảng nghỉ không được chồng nhau.")
        if duration - sum(row["end_offset"] - row["start_offset"] for row in breaks if not row["paid"]) <= 0:
            raise ValueError("Ca phải có thời gian làm việc lớn hơn 0.")
        return {
            "schema_version": 1,
            "breaks": breaks,
            "late_grace_minutes": self.late_grace_minutes,
            "early_grace_minutes": self.early_grace_minutes,
            "capture_before_minutes": self.capture_before_minutes,
            "capture_after_minutes": self.capture_after_minutes,
        }


def duration_minutes(shift):
    return (shift.end_minute - shift.start_minute) % 1440 or 1440


def describe_shift(shift):
    rules = shift.rules or {}
    breaks = rules.get("breaks", [])
    duration = duration_minutes(shift)
    return {
        "id": shift.id,
        "family_id": shift.family_id,
        "revision": shift.revision,
        "name": shift.name,
        "start": clock(shift.start_minute),
        "end": clock(shift.end_minute),
        "timezone": shift.timezone,
        "overnight": shift.end_minute <= shift.start_minute,
        "active": shift.archived_at is None,
        "duration_minutes": duration,
        "expected_work_minutes": duration
        - sum(row["end_offset"] - row["start_offset"] for row in breaks if not row["paid"]),
        "breaks": [
            {
                "start": clock(shift.start_minute + row["start_offset"]),
                "end": clock(shift.start_minute + row["end_offset"]),
                "paid": row["paid"],
            }
            for row in breaks
        ],
        **{
            key: rules.get(key, default)
            for key, default in [
                ("late_grace_minutes", 0),
                ("early_grace_minutes", 0),
                ("capture_before_minutes", 120),
                ("capture_after_minutes", 120),
            ]
        },
    }


def local_instant(local, zone):
    first, second = local.replace(tzinfo=zone, fold=0), local.replace(tzinfo=zone, fold=1)
    if (
        first.utcoffset() != second.utcoffset()
        or first.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != local
    ):
        raise ValueError("Giờ ca không tồn tại hoặc không duy nhất do đổi giờ mùa hè; cần chọn giờ khác.")
    return first.astimezone(UTC)


def shift_interval(shift, work_date):
    zone = ZoneInfo(shift.timezone)
    start = datetime.combine(work_date, time()) + timedelta(minutes=shift.start_minute)
    end = start + timedelta(minutes=duration_minutes(shift))
    return local_instant(start, zone), local_instant(end, zone)


def overlaps(left, right):
    return left[0] < right[1] and right[0] < left[1]
