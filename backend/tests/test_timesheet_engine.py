from datetime import UTC, date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from app.shift_rules import ShiftInput, minute
from app.timesheet_engine import Punch, Schedule, calculate

DAY = date(2026, 10, 28)
AS_OF = datetime(2026, 10, 30, tzinfo=UTC)


def shift(start="08:00", end="17:00", breaks=None, identity="day", before=120, after=120, grace=0):
    payload = ShiftInput(
        name="Ca thử",
        start=start,
        end=end,
        breaks=breaks if breaks is not None else [{"start": "12:00", "end": "13:00", "paid": False}],
        capture_before_minutes=before,
        capture_after_minutes=after,
        late_grace_minutes=grace,
        early_grace_minutes=grace,
    )
    return SimpleNamespace(
        id=identity,
        revision=1,
        timezone="Asia/Ho_Chi_Minh",
        start_minute=minute(start),
        end_minute=minute(end),
        rules=payload.normalized_rules(),
    )


def instant(value, day=DAY):
    return datetime.fromisoformat(f"{day.isoformat()}T{value}+07:00").astimezone(UTC)


def punches(*values, day=DAY):
    return [
        Punch(str(index), "p", direction, instant(value, day))
        for index, (direction, value) in enumerate(values)
    ]


def row(events, definition=None, as_of=AS_OF, day=DAY):
    report = calculate([Schedule("assignment", "p", day, definition or shift())], events, as_of)
    return report["rows"][0]


@pytest.mark.parametrize(
    "arrival,departure,minutes,late,early",
    [
        ("08:00", "17:00", 480, 0, 0),
        ("08:07", "17:00", 473, 420, 0),
        ("08:00", "16:52", 472, 0, 480),
        ("08:07:30", "17:00", 472.5, 450, 0),
        ("07:50", "17:10", 480, 0, 0),
    ],
)
def test_day_examples_exact_elapsed_time_and_outside_time(arrival, departure, minutes, late, early):
    result = row(punches(("in", arrival), ("out", departure)))
    assert result["status"] == "complete"
    assert result["worked_seconds"] == minutes * 60
    assert result["late_seconds"] == late
    assert result["early_seconds"] == early
    assert result["is_late"] is (late > 0)
    assert result["is_early"] is (early > 0)
    if arrival == "07:50":
        assert result["outside_shift_seconds"] == 20 * 60


def test_no_double_subtraction_for_unpaid_break_with_exit_and_reentry():
    result = row(punches(("in", "08:00"), ("out", "12:00"), ("in", "13:00"), ("out", "17:00")))
    assert result["worked_seconds"] == 480 * 60
    assert result["presence_seconds"] == 480 * 60
    assert result["unpaid_break_seconds"] == 0


def test_paid_break_credits_only_eligible_gap_and_never_double_counts():
    paid = shift(breaks=[{"start": "12:00", "end": "13:00", "paid": True}])
    absent_at_break = row(punches(("in", "08:00"), ("out", "12:00"), ("in", "13:00"), ("out", "17:00")), paid)
    assert absent_at_break["worked_seconds"] == 540 * 60
    assert absent_at_break["paid_break_credit_seconds"] == 60 * 60
    present = row(punches(("in", "08:00"), ("out", "17:00")), paid)
    assert present["worked_seconds"] == 540 * 60
    assert present["paid_break_credit_seconds"] == 0
    longer_gap = row(punches(("in", "08:00"), ("out", "11:45"), ("in", "13:15"), ("out", "17:00")), paid)
    assert longer_gap["worked_seconds"] == 510 * 60
    left_before = row(punches(("in", "08:00"), ("out", "12:00")), paid)
    assert left_before["worked_seconds"] == 240 * 60
    assert left_before["paid_break_credit_seconds"] == 0


@pytest.mark.parametrize(
    "events,flag,confirmed",
    [
        ([("in", "08:00")], "missing_out", 0),
        ([("out", "17:00")], "missing_in", 0),
        ([], "no_punches", 0),
        ([("in", "08:00"), ("out", "12:00"), ("in", "13:00")], "missing_out", 240),
        ([("in", "08:00"), ("in", "08:10"), ("out", "17:00")], "repeated_in", 480),
        ([("in", "08:00"), ("out", "12:00"), ("out", "17:00")], "missing_in", 240),
    ],
)
def test_missing_or_repeated_punches_never_infer_full_work(events, flag, confirmed):
    result = row(punches(*events))
    assert result["worked_seconds"] is None
    assert flag in result["exceptions"]
    assert result["confirmed_seconds"] == confirmed * 60


