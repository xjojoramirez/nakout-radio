import jwt
from datetime import datetime, timedelta, timezone

from app.auth import create_session_token, verify_password, verify_session_token


def test_verify_password():
    assert verify_password("secret", "secret") is True
    assert verify_password("secret", "wrong") is False


def test_session_token_roundtrip():
    token = create_session_token("secret-key")
    assert verify_session_token(token, "secret-key") is True


def test_session_token_rejects_tampering():
    token = create_session_token("secret-key")
    assert verify_session_token(token + "x", "secret-key") is False


def test_verify_password_non_ascii_does_not_raise():
    assert verify_password("pä", "pä") is True
    assert verify_password("pä", "pa") is False


def test_verify_password_empty_is_false():
    assert verify_password("", "") is False
    assert verify_password(None, "x") is False


def test_session_token_expired_rejected():
    token = jwt.encode(
        {"sub": "admin", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
        "secret-key",
        algorithm="HS256",
    )
    assert verify_session_token(token, "secret-key") is False


def test_session_token_wrong_key_rejected():
    token = create_session_token("secret-key")
    assert verify_session_token(token, "other-key") is False


def test_session_token_wrong_subject_rejected():
    token = jwt.encode(
        {"sub": "user", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "secret-key",
        algorithm="HS256",
    )
    assert verify_session_token(token, "secret-key") is False
