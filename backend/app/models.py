from datetime import datetime, timezone

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Genre(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    slug: str = Field(index=True, unique=True)
    is_default: bool = False
    sort_order: int = 0


class Playlist(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    genre_id: int = Field(foreign_key="genre.id", index=True)
    youtube_playlist_id: str
    label: str = ""


class TrackCache(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    playlist_id: int = Field(foreign_key="playlist.id", index=True)
    youtube_video_id: str
    title: str
    artist: str
    thumbnail_url: str = ""
    duration_seconds: int = 0
    position: int = 0
    fetched_at: datetime = Field(default_factory=_utcnow)


class ScheduleSlot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    genre_id: int = Field(foreign_key="genre.id", index=True)
    days_of_week: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    start_time: str


class Setting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str = ""


class RevokedSession(SQLModel, table=True):
    jti: str = Field(primary_key=True)
    expires_at: datetime = Field(index=True)