def test_same_time_opposite_directions_require_review():
    result = row(punches(("in", "08:00"), ("out", "12:00"), ("in", "12:00"), ("out", "17:00")))
    assert result["worked_seconds"] is None
    assert "same_time_conflict" in result["exceptions"]


def test_current_and_future_shifts_are_not_finalized_and_grace_does_not_add_work():
    definition = shift(grace=10)
    result = row(punches(("in", "08:07"), ("out", "17:00")), definition)
    assert result["worked_seconds"] == 473 * 60
    assert not result["is_late"]
    current = row(punches(("in", "08:00"), ("out", "12:00")), as_of=instant("12:30"))
    assert current["status"] == "in_progress"
    assert current["worked_seconds"] is None
    assert current["early_seconds"] is None
    assert row([], as_of=instant("07:00"))["status"] == "upcoming"
    assert row([], as_of=instant("18:00"))["status"] == "pending"
    assert row([], as_of=instant("20:00"))["status"] == "incomplete"


def test_overnight_month_year_boundary_and_midnight_break():
    day = date(2026, 12, 31)
    night = shift("22:00", "06:00", breaks=[])
    events = [
        Punch("in", "p", "in", instant("22:00", day)),
        Punch("out", "p", "out", instant("06:00", date(2027, 1, 1))),
    ]
    result = row(events, night, as_of=datetime(2027, 1, 2, tzinfo=UTC), day=day)
    assert result["work_date"] == "2026-12-31"
    assert result["worked_seconds"] == 480 * 60
    with_break = shift("22:00", "06:00", breaks=[{"start": "23:45", "end": "00:15", "paid": False}])
    assert (
        row(events, with_break, as_of=datetime(2027, 1, 2, tzinfo=UTC), day=day)["worked_seconds"] == 450 * 60
    )


def test_direction_resolves_adjacent_boundary_but_overlapping_candidates_are_never_guessed():
    morning = shift("08:00", "12:00", breaks=[], identity="morning", before=0, after=0)
    afternoon = shift("12:00", "17:00", breaks=[], identity="afternoon", before=0, after=0)
    schedules = [Schedule("a", "p", DAY, morning), Schedule("b", "p", DAY, afternoon)]
    report = calculate(
        schedules, punches(("in", "08:00"), ("out", "12:00"), ("in", "12:00"), ("out", "17:00")), AS_OF
    )
    assert not report["ambiguous_events"]
    assert [item["worked_seconds"] for item in report["rows"]] == [240 * 60, 300 * 60]
    late_morning = shift("08:00", "12:00", breaks=[], identity="morning", after=120)
    early_afternoon = shift("13:00", "17:00", breaks=[], identity="afternoon", before=120)
    report = calculate(
        [Schedule("a", "p", DAY, late_morning), Schedule("b", "p", DAY, early_afternoon)],
        punches(("in", "11:30")),
        AS_OF,
    )
    assert len(report["ambiguous_events"]) == 1
    assert all(item["status"] == "needs_review" and item["worked_seconds"] is None for item in report["rows"])


def test_unassigned_wrong_direction_and_other_person_never_count():
    events = punches(("in", "17:30"), ("out", "07:00"))
    events.append(Punch("other", "someone-else", "in", instant("08:00")))
    report = calculate([Schedule("a", "p", DAY, shift())], events, AS_OF)
    assert len(report["unassigned_events"]) == 3
    assert report["rows"][0]["worked_seconds"] is None


def test_reproducibility_timezone_normalization_and_duplicate_id_protection():
    schedule = Schedule("a", "p", DAY, shift())
    events = punches(("in", "08:00"), ("out", "17:00"))
    first = calculate([schedule], events, AS_OF)
    assert calculate([schedule], list(reversed(events)) + [events[0]], AS_OF) == first
    local = [
        Punch(
            item.id,
            item.employee_id,
            item.direction,
            item.at.astimezone(datetime.fromisoformat("2026-01-01T00:00+07:00").tzinfo),
        )
        for item in events
    ]
    assert calculate([schedule], local, AS_OF) == first
    with pytest.raises(ValueError, match="conflicting_punch_id"):
        calculate([schedule], events + [Punch("0", "p", "out", events[0].at)], AS_OF)
    with pytest.raises(ValueError, match="requires_timezone"):
        calculate([schedule], events, AS_OF.replace(tzinfo=None))


def test_repeated_wall_clock_hour_does_not_hide_conflicting_event_ids():
    zone = ZoneInfo("America/New_York")
    earlier = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=0)
    later = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=1)
    with pytest.raises(ValueError, match="conflicting_punch_id"):
        calculate(
            [],
            [Punch("same", "p", "in", earlier), Punch("same", "p", "in", later)],
            datetime(2026, 11, 2, tzinfo=UTC),
        )
