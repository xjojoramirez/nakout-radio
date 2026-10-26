from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import LOCKABLE_FIELDS


def _http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


class TrackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    youtube_video_id: str
    title: str
    artist: str
    thumbnail_url: str
    duration_seconds: int
    position: int
    volume_offset_db: float = 0.0


class GenreOut(BaseModel):
    id: int
    name: str
    slug: str
    is_default: bool
    color: str = ""
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
    phase: Literal["playing", "gap"] = "playing"
    next_track: TrackOut | None = None
    seconds_until_start: float | None = None
    preload_lead_seconds: float = 20.0


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
    synced_at: str | None = None


class PlayIn(BaseModel):
    genre_id: int
    youtube_video_id: str


class GenreRefIn(BaseModel):
    genre_id: int


class OrderIn(BaseModel):
    video_ids: list[str]


class QueueOut(BaseModel):
    tracks: list[TrackOut]
    index: int = -1
    live: bool = False
    manual: bool = False


class SlotTodayOut(BaseModel):
    id: int
    genre_id: int
    genre_name: str
    start_time: str


class ScheduleTodayOut(BaseModel):
    current_id: int | None = None
    slots: list[SlotTodayOut] = []
    carry: SlotTodayOut | None = None


class ChangelogEntryOut(BaseModel):
    date: str
    title: str
    summary: str


# --------------------------------------------------------------------------
# Track details
# --------------------------------------------------------------------------

