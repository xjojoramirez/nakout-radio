"""Wikipedia story and chart enrichment."""

from datetime import datetime

import httpx
import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.enrichment.base import ProviderError
from app.enrichment.pipeline import (
    enrich_stories_pending,
    enrich_story,
    progress,
)
from app.enrichment.wikipedia import (
    ChartData,
    WikipediaData,
    lookup_wikipedia,
    parse_charts,
)
from app.models import (
    Genre,
    Playlist,
    TrackCache,
    TrackChartEntry,
    TrackDetail,
)

EXTRACT = '''"Blue in Green" is a jazz ballad by Miles Davis, first released in 1959 on
the album Kind of Blue. It is credited to Davis and Bill Evans.

== Background ==
Davis composed the piece with Bill Evans in 1959. Evans supplied the harmonic
framework, and the pair developed it during the Kind of Blue sessions. The
recording was made in two takes at Columbia's 30th Street Studio.

== Composition ==
The piece is a ten-bar form rather than the usual twelve-bar blues. Its modal
harmony moves slowly, leaving room for the trumpet and piano solos that made
the album famous.

=== Development ===
The arrangement was sketched in one afternoon.

== References ==
Citations that should never appear in liner notes.
'''

WIKITEXT = """
== Charts ==
=== Weekly charts ===
{{single chart|Billboardhot100|3|artist=Miles Davis|song=Blue in Green}}
{{single chart|UK|12|artist=Miles Davis|song=Blue in Green|date=1959-11-02}}
{{single chart|Billboardhot100|5|artist=Miles Davis|song=Blue in Green}}
=== Year-end charts ===
{{single chart|UK|40|artist=Miles Davis|song=Blue in Green}}
=== Decade-end charts ===
{{single chart|Billboardhot100|80|artist=Miles Davis|song=Blue in Green}}
"""

# Jump (Van Halen) style: weekly charts written as a plain wikitables, with a
# template row mixed in and a separate year-end table that must be ignored.
WIKITABLE = """
== Charts ==
=== Weekly charts ===
{| class="wikitable sortable"
|-
!Chart (1984)
!Peak<br/>position
|-
|Argentina ([[CAPIF]])<ref>{{cite web|url=x|title=y}}</ref>
|align="center"|8
|-
{{Single chart|Austria|4|artist=Van Halen|song=Jump}}
|-
|US ''Billboard'' Hot 100<ref name="musicvf.com"/>
| style="text-align:center;"|1
|-
|South Africa (Springbok Radio)
|align="center"|6
|-
|{{Single chart|Ireland2|5|song=Torn Between Two Lovers}}
|-
|UK Singles ([[Official Charts Company|OCC]])
| style="text-align:center;"|7
|}
=== Year-end charts ===
{| class="wikitable sortable"
|-
!Chart (1984)
!Peak<br/>position
|-
|US ''Billboard'' Hot 100
|6
|}
"""


def _chart_pairs(charts):
    return {(entry.chart_name, entry.peak) for entry in charts}

PAGE_URL = "https://en.wikipedia.org/wiki/Blue_in_Green_(song)"


