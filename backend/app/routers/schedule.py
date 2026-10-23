from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.broadcast import get_current, utcnow
from app.config import get_settings
from app.db import get_session
from app.models import Genre, ScheduleSlot
from app.routers.genres import tracks_for_genre
from app.schemas import (
    CurrentGenreOut,
    GenreOut,
    ScheduleTodayOut,
    SlotTodayOut,
    TrackOut,
)

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


def _last_slot_before(
    slots: list[ScheduleSlot], weekday: int
) -> ScheduleSlot | None:
    """Latest slot that started on an earlier weekday, searching back a week."""
    for offset in range(1, 7):
        day = (weekday - offset) % 7
        candidates = [slot for slot in slots if day in slot.days_of_week]
        if candidates:
            return max(candidates, key=lambda slot: slot.start_time)
    return None


@router.get("/now", response_model=CurrentGenreOut)
def schedule_now(session: Session = Depends(get_session)) -> CurrentGenreOut:
    ts = utcnow()
    state = get_current(session, ts)
    genre_out = None
    if state.genre is not None:
        genre_out = GenreOut(
            id=state.genre.id,
            name=state.genre.name,
            slug=state.genre.slug,
            is_default=state.genre.is_default,
            color=state.genre.color or "",
            track_count=len(tracks_for_genre(session, state.genre.id)),
        )
    return CurrentGenreOut(
        genre=genre_out,
        track=TrackOut.model_validate(state.track) if state.track else None,
        cursor=None,
        source=state.source,
        offset_seconds=state.offset_seconds,
        server_time=ts.replace(tzinfo=timezone.utc).isoformat(),
    )


@router.get("/today", response_model=ScheduleTodayOut)
def schedule_today(session: Session = Depends(get_session)) -> ScheduleTodayOut:
    """Today's schedule slots for the public homepage.

    Slots are filtered by the weekday of ``GENRE_TZ`` and sorted by start
    time. ``current_id`` is the latest slot that already started, falling back
    to the most recent slot from an earlier weekday so a show that runs past
    midnight keeps its indicator. ``carry`` exposes that earlier-weekday slot
    when it is not already part of today's list.
    """
    tz = ZoneInfo(get_settings().genre_tz)
    now = datetime.now(tz)
    now_str = f"{now.hour:02d}:{now.minute:02d}"
    weekday = now.weekday()
    genre_names = {g.id: g.name for g in session.exec(select(Genre)).all()}
    all_slots = session.exec(select(ScheduleSlot)).all()
    today = [
        SlotTodayOut(
            id=slot.id,
            genre_id=slot.genre_id,
            genre_name=genre_names.get(slot.genre_id, ""),
            start_time=slot.start_time,
        )
        for slot in all_slots
        if weekday in slot.days_of_week
    ]
    today.sort(key=lambda s: s.start_time)
    started = [s for s in today if s.start_time <= now_str]
    carry = None
    if started:
        current_id = started[-1].id
    else:
        previous = _last_slot_before(all_slots, weekday)
        current_id = previous.id if previous is not None else None
        if previous is not None and all(s.id != previous.id for s in today):
            carry = SlotTodayOut(
                id=previous.id,
                genre_id=previous.genre_id,
                genre_name=genre_names.get(previous.genre_id, ""),
                start_time=previous.start_time,
            )
    return ScheduleTodayOut(
        current_id=current_id,
        slots=today,
        carry=carry,
    )
