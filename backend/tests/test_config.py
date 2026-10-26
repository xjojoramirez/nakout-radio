import pytest

from app.config import Settings


def test_settings_defaults():
    s = Settings(_env_file=None)
    assert s.genre_tz == "Asia/Manila"
    assert s.cache_ttl_minutes == 60
    assert s.database_url.startswith("sqlite")


def test_loudness_target_default(monkeypatch):
    monkeypatch.delenv("LOUDNESS_TARGET_DB", raising=False)
    assert Settings(_env_file=None).loudness_target_db == -9.0


def test_changelog_path_points_at_the_curated_studio_feed():
    path = Settings(_env_file=None).changelog_path.replace("\\", "/")

    assert path.endswith("docs/studio/changelog.md")


def test_missing_secret_raises(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("YT_API_KEY", raising=False)
    try:
        Settings(_env_file=None)
    except Exception as exc:
        assert "secret_key" in str(exc).lower() or "admin_password" in str(exc).lower()
    else:
        raise AssertionError("Settings should reject empty required config")


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_track_gap_default(monkeypatch):
    monkeypatch.delenv("TRACK_GAP_SECONDS", raising=False)
    assert Settings(_env_file=None).track_gap_seconds == 2.0


def test_track_gap_rejects_out_of_range():
    with pytest.raises(Exception):
        Settings(_env_file=None, track_gap_seconds=-1)
    with pytest.raises(Exception):
        Settings(_env_file=None, track_gap_seconds=31)


def test_track_gap_accepts_zero_and_fraction():
    assert Settings(_env_file=None, track_gap_seconds=0).track_gap_seconds == 0
    assert Settings(_env_file=None, track_gap_seconds=1.5).track_gap_seconds == 1.5


def test_preload_lead_default(monkeypatch):
    monkeypatch.delenv("PRELOAD_LEAD_SECONDS", raising=False)
    assert Settings(_env_file=None).preload_lead_seconds == 20.0


def test_preload_lead_rejects_out_of_range():
    with pytest.raises(Exception):
        Settings(_env_file=None, preload_lead_seconds=-1)
    with pytest.raises(Exception):
        Settings(_env_file=None, preload_lead_seconds=301)


def test_preload_lead_accepts_zero_and_fraction():
    assert Settings(_env_file=None, preload_lead_seconds=0).preload_lead_seconds == 0
    assert Settings(_env_file=None, preload_lead_seconds=12.5).preload_lead_seconds == 12.5


def test_enrichment_defaults(monkeypatch):
    monkeypatch.delenv("ENRICHMENT_ENABLED", raising=False)
    monkeypatch.delenv("ENRICHMENT_PAUSE_SECONDS", raising=False)
    monkeypatch.delenv("ENRICHMENT_MAX_CONSECUTIVE_ERRORS", raising=False)

    settings = Settings(_env_file=None)

    assert settings.enrichment_enabled is True
    assert settings.enrichment_pause_seconds == 0.5
    assert settings.enrichment_max_consecutive_errors == 5


def test_enrichment_settings_reject_out_of_range():
    with pytest.raises(Exception):
        Settings(_env_file=None, enrichment_pause_seconds=-1)
    with pytest.raises(Exception):
        Settings(_env_file=None, enrichment_pause_seconds=11)
    with pytest.raises(Exception):
        Settings(_env_file=None, enrichment_max_consecutive_errors=0)
    with pytest.raises(Exception):
        Settings(_env_file=None, enrichment_max_consecutive_errors=51)
