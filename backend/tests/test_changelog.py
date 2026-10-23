from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.changelog import parse_changelog
from app.db import get_session
from app.main import create_app
from app.routers import admin

def _many_entries(count: int = 12) -> str:
    return "\n\n".join(
        f"## 2026-01-{day:02d} — Entry {day}\n\nSummary {day}."
        for day in range(1, count + 1)
    )


SAMPLE = """# Changelog

Intro paragraph that must be ignored.

## 2026-10-23 — stay paused in the background

On a phone, a tuned-in listener had `audio` stop when the video started.

- Files touched:
  - `frontend/src/hooks/useYouTubePlayer.ts`

## 2026-10-22 — second change

**Bold** first paragraph with a [link](https://example.com) and *emphasis*.

Second paragraph.
"""


def test_parses_date_title_and_first_paragraph():
    entries = parse_changelog(SAMPLE)

    assert len(entries) == 2
    assert entries[0].date == "2026-10-23"
    assert entries[0].title == "stay paused in the background"
    assert (
        entries[0].summary
        == "On a phone, a tuned-in listener had audio stop when the video started."
    )
    assert entries[1].summary == "Bold first paragraph with a link and emphasis."


def test_respects_limit():
    entries = parse_changelog(SAMPLE, limit=1)

    assert len(entries) == 1
    assert entries[0].date == "2026-10-23"


def test_default_limit_is_ten():
    entries = parse_changelog(_many_entries())

    assert len(entries) == 10
    assert entries[0].title == "Entry 1"
    assert entries[-1].title == "Entry 10"


def test_skips_malformed_headings_and_keeps_entries_without_a_summary():
    text = (
        "## not a date\n\nBody\n\n"
        "## 2026-01-01 — No body\n\n"
        "## 2026-01-02 — Has body\n\nHello.\n"
    )

    entries = parse_changelog(text)

    assert [(entry.date, entry.title) for entry in entries] == [
        ("2026-01-01", "No body"),
        ("2026-01-02", "Has body"),
    ]
    assert entries[0].summary == ""
    assert entries[1].summary == "Hello."


def test_strips_inline_markdown_from_titles():
    entries = parse_changelog("## 2026-01-01 — Fix `www.nakout.com`\n\nBody.")

    assert entries[0].title == "Fix www.nakout.com"


def test_does_not_use_a_file_list_as_the_summary():
    text = "## 2026-01-01 — Only files\n\n- Files touched:\n  - `a.ts`\n"

    entries = parse_changelog(text)

    assert entries[0].summary == ""


def test_handles_windows_line_endings():
    entries = parse_changelog(SAMPLE.replace("\n", "\r\n"))

    assert entries[0].date == "2026-10-23"
    assert entries[0].summary.startswith("On a phone")


def test_curated_studio_feed_has_no_internal_technical_markers():
    feed = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "studio"
        / "changelog.md"
    ).read_text(encoding="utf-8").lower()

    for marker in (
        "docker",
        "caddy",
        "tls",
        "sqlite",
        "migration",
        "issue #",
        "/app/",
        "http://",
        "https://",
    ):
        assert marker not in feed


def _client(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/t.db",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    def override():
        with Session(engine) as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override
    return TestClient(app), engine


def _login(client: TestClient) -> None:
    assert (
        client.post(
            "/api/studio/login", json={"password": "test-pass"}
        ).status_code
        == 200
    )


def test_changelog_requires_auth(tmp_path):
    client, _ = _client(tmp_path)

    assert client.get("/api/studio/changelog").status_code == 401


def test_changelog_returns_entries(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    _login(client)
    changelog = tmp_path / "changelog.md"
    changelog.write_text(SAMPLE, encoding="utf-8")
    monkeypatch.setattr(
        admin,
        "get_settings",
        lambda: SimpleNamespace(
            secret_key="test-secret", changelog_path=str(changelog)
        ),
    )

    resp = client.get("/api/studio/changelog?limit=1")

    assert resp.status_code == 200
    assert resp.json() == [
        {
            "date": "2026-10-23",
            "title": "stay paused in the background",
            "summary": (
                "On a phone, a tuned-in listener had audio stop when the "
                "video started."
            ),
        }
    ]


def test_changelog_defaults_to_ten_entries(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    _login(client)
    changelog = tmp_path / "changelog.md"
    changelog.write_text(_many_entries(), encoding="utf-8")
    monkeypatch.setattr(
        admin,
        "get_settings",
        lambda: SimpleNamespace(
            secret_key="test-secret", changelog_path=str(changelog)
        ),
    )

    resp = client.get("/api/studio/changelog")

    assert resp.status_code == 200
    assert len(resp.json()) == 10


def test_changelog_returns_503_when_file_is_missing(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    _login(client)
    monkeypatch.setattr(
        admin,
        "get_settings",
        lambda: SimpleNamespace(
            secret_key="test-secret",
            changelog_path=str(tmp_path / "missing.md"),
        ),
    )

    resp = client.get("/api/studio/changelog")

    assert resp.status_code == 503
    assert resp.json()["detail"] == "Changelog unavailable"


def test_changelog_rejects_invalid_limit(tmp_path):
    client, _ = _client(tmp_path)
    _login(client)

    assert client.get("/api/studio/changelog?limit=0").status_code == 422
    assert client.get("/api/studio/changelog?limit=51").status_code == 422
