import os

import pytest

os.environ.setdefault("YT_API_KEY", "test-key")
os.environ.setdefault("ADMIN_PASSWORD", "test-pass")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("COOKIE_SECURE", "false")
# Tests that exercise the schedule assume Manila local time (UTC+8). Override
# any ambient GENRE_TZ so the result does not depend on the developer's env.
os.environ["GENRE_TZ"] = "Asia/Manila"


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import create_app

    return TestClient(create_app())
