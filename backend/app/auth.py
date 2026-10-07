import hmac
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import delete
from sqlmodel import Session

from app.models import RevokedSession

_ALGORITHM = "HS256"
COOKIE_NAME = "nakout_session"
_TTL_HOURS = 24


def verify_password(candidate: str, expected: str) -> bool:
    if not candidate or not expected:
        return False
    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


def create_session_token(secret_key: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "admin",
        "iat": now,
        "jti": uuid.uuid4().hex,
        "exp": now + timedelta(hours=_TTL_HOURS),
    }
    return jwt.encode(payload, secret_key, algorithm=_ALGORITHM)


def decode_session_token(token: str, secret_key: str) -> dict | None:
    try:
        payload = jwt.decode(token, secret_key, algorithms=[_ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("sub") != "admin":
        return None
    return payload


def verify_session_token(token: str, secret_key: str) -> bool:
    return decode_session_token(token, secret_key) is not None


def _naive_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=None) if value.tzinfo else value


def revoke_session(session: Session, jti: str, expires_at: datetime) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    session.exec(delete(RevokedSession).where(RevokedSession.expires_at < now))
    session.merge(RevokedSession(jti=jti, expires_at=_naive_utc(expires_at)))
    session.commit()


def is_session_revoked(session: Session, jti: str) -> bool:
    return session.get(RevokedSession, jti) is not None
