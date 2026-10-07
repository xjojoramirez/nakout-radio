from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Playlist, ScheduleSlot, Setting, Genre, TrackCache


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _genre_with_playlist(session):
    st = Genre(name="A", slug="a")
    session.add(st)
    session.commit()
    session.refresh(st)
    pl = Playlist(genre_id=st.id, youtube_playlist_id="PL1")
    session.add(pl)
    session.commit()
    session.refresh(pl)
    return st, pl


def test_genre_slug_unique_defaults():
    s = Genre(name="Chill", slug="chill")
    assert s.is_default is False
    assert s.sort_order == 0


def test_schedule_slot_stores_days_list():
    slot = ScheduleSlot(
        genre_id=1,
        days_of_week=[0, 1, 2, 3, 4],
        start_time="06:00",
    )
    assert slot.days_of_week == [0, 1, 2, 3, 4]


def test_schedule_slot_days_round_trip(session):
    st, _ = _genre_with_playlist(session)
    slot = ScheduleSlot(
        genre_id=st.id,
        days_of_week=[0, 1, 2, 3, 4],
        start_time="06:00",
    )
    session.add(slot)
    session.commit()
    slot_id = slot.id
    session.expire(slot)
    loaded = session.exec(select(ScheduleSlot).where(ScheduleSlot.id == slot_id)).one()
    assert loaded.days_of_week == [0, 1, 2, 3, 4]
    assert not hasattr(loaded, "end_time")


def test_track_cache_fetched_at_round_trip_is_naive(session):
    _, pl = _genre_with_playlist(session)
    track = TrackCache(
        playlist_id=pl.id,
        youtube_video_id="vid1",
        title="Song",
        artist="Artist",
    )
    session.add(track)
    session.commit()
    track_id = track.id
    session.expire(track)
    loaded = session.exec(select(TrackCache).where(TrackCache.id == track_id)).one()
    assert isinstance(loaded.fetched_at, datetime)
    assert loaded.fetched_at.tzinfo is None


def test_duplicate_genre_slug_raises(session):
    session.add(Genre(name="One", slug="dup"))
    session.commit()
    session.add(Genre(name="Two", slug="dup"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_setting_round_trip(session):
    session.add(Setting(key="youtube_channel_id", value="UC123"))
    session.commit()
    loaded = session.get(Setting, "youtube_channel_id")
    assert loaded is not None
    assert loaded.value == "UC123"


def test_setting_value_can_be_updated(session):
    session.add(Setting(key="youtube_channel_title", value="Old"))
    session.commit()
    row = session.get(Setting, "youtube_channel_title")
    row.value = "New"
    session.add(row)
    session.commit()
    assert session.get(Setting, "youtube_channel_title").value == "New"
