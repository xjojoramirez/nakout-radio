import base64
import hashlib
import hmac


def _sign(secret: str, payload: str) -> str:
    return hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def encode_cursor(secret: str, slug: str, position: int) -> str:
    payload = f"{slug}:{position}"
    signature = _sign(secret, payload)
    raw = f"{payload}:{signature}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(secret: str, token: str) -> tuple[str, int] | None:
    if not token or len(token) > 4096:
        return None
    try:
        raw = base64.b64decode(
            token.encode("ascii"), altchars=b"-_", validate=True
        ).decode("utf-8")
    except Exception:
        return None
    parts = raw.rsplit(":", 2)
    if len(parts) != 3:
        return None
    slug, position_text, signature = parts
    expected = _sign(secret, f"{slug}:{position_text}")
    if not hmac.compare_digest(signature.encode("utf-8"), expected.encode("ascii")):
        return None
    try:
        position = int(position_text)
    except ValueError:
        return None
    return slug, position
