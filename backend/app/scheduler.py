from datetime import datetime, time, timedelta

Slot = tuple[int, list[int], str]  # genre_id, days, start


def _to_time(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


def _most_recent_occurrence(now: datetime, day: int, start: str) -> datetime:
    """Most recent datetime <= now at ``start`` on weekday ``day``.

    Looks back at most one week, so it also covers the case where today's start
    time has not happened yet.
    """
    days_back = (now.weekday() - day) % 7
    candidate = datetime.combine(
        now.date() - timedelta(days=days_back), _to_time(start), now.tzinfo
    )
    if candidate > now:
        candidate -= timedelta(days=7)
    return candidate


def resolve_genre_id(
    slots: list[Slot], now: datetime, default_id: int | None
) -> int | None:
    """Return the genre whose most recent scheduled start is latest at ``now``.

    Returns ``default_id`` when no slot has any applicable start.
    """
    best: tuple[datetime, int, int] | None = None
    for index, (genre_id, days, start) in enumerate(slots):
        for day in days:
            candidate = (_most_recent_occurrence(now, day, start), index, genre_id)
            if best is None or candidate > best:
                best = candidate
    return best[2] if best is not None else default_id


def _next_occurrence(now: datetime, day: int, start: str) -> datetime:
    """The first datetime strictly after ``now`` for this weekly slot."""
    days_ahead = (day - now.weekday()) % 7
    candidate = datetime.combine(
        now.date() + timedelta(days=days_ahead), _to_time(start), now.tzinfo
    )
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def next_genre_change(
    slots: list[Slot],
    now: datetime,
    current_genre_id: int | None,
    default_id: int | None,
) -> datetime | None:
    """The next slot time at which the resolved genre differs from ``now``.

    Slot starts for the same genre are skipped, and a week is enough to cover
    every recurring slot. Returns ``None`` when the resolved genre never
    changes (or there are no slots).
    """
    if not slots:
        return None
    candidates = sorted(
        {
            _next_occurrence(now, day, start)
            for _, days, start in slots
            for day in days
        }
    )
    for candidate in candidates:
        resolved = resolve_genre_id(
            slots, candidate + timedelta(seconds=1), default_id
        )
        if resolved != current_genre_id:
            return candidate
    return None
