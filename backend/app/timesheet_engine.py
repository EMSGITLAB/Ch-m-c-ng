"""Deterministic pairing and duration math. No inferred missing punches."""

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .shift_rules import duration_minutes, local_instant, shift_interval

CALCULATION_VERSION = "paired-shift-v1"


@dataclass(frozen=True)
class Punch:
    id: str
    employee_id: str
    direction: str
    at: datetime


@dataclass(frozen=True)
class Schedule:
    id: str
    employee_id: str
    work_date: date
    shift: object


def microseconds(delta):
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def merged(intervals):
    result = []
    for begin, end in sorted(intervals):
        if end <= begin:
            continue
        if result and begin <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((begin, end))
    return result


def intersection(left, right):
    begin, end = max(left[0], right[0]), min(left[1], right[1])
    return max(0, microseconds(end - begin))


def length(intervals):
    return sum(microseconds(end - begin) for begin, end in merged(intervals))


def net_duration(intervals, unpaid):
    union = merged(intervals)
    return length(union) - sum(intersection(span, pause) for span in union for pause in unpaid)


def seconds(value):
    return round(value / 1_000_000, 6)


def rules_for(schedule):
    shift = schedule.shift
    rules = shift.rules if shift.rules is not None else {}
    if not isinstance(rules, dict) or not isinstance(rules.get("breaks", []), list):
        raise ValueError("invalid_shift_rules")
    if rules.get("schema_version") is not None and rules.get("schema_version") != 1:
        raise ValueError("unsupported_shift_rules")
    duration = duration_minutes(shift)
    for pause in rules.get("breaks", []):
        if not isinstance(pause, dict) or not {"start_offset", "end_offset", "paid"} <= pause.keys():
            raise ValueError("invalid_break_rule")
        if not isinstance(pause["start_offset"], int) or not isinstance(pause["end_offset"], int):
            raise ValueError("invalid_break_rule")
    breaks = sorted(rules.get("breaks", []), key=lambda row: row["start_offset"])
    for index, row in enumerate(breaks):
        if not (0 <= row["start_offset"] < row["end_offset"] <= duration) or not isinstance(
            row["paid"], bool
        ):
            raise ValueError("invalid_break_rule")
        if index and breaks[index - 1]["end_offset"] > row["start_offset"]:
            raise ValueError("overlapping_break_rules")
    for key, limit in [
        ("late_grace_minutes", 180),
        ("early_grace_minutes", 180),
        ("capture_before_minutes", 720),
        ("capture_after_minutes", 720),
    ]:
        value = rules.get(key, 120 if key.startswith("capture_") else 0)
        if not isinstance(value, int) or not 0 <= value <= limit:
            raise ValueError("invalid_shift_rule")
    zone = ZoneInfo(shift.timezone)
    local_start = datetime.combine(schedule.work_date, time()) + timedelta(minutes=shift.start_minute)
    pauses = [
        (
            local_instant(local_start + timedelta(minutes=row["start_offset"]), zone),
            local_instant(local_start + timedelta(minutes=row["end_offset"]), zone),
            row["paid"],
        )
        for row in breaks
    ]
    return rules, pauses


def pair_punches(punches):
    ordered = sorted(punches, key=lambda punch: (punch.at, punch.id))
    by_time = defaultdict(list)
    for punch in ordered:
        by_time[punch.at].append(punch)
    conflicts = {instant for instant, items in by_time.items() if len({item.direction for item in items}) > 1}
    flags = {"same_time_conflict"} if conflicts else set()
    opened = None
    pairs = []
    for punch in ordered:
        if punch.at in conflicts:
            continue
        if punch.direction == "in":
            if opened is not None:
                flags.add("repeated_in")
            else:
                opened = punch
        elif opened is None:
            flags.add("missing_in")
        else:
            if punch.at <= opened.at:
                flags.add("invalid_pair_order")
            else:
                pairs.append((opened.at, punch.at))
            opened = None
    if opened is not None:
        flags.add("missing_out")
    if not ordered:
        flags.add("no_punches")
    return ordered, pairs, flags


