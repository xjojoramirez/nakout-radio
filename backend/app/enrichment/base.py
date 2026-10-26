"""Shared provider types and lock-aware merge rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PROVIDER_LABELS = {
    "deezer": "Deezer",
    "musicbrainz": "MusicBrainz",
}

USER_AGENT = "nakout-radio/1.0 (+https://github.com/xjojoramirez/nakout-radio)"


class ProviderError(RuntimeError):
    """A metadata provider returned an error or unusable data."""


@dataclass
class ProviderData:
    provider: str
    url: str
    confidence: Literal["exact", "fuzzy"] = "exact"
    fields: dict[str, Any] = field(default_factory=dict)


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict, tuple, set)):
        return not value
    return False


def year_from_date(value: str | None) -> int | None:
    if not value:
        return None
    head = value.strip()[:4]
    return int(head) if head.isdigit() else None


def apply_provider_data(
    row: Any,
    data: ProviderData,
    *,
    fetched_at: str,
    force: bool = False,
) -> int:
    """Fill empty, unlocked fields on ``row`` from ``data``.

    ``force`` also refreshes values that were previously auto-filled (they have
    a ``sources`` entry). Manually entered values have no source entry and a
    lock, so they survive both normal and forced runs.
    """
    sources = dict(row.sources or {})
    locked = set(row.locked_fields or [])
    applied = 0

    for field_name, value in data.fields.items():
        if field_name in locked or is_empty(value):
            continue
        current = getattr(row, field_name, None)
        if is_empty(current) or (force and field_name in sources):
            setattr(row, field_name, value)
            sources[field_name] = {
                "provider": data.provider,
                "url": data.url,
                "fetched_at": fetched_at,
            }
            applied += 1

    row.sources = sources
    return applied


def metadata_sources(row: Any) -> list[str]:
    """Provider display names for the fields currently shown, in priority order."""
    if row is None:
        return []
    providers: list[str] = []
    for source in (row.sources or {}).values():
        provider = source.get("provider") if isinstance(source, dict) else None
        if provider and provider not in providers:
            providers.append(provider)
    order = {"deezer": 0, "musicbrainz": 1}
    providers.sort(key=lambda name: (order.get(name, 99), name))
    return [PROVIDER_LABELS.get(name, name.title()) for name in providers]
