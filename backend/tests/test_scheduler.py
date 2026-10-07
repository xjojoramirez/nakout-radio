from datetime import datetime
from zoneinfo import ZoneInfo

from app.scheduler import resolve_genre_id

TZ = ZoneInfo("Asia/Manila")


def _dt(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=TZ)


def test_resolve_within_run():
    slots = [(1, [0, 1, 2, 3, 4], "06:00")]
    assert resolve_genre_id(slots, _dt(2026, 1, 5, 9), default_id=9) == 1  # Mon


def test_empty_slots_returns_default():
    assert resolve_genre_id([], _dt(2026, 1, 5, 9), default_id=9) == 9


def test_later_same_day_start_wins():
    slots = [(1, [0], "06:00"), (2, [0], "12:00")]
    assert resolve_genre_id(slots, _dt(2026, 1, 5, 8), default_id=9) == 1
    assert resolve_genre_id(slots, _dt(2026, 1, 5, 13), default_id=9) == 2


def test_before_first_start_wraps_to_previous_week():
    # Monday 03:00 is before Monday 06:00, so the last start was a week ago.
    slots = [(1, [0], "06:00")]
    assert resolve_genre_id(slots, _dt(2026, 1, 5, 3), default_id=9) == 1


def test_overnight_wraps_to_previous_day():
    # Monday 22:00 runs into Tuesday early morning.
    slots = [(1, [0], "22:00")]
    assert resolve_genre_id(slots, _dt(2026, 1, 6, 1), default_id=9) == 1


def test_weekday_slot_carries_into_weekend():
    # With only a weekday slot, the most recent start on Saturday is Friday's.
    slots = [(1, [0, 1, 2, 3, 4], "06:00")]
    assert resolve_genre_id(slots, _dt(2026, 1, 10, 9), default_id=9) == 1  # Sat


def test_most_recent_day_wins():
    slots = [(1, [0], "08:00"), (2, [2], "08:00")]
    assert resolve_genre_id(slots, _dt(2026, 1, 7, 9), default_id=9) == 2  # Wed
    assert resolve_genre_id(slots, _dt(2026, 1, 6, 9), default_id=9) == 1  # Tue
