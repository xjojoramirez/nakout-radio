from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.broadcast import get_current, utcnow
from app.db import get_session
from app.routers.genres import tracks_for_genre
from app.schemas import NowOut, GenreOut, TrackOut

router = APIRouter(prefix="/api", tags=["now"])


def build_now(session: Session, ts: datetime) -> NowOut:
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
    return NowOut(
        genre=genre_out,
        track=TrackOut.model_validate(state.track) if state.track else None,
        offset_seconds=state.offset_seconds,
        server_time=ts.replace(tzinfo=timezone.utc).isoformat(),
        source=state.source,
    )


@router.get("/now", response_model=NowOut)
def now(session: Session = Depends(get_session)) -> NowOut:
    return build_now(session, utcnow())