def _client(extract: str = EXTRACT, wikitext_status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        action = params.get("action")
        if action == "query" and params.get("list") == "search":
            return httpx.Response(
                200,
                json={
                    "query": {
                        "search": [
                            {"title": "Blue in Green (song)"},
                            {"title": "Blue in Green (album)"},
                        ]
                    }
                },
            )
        if action == "query":
            return httpx.Response(
                200,
                json={
                    "query": {
                        "pages": [
                            {
                                "title": "Blue in Green (song)",
                                "fullurl": PAGE_URL,
                                "extract": extract,
                            }
                        ]
                    }
                },
            )
        if action == "parse":
            if wikitext_status != 200:
                return httpx.Response(wikitext_status)
            return httpx.Response(
                200, json={"parse": {"wikitext": WIKITEXT}}
            )
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _wiki(**overrides) -> WikipediaData:
    data = WikipediaData(
        title="Blue in Green (song)",
        url=PAGE_URL,
        summary='"Blue in Green" is a jazz ballad by Miles Davis.',
        story="Davis composed the piece with Bill Evans in 1959.",
        charts=[
            ChartData(
                chart_name="Billboard Hot 100",
                country="US",
                peak=3,
                year=1959,
            )
        ],
        confidence="exact",
    )
    for key, value in overrides.items():
        setattr(data, key, value)
    return data


# --- provider --------------------------------------------------------------


def test_lookup_maps_summary_story_and_charts():
    data = lookup_wikipedia(
        "Blue in Green (Remaster)", "Miles Davis", _client(),
        sleep=lambda _: None,
    )

    assert data is not None
    assert data.url == PAGE_URL
    assert data.confidence == "exact"
    assert data.summary.startswith('"Blue in Green" is a jazz ballad')
    assert "ten-bar form" in data.story
    assert "References" not in data.story
    assert "===" not in data.story
    assert "sketched in one afternoon" in data.story
    assert "\n\n" in data.story
    assert [(entry.chart_name, entry.peak) for entry in data.charts] == [
        ("Billboard Hot 100", 3),
        ("UK Singles (OCC)", 12),
    ]
    uk = next(entry for entry in data.charts if entry.country == "GB")
    assert uk.year == 1959


def test_story_keeps_whole_sentences_within_the_limit():
    sentence = "The song was written in a small studio in 1959."
    long_section = " ".join([sentence] * 40)
    extract = (
        '"Blue in Green" is a jazz ballad by Miles Davis.\n\n'
        f"== Background ==\n{long_section}\n"
    )

    data = lookup_wikipedia(
        "Blue in Green", "Miles Davis", _client(extract=extract),
        sleep=lambda _: None,
    )

    assert data is not None
    assert len(data.story) <= 950
    assert data.story.endswith(".")
    assert "..." not in data.story


def test_lookup_rejects_a_page_that_does_not_mention_the_artist():
    extract = '"Blue in Green" is a jazz ballad first released in 1959.\n'

    assert lookup_wikipedia(
        "Blue in Green",
        "Miles Davis",
        _client(extract=extract),
        sleep=lambda _: None,
    ) is None


def test_lookup_ignores_an_artist_word_used_as_ordinary_prose():
    # "Release" is a band name, but the Alicia Keys article only uses the
    # word "release"; the old substring check happily matched it.
    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("list") == "search":
            return httpx.Response(
                200,
                json={
                    "query": {
                        "search": [
                            {"title": "Fallin' (Alicia Keys song)"}
                        ]
                    }
                },
            )
        if params.get("action") == "query":
            return httpx.Response(
                200,
                json={
                    "query": {
                        "pages": [
                            {
                                "title": "Fallin' (Alicia Keys song)",
                                "fullurl": "https://en.wikipedia.org/wiki/Fallin%27_(Alicia_Keys_song)",
                                "extract": (
                                    "\"Fallin'\" is a song by American singer "
                                    "Alicia Keys, released in 2001.\n\n"
                                    "== Background ==\nThe single's release "
                                    "was delayed.\n"
                                ),
                            }
                        ]
                    }
                },
            )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    assert lookup_wikipedia(
        "Fallin'", "Release", client, sleep=lambda _: None
    ) is None


def test_lookup_rejects_album_pages():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"query": {"search": [{"title": "Blue in Green (album)"}]}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    assert lookup_wikipedia(
        "Blue in Green", "Miles Davis", client, sleep=lambda _: None
    ) is None


def test_lookup_raises_on_an_api_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"error": {"code": "bad", "info": "nope"}}
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(ProviderError):
        lookup_wikipedia(
            "Blue in Green", "Miles Davis", client, sleep=lambda _: None
        )


def test_lookup_keeps_the_story_when_chart_wikitext_fails():
    data = lookup_wikipedia(
        "Blue in Green",
        "Miles Davis",
        _client(wikitext_status=503),
        sleep=lambda _: None,
    )

    assert data is not None
    assert data.story
    assert data.charts == []


