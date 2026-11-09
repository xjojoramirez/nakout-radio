from datetime import datetime, timedelta, timezone

import jwt

from app.auth import (
    create_session_token,
    decode_session_token,
    verify_password,
    verify_session_token,
)

SECRET = "secret-key-0123456789abcdef0123456789"
OTHER = "other-key-0123456789abcdef0123456789"


def test_verify_password():
    assert verify_password("secret", "secret") is True
    assert verify_password("secret", "wrong") is False


def test_session_token_roundtrip():
    token = create_session_token(SECRET)
    assert verify_session_token(token, SECRET) is True


def test_session_token_has_unique_jti():
    first = decode_session_token(create_session_token(SECRET), SECRET)
    second = decode_session_token(create_session_token(SECRET), SECRET)
    assert first is not None and second is not None
    assert first["sub"] == "admin"
    assert first["jti"] and second["jti"]
    assert first["jti"] != second["jti"]


def test_decode_rejects_wrong_key():
    token = create_session_token(SECRET)
    assert decode_session_token(token, OTHER) is None


def test_session_token_rejects_tampering():
    token = create_session_token(SECRET)
    assert verify_session_token(token + "x", SECRET) is False


def test_verify_password_non_ascii_does_not_raise():
    assert verify_password("pä", "pä") is True
    assert verify_password("pä", "pa") is False


def test_verify_password_empty_is_false():
    assert verify_password("", "") is False
    assert verify_password(None, "x") is False


def test_session_token_expired_rejected():
    token = jwt.encode(
        {"sub": "admin", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
        SECRET,
        algorithm="HS256",
    )
    assert verify_session_token(token, SECRET) is False


def test_session_token_wrong_key_rejected():
    token = create_session_token(SECRET)
    assert verify_session_token(token, OTHER) is False


def test_session_token_wrong_subject_rejected():
    token = jwt.encode(
        {"sub": "user", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        SECRET,
        algorithm="HS256",
    )
    assert verify_session_token(token, SECRET) is False
