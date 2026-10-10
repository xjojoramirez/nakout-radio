from collections.abc import Callable

from sqlmodel import Session, delete

from app.models import Playlist, TrackCache, _utcnow
from app.youtube import TrackData


def sync_playlist(
    session: Session,
    playlist: Playlist,
    fetch: Callable[[str], list[TrackData]],
) -> int:
    tracks = fetch(playlist.youtube_playlist_id)
    session.exec(delete(TrackCache).where(TrackCache.playlist_id == playlist.id))
    for t in tracks:
        session.add(
            TrackCache(
                playlist_id=playlist.id,
                youtube_video_id=t.youtube_video_id,
                title=t.title,
                artist=t.artist,
                thumbnail_url=t.thumbnail_url,
                position=t.position,
                duration_seconds=t.duration_seconds,
            )
        )
    playlist.synced_at = _utcnow()
    session.add(playlist)
    session.commit()
    return len(tracks)
