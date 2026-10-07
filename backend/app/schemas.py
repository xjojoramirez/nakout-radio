from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


class TrackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    youtube_video_id: str
    title: str
    artist: str
    thumbnail_url: str
    duration_seconds: int
    position: int


class GenreOut(BaseModel):
    id: int
    name: str
    slug: str
    is_default: bool
    track_count: int


class GenreDetail(GenreOut):
    track: TrackOut | None = None
    cursor: str | None = None


class CurrentGenreOut(BaseModel):
    genre: GenreOut | None
    track: TrackOut | None
    cursor: str | None = None
    source: str
    offset_seconds: int = 0
    server_time: str | None = None


class NowOut(BaseModel):
    genre: GenreOut | None
    track: TrackOut | None
    offset_seconds: int
    server_time: str
    source: str


class AdvanceIn(BaseModel):
    cursor: str
    direction: Literal["next", "prev", "random"] = "next"


class AdvanceOut(BaseModel):
    track: TrackOut | None
    cursor: str


class SlotIn(BaseModel):
    genre_id: int
    days_of_week: list[int]
    start_time: str

    @field_validator("days_of_week")
    @classmethod
    def _valid_days(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("days_of_week must not be empty")
        if any(d not in range(7) for d in v):
            raise ValueError("days_of_week entries must be 0-6")
        return v

    @field_validator("start_time")
    @classmethod
    def _valid_time(cls, v: str) -> str:
        try:
            return datetime.strptime(v, "%H:%M").strftime("%H:%M")
        except ValueError as exc:
            raise ValueError("time must be HH:MM") from exc


class SlotOut(BaseModel):
    id: int
    genre_id: int
    genre_name: str
    days_of_week: list[int]
    start_time: str


class SlotUpdate(BaseModel):
    genre_id: int | None = None
    days_of_week: list[int] | None = None
    start_time: str | None = None

    @field_validator("days_of_week")
    @classmethod
    def _valid_days(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return v
        if not v:
            raise ValueError("days_of_week must not be empty")
        if any(d not in range(7) for d in v):
            raise ValueError("days_of_week entries must be 0-6")
        return v

    @field_validator("start_time")
    @classmethod
    def _valid_time(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            return datetime.strptime(v, "%H:%M").strftime("%H:%M")
        except ValueError as exc:
            raise ValueError("time must be HH:MM") from exc


class PlaylistIn(BaseModel):
    genre_id: int
    youtube_playlist_url: str
    label: str = ""


class ChannelIn(BaseModel):
    channel: str


class ChannelOut(BaseModel):
    channel_id: str | None = None
    title: str | None = None


class ChannelPlaylistOut(BaseModel):
    youtube_playlist_id: str
    title: str
    item_count: int
    thumbnail_url: str
    already_added: bool


class PlaylistOut(BaseModel):
    id: int
    genre_id: int
    genre_name: str
    youtube_playlist_id: str
    label: str
    track_count: int


class PlayIn(BaseModel):
    genre_id: int
    youtube_video_id: str


class GenreRefIn(BaseModel):
    genre_id: int


class OrderIn(BaseModel):
    video_ids: list[str]
