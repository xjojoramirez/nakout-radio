from app.config import Settings


def test_settings_defaults():
    s = Settings(_env_file=None)
    assert s.genre_tz == "Asia/Manila"
    assert s.cache_ttl_minutes == 60
    assert s.database_url.startswith("sqlite")


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
