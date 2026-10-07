import threading
import time
from collections import defaultdict, deque

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 900

_lock = threading.Lock()
_failures: dict[str, deque[float]] = defaultdict(deque)


def _prune(key: str, now: float) -> deque[float]:
    attempts = _failures[key]
    cutoff = now - WINDOW_SECONDS
    while attempts and attempts[0] < cutoff:
        attempts.popleft()
    return attempts


def is_locked(key: str) -> bool:
    now = time.monotonic()
    with _lock:
        return len(_prune(key, now)) >= MAX_ATTEMPTS


def record_failure(key: str) -> None:
    now = time.monotonic()
    with _lock:
        _prune(key, now).append(now)


def reset(key: str) -> None:
    with _lock:
        _failures.pop(key, None)


def clear() -> None:
    with _lock:
        _failures.clear()
