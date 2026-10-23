import re
from dataclasses import dataclass
from pathlib import Path

_HEADING_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})\s*[—–-]\s*(?P<title>.+?)\s*$"
)
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_BULLET_RE = re.compile(r"^(?:[-*+]|\d+\.)\s+")

DEFAULT_LIMIT = 8


@dataclass(frozen=True)
class ChangelogEntry:
    date: str
    title: str
    summary: str


def load_changelog(
    path: Path, limit: int = DEFAULT_LIMIT
) -> list[ChangelogEntry]:
    return parse_changelog(path.read_text(encoding="utf-8"), limit)


def parse_changelog(text: str, limit: int = DEFAULT_LIMIT) -> list[ChangelogEntry]:
    """Return the newest changelog entries, newest first.

    ``docs/changelog.md`` is the source of truth. Each level-two heading must
    look like ``## YYYY-MM-DD — title``; the first prose paragraph underneath
    becomes the summary shown in the Studio dialog.
    """
    if limit <= 0:
        return []

    entries: list[ChangelogEntry] = []
    current: tuple[str, str] | None = None
    body: list[str] = []
    in_fence = False

    def flush() -> None:
        if current is None:
            return
        date, title = current
        entries.append(
            ChangelogEntry(
                date=date,
                title=title,
                summary=_first_paragraph(body),
            )
        )

    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence

        if not in_fence and line.startswith("## "):
            flush()
            body = []
            current = _parse_heading(line[3:])
            continue

        if current is not None:
            body.append(line)

    flush()
    return entries[:limit]


def _parse_heading(value: str) -> tuple[str, str] | None:
    match = _HEADING_RE.match(value.strip())
    if match is None:
        return None
    return match.group("date"), _plain_text(match.group("title"))


def _first_paragraph(lines: list[str]) -> str:
    block: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if block:
                return _plain_text(" ".join(block))
            continue
        block.append(stripped)

    return _plain_text(" ".join(block)) if block else ""


def _plain_text(value: str) -> str:
    value = _LINK_RE.sub(r"\1", value)
    value = value.replace("`", "")
    value = _BOLD_RE.sub(r"\1", value)
    value = _ITALIC_RE.sub(r"\1", value)
    value = re.sub(r"\s+", " ", value).strip()
    if _BULLET_RE.match(value):
        return ""
    return value
