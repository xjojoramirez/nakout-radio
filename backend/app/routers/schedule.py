from datetime import timezone

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.broadcast import get_current, utcnow
from app.db import get_session
from app.routers.genres import tracks_for_genre
from app.schemas import CurrentGenreOut, GenreOut, TrackOut

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


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