class ChartEntryIn(BaseModel):
    chart_name: str = Field(min_length=1, max_length=120)
    country: str = Field(default="", max_length=40)
    peak: int = Field(ge=1, le=200)
    weeks_on_chart: int | None = Field(default=None, ge=0, le=2000)
    year: int | None = Field(default=None, ge=1900, le=2100)
    source_url: str = Field(default="", max_length=500)

    @field_validator("chart_name")
    @classmethod
    def _chart_name(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("chart_name is required")
        return v

    @field_validator("country")
    @classmethod
    def _country(cls, v: str) -> str:
        v = (v or "").strip()
        return v.upper() if len(v) <= 3 else v

    @field_validator("source_url")
    @classmethod
    def _source_url(cls, v: str) -> str:
        v = (v or "").strip()
        if v and not _http_url(v):
            raise ValueError("source_url must be an http(s) URL")
        return v


class CreditIn(BaseModel):
    role: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)

    @field_validator("role", "name")
    @classmethod
    def _clean(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("must not be empty")
        return v


class LinkIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    url: str = Field(min_length=1, max_length=500)

    @field_validator("label")
    @classmethod
    def _label(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("label must not be empty")
        return v

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        v = (v or "").strip()
        if not _http_url(v):
            raise ValueError("url must be an http(s) URL")
        return v


_TEXT_FIELDS = (
    "album",
    "album_artist",
    "release_date",
    "label",
    "catalog_number",
    "isrc",
    "country",
    "language",
    "musical_key",
    "cover_url",
    "summary",
    "story",
    "dj_note",
    "lyric_snippet",
)


class TrackDetailIn(BaseModel):
    album: str | None = Field(default=None, max_length=300)
    album_artist: str | None = Field(default=None, max_length=300)
    release_date: str | None = Field(default=None, max_length=20)
    release_year: int | None = Field(default=None, ge=1900, le=2100)
    label: str | None = Field(default=None, max_length=200)
    catalog_number: str | None = Field(default=None, max_length=80)
    isrc: str | None = Field(default=None, max_length=20)
    track_number: int | None = Field(default=None, ge=1, le=999)
    disc_number: int | None = Field(default=None, ge=1, le=99)
    genres: list[str] = Field(default_factory=list)
    country: str | None = Field(default=None, max_length=60)
    language: str | None = Field(default=None, max_length=60)
    bpm: int | None = Field(default=None, ge=20, le=400)
    musical_key: str | None = Field(default=None, max_length=20)
    cover_url: str | None = Field(default=None, max_length=500)

    summary: str | None = Field(default=None, max_length=1000)
    story: str | None = Field(default=None, max_length=20000)
    dj_note: str | None = Field(default=None, max_length=4000)
    dj_note_public: bool = True
    lyric_snippet: str | None = Field(default=None, max_length=200)
    moods: list[str] = Field(default_factory=list)
    similar_video_ids: list[str] = Field(default_factory=list)
    credits: list[CreditIn] = Field(default_factory=list)
    links: list[LinkIn] = Field(default_factory=list)

    charts: list[ChartEntryIn] = Field(default_factory=list)
    locked_fields: list[str] = Field(default_factory=list)

    @field_validator(*_TEXT_FIELDS, mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    @field_validator("cover_url")
    @classmethod
    def _cover_url(cls, v: str | None) -> str | None:
        if v and not _http_url(v):
            raise ValueError("cover_url must be an http(s) URL")
        return v

    @field_validator("genres", "moods", "similar_video_ids")
    @classmethod
    def _clean_list(cls, v: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in v:
            item = (item or "").strip()
            if item and item not in cleaned:
                cleaned.append(item)
        return cleaned

    @field_validator("genres", "moods")
    @classmethod
    def _cap_tags(cls, v: list[str]) -> list[str]:
        if len(v) > 24:
            raise ValueError("at most 24 entries are allowed")
        if any(len(item) > 60 for item in v):
            raise ValueError("entries must be 60 characters or fewer")
        return v

    @field_validator("similar_video_ids")
    @classmethod
    def _cap_similar(cls, v: list[str]) -> list[str]:
        if len(v) > 20:
            raise ValueError("at most 20 similar tracks are allowed")
        return v

    @field_validator("charts")
    @classmethod
    def _cap_charts(cls, v: list[ChartEntryIn]) -> list[ChartEntryIn]:
        if len(v) > 50:
            raise ValueError("at most 50 chart entries are allowed")
        return v

    @field_validator("locked_fields")
    @classmethod
    def _valid_locks(cls, v: list[str]) -> list[str]:
        unknown = [field for field in v if field not in LOCKABLE_FIELDS]
        if unknown:
            raise ValueError(f"unknown locked field: {unknown[0]}")
        return list(dict.fromkeys(v))


class ChartEntryOut(BaseModel):
    chart_name: str
    country: str = ""
    peak: int
    weeks_on_chart: int | None = None
    year: int | None = None
    source_url: str = ""


class SimilarTrackOut(BaseModel):
    youtube_video_id: str
    title: str = ""
    artist: str = ""


class TrackDetailBase(BaseModel):
    youtube_video_id: str
    title: str = ""
    artist: str = ""

    album: str | None = None
    album_artist: str | None = None
    release_date: str | None = None
    release_year: int | None = None
    label: str | None = None
    catalog_number: str | None = None
    isrc: str | None = None
    track_number: int | None = None
    disc_number: int | None = None
    genres: list[str] = Field(default_factory=list)
    country: str | None = None
    language: str | None = None
    bpm: int | None = None
    musical_key: str | None = None
    cover_url: str | None = None

    summary: str | None = None
    story: str | None = None
    dj_note: str | None = None
    lyric_snippet: str | None = None
    moods: list[str] = Field(default_factory=list)
    credits: list[CreditIn] = Field(default_factory=list)
    links: list[LinkIn] = Field(default_factory=list)

    charts: list[ChartEntryOut] = Field(default_factory=list)
    similar: list[SimilarTrackOut] = Field(default_factory=list)


class TrackDetailOut(TrackDetailBase):
    dj_note_public: bool = True
    sources: dict = Field(default_factory=dict)
    locked_fields: list[str] = Field(default_factory=list)
    needs_review: bool = False
    enriched_at: datetime | None = None
    enrich_error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    status: Literal["empty", "auto", "curated"] = "empty"
    completeness: int = 0


class TrackLibraryItem(BaseModel):
    youtube_video_id: str
    title: str
    artist: str
    thumbnail_url: str = ""
    duration_seconds: int = 0
    album: str | None = None
    release_year: int | None = None
    status: Literal["empty", "auto", "curated"] = "empty"
    completeness: int = 0
    genres: list[str] = Field(default_factory=list)


class TrackLibraryOut(BaseModel):
    items: list[TrackLibraryItem]
    total: int
    limit: int
    offset: int
