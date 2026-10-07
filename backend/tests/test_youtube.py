import pytest

from app.youtube import (
    PlaylistData,
    _channel_lookup_param,
    fetch_channel_playlists,
    fetch_playlist_items,
    parse_playlist_id,
    resolve_channel_id,
)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("PL123abc", "PL123abc"),
        ("https://www.youtube.com/playlist?list=PL123abc", "PL123abc"),
        ("https://music.youtube.com/playlist?list=OLAK5uy_xyz&si=1", "OLAK5uy_xyz"),
        ("https://youtu.be/abc?list=PL999", "PL999"),
    ],
)
def test_parse_playlist_id(value, expected):
    assert parse_playlist_id(value) == expected


def test_parse_playlist_id_rejects_empty():
    with pytest.raises(ValueError):
        parse_playlist_id("https://www.youtube.com/watch?v=abc")


def test_fetch_playlist_items_parses_response():
    payload = {
        "items": [
            {
                "snippet": {
                    "title": "Song A",
                    "videoOwnerChannelTitle": "Artist A",
                    "position": 0,
                    "resourceId": {"videoId": "vidA"},
                    "thumbnails": {"high": {"url": "https://img/a.jpg"}},
                },
                "contentDetails": {"videoPublishedAt": "2020-01-01T00:00:00Z"},
            }
        ]
    }

    class FakeClient:
        def get(self, url, params=None):
            class R:
                def raise_for_status(self):
                    return None

                def json(self_inner):
                    return payload

            return R()

    tracks = fetch_playlist_items("PL1", "key", FakeClient())
    assert tracks[0].youtube_video_id == "vidA"
    assert tracks[0].title == "Song A"
    assert tracks[0].artist == "Artist A"
    assert tracks[0].position == 0


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Chiqui Pineda - Topic", "Chiqui Pineda"),
        ("Chiqui Pineda - topic", "Chiqui Pineda"),
        ("Chiqui Pineda-Topic", "Chiqui Pineda"),
        ("Artist A", "Artist A"),
        ("Some Band - Topic ", "Some Band"),
    ],
)
def test_fetch_playlist_items_strips_topic_suffix(raw, expected):
    payload = {
        "items": [
            {
                "snippet": {
                    "title": "Song A",
                    "videoOwnerChannelTitle": raw,
                    "position": 0,
                    "resourceId": {"videoId": "vidA"},
                }
            }
        ]
    }

    class FakeClient:
        def get(self, url, params=None):
            class R:
                def raise_for_status(self):
                    return None

                def json(self_inner):
                    return payload

            return R()

    tracks = fetch_playlist_items("PL1", "key", FakeClient())
    assert tracks[0].artist == expected


def test_fetch_follows_pagination():
    page1 = {
        "items": [
            {"snippet": {"title": "One", "position": 0,
                         "resourceId": {"videoId": "v1"},
                         "thumbnails": {"high": {"url": "u1"}}}}
        ],
        "nextPageToken": "TOKEN2",
    }
    page2 = {
        "items": [
            {"snippet": {"title": "Two", "position": 1,
                         "resourceId": {"videoId": "v2"},
                         "thumbnails": {"high": {"url": "u2"}}}}
        ],
    }
    pages = [page1, page2]
    seen_params = []

    class FakeClient:
        def get(self, url, params=None):
            seen_params.append(params)
            payload = pages.pop(0)

            class R:
                def raise_for_status(self):
                    return None

                def json(self_inner):
                    return payload

            return R()

    tracks = fetch_playlist_items("PL1", "key", FakeClient())
    assert [t.youtube_video_id for t in tracks] == ["v1", "v2"]
    assert seen_params[0].get("pageToken") is None
    assert seen_params[1].get("pageToken") == "TOKEN2"


