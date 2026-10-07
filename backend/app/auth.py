import hmac
from datetime import datetime, timedelta, timezone

import jwt

_ALGORITHM = "HS256"
COOKIE_NAME = "nakout_session"
_TTL_HOURS = 24


def verify_password(candidate: str, expected: str) -> bool:
    if not candidate or not expected:
        return False
    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


def create_session_token(secret_key: str) -> str:
    payload = {
        "sub": "admin",
        "exp": datetime.now(timezone.utc) + timedelta(hours=_TTL_HOURS),
    }
    return jwt.encode(payload, secret_key, algorithm=_ALGORITHM)


def verify_session_token(token: str, secret_key: str) -> bool:
    try:
        payload = jwt.decode(token, secret_key, algorithms=[_ALGORITHM])
    except jwt.PyJWTError:
        return False
    return payload.get("sub") == "admin"
