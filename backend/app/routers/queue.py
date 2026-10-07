import random

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_session
from app.models import Genre
from app.queue import decode_cursor, encode_cursor
from app.routers.genres import tracks_for_genre
from app.schemas import AdvanceIn, AdvanceOut, TrackOut

router = APIRouter(prefix="/api/queue", tags=["queue"])


@router.post("/advance", response_model=AdvanceOut)
def advance(body: AdvanceIn, session: Session = Depends(get_session)) -> AdvanceOut:
    settings = get_settings()
    decoded = decode_cursor(settings.secret_key, body.cursor)
    if decoded is None:
        raise HTTPException(status_code=400, detail="invalid cursor")
    slug, position = decoded
    genre = session.exec(select(Genre).where(Genre.slug == slug)).first()
    if genre is None:
        raise HTTPException(status_code=404, detail="genre not found")
    tracks = tracks_for_genre(session, genre.id)
    total = len(tracks)
    if total == 0:
        return AdvanceOut(track=None, cursor=body.cursor)
    if body.direction == "random":
        new_position = random.randrange(total)
    elif body.direction == "prev":
        new_position = (position - 1) % total
    else:
        new_position = (position + 1) % total
    return AdvanceOut(
        track=TrackOut.model_validate(tracks[new_position]),
        cursor=encode_cursor(settings.secret_key, slug, new_position),
    )