def test_fetch_skips_items_without_video_id():
    payload = {
        "items": [
            {"snippet": {"title": "Bad", "resourceId": {}}},
            {"snippet": {"title": "Good", "resourceId": {"videoId": "vid"}}},
        ]
    }

    class FakeClient:
        def get(self, url, params=None):
            class R:
                def raise_for_status(self):
                    return None

                def json(self_inner):
                    return payload

            return R()

    tracks = fetch_playlist_items("PL1", "key", FakeClient())
    assert [t.youtube_video_id for t in tracks] == ["vid"]


class _ChannelClient:
    def __init__(self, payload):
        self.payload = payload
        self.seen_params = None

    def get(self, url, params=None):
        self.seen_params = params
        payload = self.payload

        class R:
            def raise_for_status(self):
                return None

            def json(self_inner):
                return payload

        return R()


@pytest.mark.parametrize(
    "value,param_key,param_value",
    [
        ("UCabc123", "id", "UCabc123"),
        ("@somehandle", "forHandle", "@somehandle"),
        ("https://www.youtube.com/@somehandle", "forHandle", "@somehandle"),
        ("https://www.youtube.com/channel/UCxyz", "id", "UCxyz"),
        ("https://www.youtube.com/user/legacyuser", "forUsername", "legacyuser"),
    ],
)
def test_resolve_channel_id_lookup_param(value, param_key, param_value):
    payload = {"items": [{"id": "UCresolved", "snippet": {"title": "My Channel"}}]}
    client = _ChannelClient(payload)
    channel_id, title = resolve_channel_id(value, "key", client)
    assert channel_id == "UCresolved"
    assert title == "My Channel"
    assert client.seen_params[param_key] == param_value


@pytest.mark.parametrize(
    "value,expected",
    [
        ("https://www.youtube.com/@handle/videos", {"forHandle": "@handle"}),
        ("https://youtube.com/channel/UC1/playlists", {"id": "UC1"}),
        ("https://music.youtube.com/@x", {"forHandle": "@x"}),
    ],
)
def test_channel_lookup_param_edge_cases(value, expected):
    assert _channel_lookup_param(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "https://youtube.com.evil.com/@x",
        "https://www.youtube.com/",
    ],
)
def test_channel_lookup_param_invalid_urls(value):
    with pytest.raises(ValueError):
        _channel_lookup_param(value)


def test_resolve_channel_id_empty_raises():
    with pytest.raises(ValueError):
        _channel_lookup_param("   ")


def test_resolve_channel_id_not_found_raises():
    with pytest.raises(ValueError):
        resolve_channel_id("UCnope", "key", _ChannelClient({"items": []}))


def test_resolve_channel_id_rejects_non_youtube_url():
    with pytest.raises(ValueError):
        _channel_lookup_param("https://example.com/@foo")


def test_fetch_channel_playlists_parses_response():
    payload = {
        "items": [
            {
                "id": "PLaaa",
                "snippet": {
                    "title": "Chill Mix",
                    "thumbnails": {"high": {"url": "https://img/a.jpg"}},
                },
                "contentDetails": {"itemCount": 12},
            }
        ]
    }

    class FakeClient:
        def get(self, url, params=None):
            class R:
                def raise_for_status(self):
                    return None

                def json(self_inner):
                    return payload

            return R()

    result = fetch_channel_playlists("UC1", "key", FakeClient())
    assert result == [
        PlaylistData(
            youtube_playlist_id="PLaaa",
            title="Chill Mix",
            item_count=12,
            thumbnail_url="https://img/a.jpg",
        )
    ]


def test_fetch_channel_playlists_follows_pagination():
    page1 = {
        "items": [
            {
                "id": "PL1",
                "snippet": {"title": "One", "thumbnails": {}},
                "contentDetails": {"itemCount": 1},
            }
        ],
        "nextPageToken": "TOKEN2",
    }
    page2 = {
        "items": [
            {
                "id": "PL2",
                "snippet": {"title": "Two", "thumbnails": {}},
                "contentDetails": {"itemCount": 2},
            }
        ],
    }
    pages = [page1, page2]
    seen = []

    class FakeClient:
        def get(self, url, params=None):
            seen.append(params)
            payload = pages.pop(0)

            class R:
                def raise_for_status(self):
                    return None

                def json(self_inner):
                    return payload

            return R()

    result = fetch_channel_playlists("UC1", "key", FakeClient())
    assert [p.youtube_playlist_id for p in result] == ["PL1", "PL2"]
    assert seen[0].get("pageToken") is None
    assert seen[1].get("pageToken") == "TOKEN2"


