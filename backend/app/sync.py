from collections.abc import Callable

from sqlmodel import Session, delete, select

from app.models import Playlist, TrackCache, _utcnow
from app.youtube import TrackData


def sync_playlist(
    session: Session,
    playlist: Playlist,
    fetch: Callable[[str], list[TrackData]],
) -> int:
    tracks = fetch(playlist.youtube_playlist_id)
    # Loudness lookups are expensive and must survive re-syncs: carry them
    # over for video ids whose title/artist did not change. A changed title or
    # artist can mean a different Deezer match, so those are re-checked.
    previous = {
        t.youtube_video_id: (t.title, t.artist, t.gain_db, t.gain_checked_at)
        for t in session.exec(
            select(TrackCache).where(TrackCache.playlist_id == playlist.id)
        ).all()
    }
    session.exec(delete(TrackCache).where(TrackCache.playlist_id == playlist.id))
    for t in tracks:
        gain_db: float | None = None
        gain_checked_at = None
        old = previous.get(t.youtube_video_id)
        if old is not None and old[0] == t.title and old[1] == t.artist:
            gain_db, gain_checked_at = old[2], old[3]
        session.add(
            TrackCache(
                playlist_id=playlist.id,
                youtube_video_id=t.youtube_video_id,
                title=t.title,
                artist=t.artist,
                thumbnail_url=t.thumbnail_url,
                position=t.position,
                duration_seconds=t.duration_seconds,
                gain_db=gain_db,
                gain_checked_at=gain_checked_at,
            )
        )
    playlist.synced_at = _utcnow()
    session.add(playlist)
    session.commit()
    return len(tracks)