def calculate(schedules, punches, as_of):
    if as_of.tzinfo is None:
        raise ValueError("as_of_requires_timezone")
    as_of = as_of.astimezone(UTC)
    punch_ids = {}
    for punch in punches:
        if punch.at.tzinfo is None or punch.direction not in {"in", "out"}:
            raise ValueError("invalid_punch")
        value = (punch.employee_id, punch.direction, punch.at.astimezone(UTC))
        if punch.id in punch_ids and punch_ids[punch.id] != value:
            raise ValueError("conflicting_punch_id")
        punch_ids[punch.id] = value
    unique = {
        punch.id: Punch(punch.id, punch.employee_id, punch.direction, punch.at.astimezone(UTC))
        for punch in punches
        if punch.at <= as_of
    }
    if len({row.id for row in schedules}) != len(schedules):
        raise ValueError("duplicate_schedule_id")
    contexts = {}
    by_employee = defaultdict(list)
    for row in schedules:
        rule, pauses = rules_for(row)
        start, end = shift_interval(row.shift, row.work_date)
        context = {
            "schedule": row,
            "start": start,
            "end": end,
            "rules": rule,
            "pauses": pauses,
            "before": start - timedelta(minutes=rule.get("capture_before_minutes", 120)),
            "after": end + timedelta(minutes=rule.get("capture_after_minutes", 120)),
            "punches": [],
            "ambiguous": [],
        }
        contexts[row.id] = context
        by_employee[row.employee_id].append(context)
    unassigned = []
    ambiguous = []
    for punch in sorted(unique.values(), key=lambda value: (value.at, value.id)):
        candidates = [
            context
            for context in by_employee[punch.employee_id]
            if (
                context["before"] <= punch.at < context["end"]
                if punch.direction == "in"
                else context["start"] < punch.at <= context["after"]
            )
        ]
        if len(candidates) == 1:
            candidates[0]["punches"].append(punch)
        elif len(candidates) > 1:
            item = {
                "event_id": punch.id,
                "employee_id": punch.employee_id,
                "at": punch.at.isoformat(),
                "direction": punch.direction,
                "candidate_assignments": sorted(context["schedule"].id for context in candidates),
            }
            ambiguous.append(item)
            for context in candidates:
                context["ambiguous"].append(punch.id)
        else:
            unassigned.append(
                {
                    "event_id": punch.id,
                    "employee_id": punch.employee_id,
                    "at": punch.at.isoformat(),
                    "direction": punch.direction,
                }
            )
    rows = []
    for _key, context in sorted(
        contexts.items(),
        key=lambda value: (value[1]["schedule"].work_date, value[1]["schedule"].employee_id, value[0]),
    ):
        row = context["schedule"]
        start, end = context["start"], context["end"]
        ordered, pairs, flags = pair_punches(context["punches"])
        if context["ambiguous"]:
            flags.add("ambiguous_window")
            flags.discard("no_punches")
        unpaid = [(begin, finish) for begin, finish, paid in context["pauses"] if not paid]
        paid = [(begin, finish) for begin, finish, is_paid in context["pauses"] if is_paid]
        in_shift = [
            (max(begin, start), min(finish, end))
            for begin, finish in pairs
            if max(begin, start) < min(finish, end)
        ]
        physical = net_duration(in_shift, unpaid)
        credit = 0
        if not flags and pairs:
            coverage = (pairs[0][0], pairs[-1][1])
            eligible = [
                (max(begin, coverage[0]), min(finish, coverage[1]))
                for begin, finish in paid
                if max(begin, coverage[0]) < min(finish, coverage[1])
            ]
            credit = net_duration(in_shift + eligible, unpaid) - physical
        confirmed = physical + credit
        if "ambiguous_window" in flags or flags & {"repeated_in", "same_time_conflict", "invalid_pair_order"}:
            status = "needs_review"
        elif as_of < start and not ordered:
            status = "upcoming"
        elif as_of < end:
            status = "in_progress"
        elif not flags:
            status = "complete"
        elif as_of <= context["after"]:
            status = "pending"
        else:
            status = "incomplete"
        first_in = next((item.at for item in ordered if item.direction == "in"), None)
        last_out = next((item.at for item in reversed(ordered) if item.direction == "out"), None)
        late = max(0, microseconds(first_in - start)) if first_in else None
        early = max(0, microseconds(end - last_out)) if last_out and as_of >= end and not flags else None
        row_result = {
            "assignment_id": row.id,
            "employee_id": row.employee_id,
            "work_date": row.work_date.isoformat(),
            "shift_id": row.shift.id,
            "shift_revision": row.shift.revision,
            "timezone": row.shift.timezone,
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "status": status,
            "exceptions": sorted(flags),
            "first_in": first_in.isoformat() if first_in else None,
            "last_out": last_out.isoformat() if last_out else None,
            "worked_seconds": seconds(confirmed) if status == "complete" else None,
            "confirmed_seconds": seconds(confirmed),
            "expected_seconds": seconds(net_duration([(start, end)], unpaid)),
            "presence_seconds": seconds(length(pairs)),
            "unpaid_break_seconds": seconds(length(in_shift) - physical),
            "paid_break_credit_seconds": seconds(credit),
            "outside_shift_seconds": seconds(length(pairs) - length(in_shift)),
            "late_seconds": seconds(late) if late is not None else None,
            "early_seconds": seconds(early) if early is not None else None,
            "is_late": late is not None and late > context["rules"].get("late_grace_minutes", 0) * 60_000_000,
            "is_early": early is not None
            and early > context["rules"].get("early_grace_minutes", 0) * 60_000_000,
            "event_ids": [item.id for item in ordered],
            "ambiguous_event_ids": sorted(context["ambiguous"]),
        }
        rows.append(row_result)
    source = {
        "version": CALCULATION_VERSION,
        "schedules": [
            {
                "id": row.id,
                "employee": row.employee_id,
                "date": row.work_date.isoformat(),
                "shift": row.shift.id,
                "revision": row.shift.revision,
                "timezone": row.shift.timezone,
                "start": row.shift.start_minute,
                "end": row.shift.end_minute,
                "rules": row.shift.rules,
            }
            for row in sorted(schedules, key=lambda value: value.id)
        ],
        "punches": [
            [item.id, item.employee_id, item.direction, item.at.astimezone(UTC).isoformat()]
            for item in sorted(unique.values(), key=lambda value: value.id)
        ],
    }
    digest = hashlib.sha256(
        json.dumps(source, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return {
        "calculation_version": CALCULATION_VERSION,
        "source_digest": digest,
        "as_of": as_of.isoformat(),
        "rows": rows,
        "unassigned_events": unassigned,
        "ambiguous_events": ambiguous,
        "finalized": False,
        "work_policy": "within_scheduled_shift;outside_time_reported_separately;no_rounding",
    }