def test_fetch_channel_playlists_handles_missing_fields():
    payload = {
        "items": [
            {"id": "PL1", "snippet": {"title": "No details"}},
            {"snippet": {"title": "No id"}},
        ]
    }

    class FakeClient:
        def get(self, url, params=None):
            class R:
                def raise_for_status(self):
                    return None

                def json(self_inner):
                    return payload

            return R()

    result = fetch_channel_playlists("UC1", "key", FakeClient())
    assert result == [
        PlaylistData(
            youtube_playlist_id="PL1",
            title="No details",
            item_count=0,
            thumbnail_url="",
        )
    ]


def test_fetch_channel_playlists_thumbnail_fallback_and_bad_count():
    payload = {
        "items": [
            {
                "id": "PL1",
                "snippet": {"title": "T", "thumbnails": {"medium": {"url": "m.jpg"}}},
                "contentDetails": {"itemCount": "7"},
            },
            {
                "id": "PL2",
                "snippet": {"title": "T2", "thumbnails": None},
                "contentDetails": {"itemCount": "not-a-number"},
            },
        ]
    }

    class FakeClient:
        def get(self, url, params=None):
            class R:
                def raise_for_status(self):
                    return None

                def json(self_inner):
                    return payload

            return R()

    result = fetch_channel_playlists("UC1", "key", FakeClient())
    assert result[0].thumbnail_url == "m.jpg"
    assert result[0].item_count == 7
    assert result[1].thumbnail_url == ""
    assert result[1].item_count == 0


def test_fetch_channel_playlists_empty_items():
    payload = {"items": []}

    class FakeClient:
        def get(self, url, params=None):
            class R:
                def raise_for_status(self):
                    return None

                def json(self_inner):
                    return payload

            return R()

    assert fetch_channel_playlists("UC1", "key", FakeClient()) == []


    assert fetch_channel_playlists("UC1", "key", FakeClient()) == []


def test_parse_iso_duration():
    from app.youtube import _parse_iso_duration

    assert _parse_iso_duration("PT3M45S") == 225
    assert _parse_iso_duration("PT1H2M3S") == 3723
    assert _parse_iso_duration("PT45S") == 45
    assert _parse_iso_duration("P0D") == 0
    assert _parse_iso_duration("") == 0
    assert _parse_iso_duration("garbage") == 0


def test_fetch_video_durations_parses():
    from app.youtube import fetch_video_durations

    calls = []

    class FakeClient:
        def get(self, url, params=None):
            calls.append(params)
            ids = params["id"].split(",")

            class R:
                def raise_for_status(self):
                    return None

                def json(self_inner):
                    return {
                        "items": [
                            {"id": v, "contentDetails": {"duration": "PT2M"}}
                            for v in ids
                        ]
                    }

            return R()

    durations = fetch_video_durations(["a", "b"], "key", FakeClient())
    assert durations == {"a": 120, "b": 120}
    assert calls[0]["id"] == "a,b"


def test_fetch_video_durations_chunks_batches():
    from app.youtube import fetch_video_durations

    seen = []

    class FakeClient:
        def get(self, url, params=None):
            seen.append(params["id"])
            ids = params["id"].split(",")

            class R:
                def raise_for_status(self):
                    return None

                def json(self_inner):
                    return {
                        "items": [
                            {"id": v, "contentDetails": {"duration": "PT1S"}}
                            for v in ids
                        ]
                    }

            return R()

    ids = [f"v{i}" for i in range(120)]
    durations = fetch_video_durations(ids, "key", FakeClient())
    assert len(durations) == 120
    assert len(seen) == 3
    assert len(seen[0].split(",")) == 50