def test_lookup_skips_a_same_named_episode():
    extracts = {
        "House of the Rising Sun (Lost)": (
            '"House of the Rising Sun" is the sixth episode of Lost.\n'
        ),
        "The House of the Rising Sun": (
            '"The House of the Rising Sun" is a traditional folk song. '
            "The Animals recorded the best-known version in 1964.\n\n"
            "== Background ==\nThe song travelled from England to America.\n"
        ),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("list") == "search":
            return httpx.Response(
                200,
                json={
                    "query": {
                        "search": [
                            {"title": "House of the Rising Sun (Lost)"},
                            {"title": "The House of the Rising Sun"},
                        ]
                    }
                },
            )
        if params.get("action") == "query":
            title = params.get("titles")
            return httpx.Response(
                200,
                json={
                    "query": {
                        "pages": [
                            {
                                "title": title,
                                "fullurl": "https://en.wikipedia.org/wiki/"
                                + str(title).replace(" ", "_"),
                                "extract": extracts[title],
                            }
                        ]
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "parse": {
                    "wikitext": (
                        "== Charts ==\n"
                        "{{single chart|Billboardhot100|22|"
                        "artist=The Animals}}"
                    )
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    data = lookup_wikipedia(
        "House of the Rising Sun", "The Animals", client, sleep=lambda _: None
    )

    assert data is not None
    assert data.title == "The House of the Rising Sun"
    assert data.confidence == "fuzzy"
    assert data.charts[0].peak == 22


def test_lookup_keeps_a_leading_parenthetical_title():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("list") == "search":
            seen.append(params.get("srsearch") or "")
            return httpx.Response(
                200,
                json={
                    "query": {
                        "search": [
                            {"title": "(I Can't Get No) Satisfaction"}
                        ]
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "query": {
                    "pages": [
                        {
                            "title": "(I Can't Get No) Satisfaction",
                            "fullurl": "https://en.wikipedia.org/wiki/"
                            "(I_Can%27t_Get_No)_Satisfaction",
                            "extract": (
                                '"(I Can\'t Get No) Satisfaction" is a song '
                                "by the Rolling Stones.\n"
                            ),
                        }
                    ]
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    data = lookup_wikipedia(
        "(I Can't Get No) Satisfaction (Mono)",
        "The Rolling Stones",
        client,
        sleep=lambda _: None,
    )

    assert data is not None
    assert seen and "Satisfaction" in seen[0]
    assert "I Can" in seen[0]


def test_lookup_accepts_a_band_credit_without_its_backing_band():
    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("list") == "search":
            return httpx.Response(
                200,
                json={
                    "query": {
                        "search": [{"title": "I Love Rock 'n' Roll"}]
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "query": {
                    "pages": [
                        {
                            "title": "I Love Rock 'n' Roll",
                            "fullurl": "https://en.wikipedia.org/wiki/"
                            "I_Love_Rock_%27n%27_Roll",
                            "extract": (
                                '"I Love Rock \'n\' Roll" is a rock song '
                                "covered by Joan Jett in 1981.\n"
                            ),
                        }
                    ]
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    data = lookup_wikipedia(
        "I Love Rock 'N Roll",
        "Joan Jett & The Blackhearts",
        client,
        sleep=lambda _: None,
    )

    assert data is not None
    assert data.confidence == "exact"


def test_key_ratio_treats_ampersand_as_and():
    from app.matching import key_ratio

    assert key_ratio("When Love And Hate Collide", "When Love & Hate Collide") == 1.0


def test_parse_charts_skips_decade_and_all_time_sections():
    charts = parse_charts(WIKITEXT, PAGE_URL)

    assert [(entry.chart_name, entry.peak) for entry in charts] == [
        ("Billboard Hot 100", 3),
        ("UK Singles (OCC)", 12),
    ]
    assert all(entry.source_url == PAGE_URL for entry in charts)


def test_parse_charts_reads_plain_wikitables():
    charts = parse_charts(WIKITABLE, PAGE_URL)

    pairs = _chart_pairs(charts)
    assert ("Billboard Hot 100", 1) in pairs
    assert ("UK Singles (OCC)", 7) in pairs
    assert ("Argentina (CAPIF)", 8) in pairs
    assert ("Austria (Ö3)", 4) in pairs
    assert ("Ireland (IRMA)", 5) in pairs
    assert ("Billboard Hot 100", 6) not in pairs

    south_africa = next(
        entry for entry in charts if entry.chart_name.startswith("South Africa")
    )
    assert south_africa.country == "ZA"

    hot = next(entry for entry in charts if entry.chart_name == "Billboard Hot 100")
    assert hot.country == "US"
    assert hot.year == 1984
    assert hot.source_url == PAGE_URL

    austria = next(
        entry for entry in charts if entry.chart_name == "Austria (Ö3)"
    )
    assert austria.year == 1984


def test_parse_charts_ignores_live_version_chart_tables():
    wikitext = """
== Charts ==
=== Weekly charts ===
{|
|-
|US ''Billboard'' Hot 100
|1
|}
== Live version ==
=== Weekly chart performance ===
{|
|-
|UK Singles (OCC)
|26
|}
{{single chart|Switzerland|36|artist=Van Halen}}
"""

    pairs = _chart_pairs(parse_charts(wikitext))

    assert ("Billboard Hot 100", 1) in pairs
    assert ("UK Singles (OCC)", 26) not in pairs
    assert ("Switzerland (Schweizer Hitparade)", 36) not in pairs


def test_parse_charts_ignores_tables_outside_chart_sections():
    wikitext = """
== Personnel ==
{| class="wikitable"
|-
|Guitar
|1
|}
"""

    assert parse_charts(wikitext) == []


def test_parse_charts_names_unmapped_billboard_charts():
    wikitext = """
== Charts ==
{{single chart|Billboardmainstreamrock|11|artist=Poison}}
{{single chart|Billboarddigitalsongs|16|artist=Poison}}
{{single chart|Billboardcanadachrtop40|9|artist=Poison}}
"""

    charts = parse_charts(wikitext)

    assert [(entry.chart_name, entry.country) for entry in charts] == [
        ("Billboard Canada CHR/Top 40", "CA"),
        ("Billboard Digital Song Sales", "US"),
        ("Billboard Mainstream Rock", "US"),
    ]


# --- pipeline --------------------------------------------------------------


def _engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/story.db",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        genre = Genre(name="Jazz", slug="jazz", is_default=True)
        session.add(genre)
        session.commit()
        session.refresh(genre)
        playlist = Playlist(genre_id=genre.id, youtube_playlist_id="PL1")
        session.add(playlist)
        session.commit()
        session.refresh(playlist)
        session.add(
            TrackCache(
                playlist_id=playlist.id,
                youtube_video_id="v1",
                title="Blue in Green (Remaster)",
                artist="Miles Davis",
                thumbnail_url="",
                duration_seconds=337,
                position=0,
            )
        )
        session.commit()
    return engine


def test_enrich_story_fills_text_link_and_charts(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        outcome = enrich_story(
            session, "v1", client=object(), wikipedia=lambda *_: _wiki()
        )
        row = session.get(TrackDetail, "v1")
        charts = session.exec(select(TrackChartEntry)).all()

    assert outcome.committed is True
    assert outcome.has_story is True
    assert outcome.charts == 1
    assert row is not None
    assert row.summary.startswith('"Blue in Green"')
    assert "Bill Evans" in row.story
    assert row.story_at is not None
    assert row.story_error is None
    assert row.sources["summary"]["provider"] == "wikipedia"
    assert row.sources["story"]["url"] == PAGE_URL
    assert row.sources["charts"]["provider"] == "wikipedia"
    assert [(link["label"], link["url"]) for link in row.links] == [
        ("Wikipedia", PAGE_URL)
    ]
    assert [(chart.chart_name, chart.peak) for chart in charts] == [
        ("Billboard Hot 100", 3)
    ]
    assert charts[0].source_url == PAGE_URL


def test_story_merge_respects_locks(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        session.add(
            TrackDetail(
                youtube_video_id="v1",
                summary="Manual summary",
                locked_fields=["summary"],
            )
        )
        session.commit()

        enrich_story(
            session, "v1", client=object(), wikipedia=lambda *_: _wiki()
        )
        row = session.get(TrackDetail, "v1")

    assert row.summary == "Manual summary"
    assert row.story
    assert "summary" not in row.sources


def test_story_force_refreshes_auto_text_but_not_manual_text(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        session.add(
            TrackDetail(
                youtube_video_id="v1",
                summary="Old auto summary",
                story="Manual story",
                sources={
                    "summary": {
                        "provider": "wikipedia",
                        "url": "https://old",
                        "fetched_at": "2020-01-01",
                    }
                },
            )
        )
        session.commit()

        enrich_story(
            session,
            "v1",
            force=True,
            client=object(),
            wikipedia=lambda *_: _wiki(),
        )
        row = session.get(TrackDetail, "v1")

    assert row.summary.startswith('"Blue in Green"')
    assert row.story == "Manual story"


def test_story_force_replaces_auto_charts_but_keeps_manual_charts(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        session.add(
            TrackDetail(
                youtube_video_id="v1",
                sources={
                    "charts": {
                        "provider": "wikipedia",
                        "url": "https://old",
                        "fetched_at": "2020-01-01",
                    }
                },
            )
        )
        session.add(
            TrackChartEntry(
                youtube_video_id="v1",
                chart_name="Old Chart",
                peak=9,
            )
        )
        session.commit()

        enrich_story(
            session,
            "v1",
            force=True,
            client=object(),
            wikipedia=lambda *_: _wiki(),
        )
        charts = session.exec(select(TrackChartEntry)).all()

    assert [(chart.chart_name, chart.peak) for chart in charts] == [
        ("Billboard Hot 100", 3)
    ]


def test_story_does_not_replace_manual_charts(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        session.add(TrackChartEntry(youtube_video_id="v1", chart_name="My Chart", peak=7))
        session.commit()

        enrich_story(
            session,
            "v1",
            force=True,
            client=object(),
            wikipedia=lambda *_: _wiki(),
        )
        charts = session.exec(select(TrackChartEntry)).all()

    assert [(chart.chart_name, chart.peak) for chart in charts] == [
        ("My Chart", 7)
    ]


def test_studio_save_marks_charts_as_curated(tmp_path):
    from app.schemas import ChartEntryIn, TrackDetailIn
    from app.track_details import save_detail

    engine = _engine(tmp_path)
    with Session(engine) as session:
        session.add(
            TrackDetail(
                youtube_video_id="v1",
                sources={
                    "charts": {
                        "provider": "wikipedia",
                        "url": "https://old",
                        "fetched_at": "2020-01-01",
                    }
                },
            )
        )
        session.commit()

        save_detail(
            session,
            "v1",
            TrackDetailIn(
                charts=[
                    ChartEntryIn(chart_name="Edited chart", peak=4)
                ]
            ),
        )

        row = session.get(TrackDetail, "v1")

    assert "charts" not in row.sources


def test_story_provider_error_leaves_the_track_pending(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        outcome = enrich_story(
            session,
            "v1",
            client=object(),
            wikipedia=lambda *_: (_ for _ in ()).throw(ProviderError("down")),
        )
        row = session.get(TrackDetail, "v1")

    assert outcome.committed is False
    assert outcome.errors
    assert row is not None
    assert row.story_at is None
    assert "down" in row.story_error


def test_story_miss_is_remembered(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        outcome = enrich_story(
            session, "v1", client=object(), wikipedia=lambda *_: None
        )
        row = session.get(TrackDetail, "v1")

    assert outcome.committed is True
    assert outcome.has_story is False
    assert row is not None
    assert row.story_at is not None
    assert row.story_error is None


def test_enrich_stories_pending_skips_known_stories(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        playlist = session.exec(select(Playlist)).first()
        session.add(
            TrackCache(
                playlist_id=playlist.id,
                youtube_video_id="v2",
                title="So What",
                artist="Miles Davis",
                thumbnail_url="",
                duration_seconds=545,
                position=1,
            )
        )
        session.add(
            TrackDetail(
                youtube_video_id="v1",
                story="Already here",
                story_at=datetime(2026, 10, 26),
            )
        )
        session.commit()

    calls: list[str] = []

    def fake(_title, artist, _client):
        calls.append(artist)
        return _wiki()

    processed = enrich_stories_pending(
        lambda: Session(engine),
        object(),
        wikipedia=fake,
        pause_seconds=0,
        sleep=lambda _: None,
    )

    assert processed == 1
    assert calls == ["Miles Davis"]
    with Session(engine) as session:
        assert session.get(TrackDetail, "v2").story_at is not None


def test_progress_counts_stories(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        session.add(
            TrackDetail(
                youtube_video_id="v1",
                story="A story",
                story_at=datetime(2026, 10, 26),
            )
        )
        session.commit()
        counts = progress(session)

    assert counts["stories"] == 1
    assert counts["stories_failed"] == 0


# --- API -------------------------------------------------------------------


def _api_client(tmp_path):
    from fastapi.testclient import TestClient

    from app.db import get_session
    from app.main import create_app
    from app import enrichment

    engine = create_engine(
        f"sqlite:///{tmp_path}/story-api.db",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        genre = Genre(name="Jazz", slug="jazz", is_default=True)
        session.add(genre)
        session.commit()
        session.refresh(genre)
        playlist = Playlist(genre_id=genre.id, youtube_playlist_id="PL1")
        session.add(playlist)
        session.commit()
        session.refresh(playlist)
        session.add(
            TrackCache(
                playlist_id=playlist.id,
                youtube_video_id="v1",
                title="Blue in Green",
                artist="Miles Davis",
                thumbnail_url="",
                duration_seconds=337,
                position=0,
            )
        )
        session.add(
            TrackDetail(
                youtube_video_id="v1",
                album="Kind of Blue",
                enriched_at=datetime(2026, 10, 26),
            )
        )
        session.commit()

    def override():
        with Session(engine) as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override
    client = TestClient(app)
    client.post("/api/studio/login", json={"password": "test-pass"})
    return client, enrichment, engine


def test_studio_fetch_includes_the_story(tmp_path, monkeypatch):
    client, enrichment, _ = _api_client(tmp_path)
    monkeypatch.setattr(
        enrichment.pipeline, "lookup_wikipedia", lambda *_: _wiki()
    )
    monkeypatch.setattr(enrichment.pipeline, "lookup_deezer", lambda *_: None)
    monkeypatch.setattr(
        enrichment.pipeline, "lookup_musicbrainz", lambda *_: None
    )

    resp = client.post("/api/studio/tracks/v1/enrich")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["story"].startswith("Davis composed")
    assert body["story_at"] is not None
    assert body["charts"][0]["chart_name"] == "Billboard Hot 100"
    public = client.get("/api/tracks/v1")
    assert public.status_code == 200
    assert public.json()["charts"][0]["peak"] == 3
    library = client.get("/api/studio/tracks").json()["items"][0]
    assert library["has_story"] is True


def test_enrichment_status_reports_story_progress(tmp_path):
    client, _, engine = _api_client(tmp_path)
    with Session(engine) as session:
        row = session.get(TrackDetail, "v1")
        row.story = "A story"
        row.story_at = datetime(2026, 10, 26)
        session.add(row)
        session.commit()

    body = client.get("/api/studio/tracks/enrich/status").json()

    assert body["total"] == 1
    assert body["stories"] == 1
    assert body["stories_failed"] == 0
