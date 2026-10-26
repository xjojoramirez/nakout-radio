"""Wikipedia story and chart provider (keyless MediaWiki API).

Two things come out of one article: prose for the liner notes (the lead
paragraph as a summary, plus the background/composition sections as the story)
and chart placements parsed from the article's ``{{single chart}}`` templates.

Templates are read rather than rendered HTML because song articles put every
weekly, year-end and decade-end placement in separate sections; keeping the
heading context lets us drop the aggregate lists and keep real chart peaks.
"""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import quote

import httpx

from app.enrichment.base import ProviderError
from app.matching import clean_query, key_ratio

API_URL = "https://en.wikipedia.org/w/api.php"
PROVIDER = "wikipedia"

# MediaWiki has no hard request budget, but the API is shared infrastructure.
PAUSE_S = 0.8
SUMMARY_LIMIT = 900
STORY_LIMIT = 2400
MAX_CHARTS = 40
MIN_MATCH_RATIO = 0.6

_HEADING_RE = re.compile(r"^(={2,6})\s*(.+?)\s*\1\s*$")
_SINGLE_CHART_RE = re.compile(r"\{\{\s*single chart\s*\|([^}]*)\}\}", re.I)
_WORD_RE = re.compile(r"[a-z0-9]+")
_DISAMBIG_RE = re.compile(r"\s*\([^)]*\)\s*$")
_BAD_PAGE_RE = re.compile(
    r"\((?:album|ep|mixtape|compilation|soundtrack|film|musical)\)\s*$",
    re.I,
)
_LIST_PAGE_RE = re.compile(r"^(?:list of|discography)", re.I)
_BAD_CHART_SECTION_RE = re.compile(
    r"decade[- ]end|all[- ]time|year[- ]end|year end|"
    r"certification|sales|awards?|accolades?",
    re.I,
)

# section headings that carry the story, in order of preference
_STORY_GROUPS: tuple[tuple[str, ...], ...] = (
    (
        "background and composition",
        "background and development",
        "background and recording",
        "background and release",
        "background",
    ),
    (
        "writing and recording",
        "writing and production",
        "writing",
        "production",
        "recording",
    ),
    (
        "composition and lyrics",
        "lyrics and composition",
        "composition",
        "lyrical content",
        "lyrics",
    ),
    ("release and promotion", "release", "music video"),
    ("legacy", "impact"),
)

_CHART_LABELS: dict[str, tuple[str, str]] = {
    "billboardhot100": ("Billboard Hot 100", "US"),
    "billboardadultcontemporary": ("Billboard Adult Contemporary", "US"),
    "billboardadultpopsongs": ("Billboard Adult Pop Songs", "US"),
    "billboardcountrysongs": ("Billboard Hot Country Songs", "US"),
    "billboardpopsongs": ("Billboard Pop Songs", "US"),
    "billboardrandbhiphop": ("Billboard Hot R&B/Hip-Hop Songs", "US"),
    "billboardrhythmic": ("Billboard Rhythmic", "US"),
    "billboarddanceclubplay": ("Billboard Dance Club Songs", "US"),
    "billboarddanceairplay": ("Billboard Dance/Mix Show Airplay", "US"),
    "billboardmainstreamrock": ("Billboard Mainstream Rock", "US"),
    "billboarddigitalsongs": ("Billboard Digital Song Sales", "US"),
    "billboardalternativesongs": ("Billboard Alternative Songs", "US"),
    "billboardglobal200": ("Billboard Global 200", ""),
    "billboardjapanhot100": ("Billboard Japan Hot 100", "JP"),
    "billboardargentinahot100": ("Billboard Argentina Hot 100", "AR"),
    "billboardcolombiahot100": ("Billboard Colombia Hot 100", "CO"),
    "billboardeurodigital": ("Billboard Euro Digital Song Sales", ""),
    "billboardcanadaac": ("Billboard Canada AC", "CA"),
    "billboardcanadachrtop40": ("Billboard Canada CHR/Top 40", "CA"),
    "billboardcanadahotac": ("Billboard Canada Hot AC", "CA"),
    "australiaurban": ("Australia Urban (ARIA)", "AU"),
    "australia urban": ("Australia Urban (ARIA)", "AU"),
    "uk": ("UK Singles (OCC)", "GB"),
    "uksingles": ("UK Singles (OCC)", "GB"),
    "uksinglesbyname": ("UK Singles (OCC)", "GB"),
    "ukrandb": ("UK R&B (OCC)", "GB"),
    "scotland": ("Scotland (OCC)", "GB"),
    "ireland": ("Ireland (IRMA)", "IE"),
    "ireland2": ("Ireland (IRMA)", "IE"),
    "ireland4": ("Ireland (IRMA)", "IE"),
    "dutch40": ("Netherlands (Dutch Top 40)", "NL"),
    "dutch100": ("Netherlands (Single Top 100)", "NL"),
    "flanders": ("Belgium (Ultratop 50 Flanders)", "BE"),
    "wallonia": ("Belgium (Ultratop 50 Wallonia)", "BE"),
    "newzealand": ("New Zealand (RMNZ)", "NZ"),
    "new zealand": ("New Zealand (RMNZ)", "NZ"),
    "australia": ("Australia (ARIA)", "AU"),
    "canada": ("Canada (Canadian Hot 100)", "CA"),
    "canada rpm": ("Canada RPM", "CA"),
    "canada rpm ac": ("Canada RPM Adult Contemporary", "CA"),
    "canada rpm country": ("Canada RPM Country", "CA"),
    "germany": ("Germany (GfK)", "DE"),
    "west germany": ("West Germany (GfK)", "DE"),
    "austria": ("Austria (Ö3)", "AT"),
    "switzerland": ("Switzerland (Schweizer Hitparade)", "CH"),
    "sweden": ("Sweden (Sverigetopplistan)", "SE"),
    "norway": ("Norway (VG-lista)", "NO"),
    "denmark": ("Denmark (Tracklisten)", "DK"),
    "finland": ("Finland (Suomen virallinen lista)", "FI"),
    "france": ("France (SNEP)", "FR"),
    "frenchdigital": ("France (SNEP)", "FR"),
    "italy": ("Italy (FIMI)", "IT"),
    "spain": ("Spain (PROMUSICAE)", "ES"),
    "portugal": ("Portugal (AFP)", "PT"),
    "poland": ("Poland (ZPAV)", "PL"),
    "hungary": ("Hungary (Mahasz)", "HU"),
    "hungarysingle": ("Hungary (Mahasz)", "HU"),
    "hungarydance": ("Hungary (Dance Top 40)", "HU"),
    "hungarystream": ("Hungary (Stream Top 40)", "HU"),
    "czech republic": ("Czech Republic (IFPI)", "CZ"),
    "czechdigital": ("Czech Republic (Singles Digitál Top 100)", "CZ"),
    "slovakia2": ("Slovakia (IFPI)", "SK"),
    "slovakdigital2": ("Slovakia (Singles Digitál Top 100)", "SK"),
    "japan": ("Japan (Oricon)", "JP"),
    "mexico": ("Mexico (AMPROFON)", "MX"),
    "brazil2": ("Brazil (Billboard)", "BR"),
}

# Billboard ids are camel-cased chart names ("Billboardmainstreamrock").
_BILLBOARD_WORDS: tuple[str, ...] = (
    "hot100",
    "chrtop",
    "mainstream",
    "alternative",
    "contemporary",
    "christian",
    "argentina",
    "colombia",
    "australia",
    "rhythmic",
    "airplay",
    "country",
    "singles",
    "digital",
    "global",
    "canada",
    "japan",
    "mexico",
    "brazil",
    "adult",
    "dance",
    "songs",
    "randb",
    "hiphop",
    "latin",
    "gospel",
    "rock",
    "club",
    "play",
    "euro",
    "pop",
    "hot",
    "ac",
    "top",
    "200",
    "100",
)
_BILLBOARD_TOKEN_DISPLAY = {
    "randb": "R&B",
    "hiphop": "Hip-Hop",
    "hot100": "Hot 100",
    "chrtop": "CHR/Top",
    "ac": "AC",
}


def _billboard_words(rest: str) -> str:
    lower = rest.casefold()
    words = sorted(_BILLBOARD_WORDS, key=len, reverse=True)
    parts: list[str] = []
    index = 0
    while index < len(lower):
        for word in words:
            if lower.startswith(word, index):
                parts.append(_BILLBOARD_TOKEN_DISPLAY.get(word, word.title()))
                index += len(word)
                break
        else:
            end = index + 1
            while end < len(lower) and not any(
                lower.startswith(word, end) for word in words
            ):
                end += 1
            parts.append(lower[index:end].title())
            index = end
    return " ".join(parts)


@dataclass
class ChartData:
    chart_name: str
    country: str = ""
    peak: int = 0
    weeks_on_chart: int | None = None
    year: int | None = None
    source_url: str = ""


@dataclass
class WikipediaData:
    url: str
    summary: str = ""
    story: str = ""
    charts: list[ChartData] = field(default_factory=list)
    confidence: Literal["exact", "fuzzy"] = "exact"
    title: str = ""


def _get_json(client: httpx.Client, **params: object) -> dict:
    resp = client.get(
        API_URL,
        params={**params, "format": "json", "formatversion": 2},
    )
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError as exc:
        raise ProviderError("malformed Wikipedia response") from exc
    if not isinstance(data, dict):
        raise ProviderError("unexpected Wikipedia response")
    error = data.get("error")
    if error:
        message = error.get("info") if isinstance(error, dict) else error
        raise ProviderError(f"Wikipedia error: {message}")
    return data


def _rank_pages(hits: list[dict], title: str) -> list[tuple[dict, float]]:
    """Plausible pages, best first. Verification may reject the top one."""
    scored: list[tuple[tuple[float, float, float], dict, float]] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        page_title = (hit.get("title") or "").strip()
        if not page_title or _LIST_PAGE_RE.search(page_title):
            continue
        if _BAD_PAGE_RE.search(page_title):
            continue
        cleaned = _DISAMBIG_RE.sub("", page_title).strip()
        ratio = key_ratio(title, cleaned)
        if ratio < MIN_MATCH_RATIO:
            continue
        song_page = (
            1.0
            if re.search(r"\((?:song|single)\)\s*$", page_title, re.I)
            else 0.0
        )
        score = (1.0 if ratio == 1.0 else 0.0, song_page, ratio)
        scored.append((score, hit, ratio))
    scored.sort(key=lambda entry: entry[0], reverse=True)
    return [(hit, ratio) for _, hit, ratio in scored]


def _search_title(raw: str) -> str:
    """Keep a leading parenthetical, drop trailing edition noise.

    ``"(I Can't Get No) Satisfaction (Mono)"`` keeps the part that the generic
    title cleaner would throw away, which is the only searchable title.
    """
    text = (raw or "").strip()
    if " - " in text:
        return ""
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]\s*$", "", text).strip()
    if text.startswith(("(", "[")):
        return text
    return ""


def _int(value: str) -> int | None:
    text = (value or "").strip().lstrip("#").replace(",", "")
    return int(text) if text.isdigit() else None


def _mentions(text: str, artist: str) -> bool:
    """Whole-word artist match, so "Release" is not found inside "released"."""
    wanted = _WORD_RE.findall((artist or "").casefold())
    if not wanted:
        return False
    words = _WORD_RE.findall((text or "").casefold())
    size = len(wanted)
    return any(words[i : i + size] == wanted for i in range(len(words) - size + 1))


def _artist_variants(artist: str) -> list[str]:
    """Accept the common credit variants found in article leads."""
    artist = (artist or "").strip()
    if not artist:
        return []
    variants = [artist]
    swapped = artist.replace("&", "and")
    if swapped != artist:
        variants.append(swapped)
    primary = re.split(
        r"\s*(?:&|\band\b|\bfeat\.?\b|\bfeaturing\b)\s*",
        artist,
        maxsplit=1,
        flags=re.I,
    )[0].strip()
    if primary and primary != artist:
        variants.append(primary)
    if artist.casefold().startswith("the "):
        variants.append(artist[4:].strip())
    seen: list[str] = []
    for variant in variants:
        if variant and variant.casefold() not in {item.casefold() for item in seen}:
            seen.append(variant)
    return seen


def _mentions_any(text: str, artist: str) -> bool:
    return any(_mentions(text, variant) for variant in _artist_variants(artist))


def _truncate(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if end >= limit // 2:
        return cut[: end + 1].strip()
    return cut.rsplit(" ", 1)[0].rstrip(",;:") + "..."


def _top_sections(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Lead text plus level-2 sections (subsections stay in their parent)."""
    intro: list[str] = []
    sections: list[tuple[str, str]] = []
    title: str | None = None
    body: list[str] = []
    for line in (text or "").splitlines():
        heading = _HEADING_RE.match(line)
        if heading:
            if len(heading.group(1)) == 2:
                if title is not None:
                    sections.append((title, "\n".join(body).strip()))
                title = heading.group(2).strip()
                body = []
            # Deeper headings are structure, not prose; drop the markup but
            # keep their paragraphs in the parent section.
            continue
        if title is None:
            intro.append(line)
        else:
            body.append(line)
    if title is not None:
        sections.append((title, "\n".join(body).strip()))
    return "\n".join(intro).strip(), sections


def _story_for(sections: list[tuple[str, str]]) -> str:
    lowered = [(title.casefold(), body) for title, body in sections]

    def pick(group: tuple[str, ...]) -> tuple[str, str] | None:
        for name in group:
            for title, body in lowered:
                if title == name and len(body) >= 120:
                    return title, body
        for name in group:
            for title, body in lowered:
                if title.startswith(name) and len(body) >= 120:
                    return title, body
        return None

    chosen: list[str] = []
    seen: set[str] = set()

    def add(hit: tuple[str, str] | None) -> None:
        if hit is None or hit[0] in seen:
            return
        seen.add(hit[0])
        chosen.append(hit[1])

    background = pick(_STORY_GROUPS[0])
    if background:
        add(background)
        # "Background and composition" already covers the music; only pull a
        # second section when the background is about the recording.
        if "composition" not in background[0]:
            add(pick(_STORY_GROUPS[2]))
    else:
        add(pick(_STORY_GROUPS[1]))
        add(pick(_STORY_GROUPS[2]))

    if not chosen:
        for group in _STORY_GROUPS[3:]:
            hit = pick(group)
            if hit:
                add(hit)
                break

    if not chosen:
        return ""
    return _truncate("\n\n".join(chosen), STORY_LIMIT)


def _chart_label(chart_id: str) -> tuple[str, str]:
    key = " ".join((chart_id or "").replace("_", " ").split()).casefold()
    if key in _CHART_LABELS:
        return _CHART_LABELS[key]
    if key.startswith("billboard"):
        rest = chart_id.strip()[len("billboard") :]
        words = _billboard_words(rest) if rest else "Chart"
        return (f"Billboard {words}".strip(), "US")
    pretty = re.sub(r"(\d+)$", r" \1", chart_id.strip())
    return (pretty.title(), "")


def parse_charts(wikitext: str, source_url: str = "") -> list[ChartData]:
    """``{{single chart}}`` placements, skipping year/decade/all-time lists."""
    found: dict[str, ChartData] = {}
    headings: list[tuple[int, str]] = []

    for line in (wikitext or "").splitlines():
        heading = _HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            while headings and headings[-1][0] >= level:
                headings.pop()
            headings.append((level, heading.group(2).strip()))
            continue

        if any(_BAD_CHART_SECTION_RE.search(name) for _, name in headings):
            continue
        match = _SINGLE_CHART_RE.search(line)
        if match is None:
            continue

        parts = [part.strip() for part in match.group(1).split("|")]
        if len(parts) < 2:
            continue
        peak = _int(parts[1])
        if peak is None or not 1 <= peak <= 200:
            continue
        name, country = _chart_label(parts[0])
        year = None
        for part in parts[2:]:
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            if key.strip().casefold() not in {"date", "year"}:
                continue
            head = re.search(r"(\d{4})", value)
            if head and 1900 <= int(head.group(1)) <= 2100:
                year = int(head.group(1))
                break

        existing = found.get(name)
        if existing is not None and existing.peak <= peak:
            continue
        found[name] = ChartData(
            chart_name=name,
            country=country,
            peak=peak,
            year=year,
            source_url=source_url,
        )

    charts = list(found.values())
    charts.sort(key=lambda entry: (entry.chart_name, entry.peak))
    return charts[:MAX_CHARTS]


def lookup_wikipedia(
    title: str,
    artist: str,
    client: httpx.Client,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> WikipediaData | None:
    """Best-effort Wikipedia prose and chart placements for a track."""
    clean_title, clean_artist = clean_query(title, artist)
    if not clean_title:
        return None

    search_title = _search_title(title) or clean_title
    query = f"{search_title} {clean_artist}".strip()
    search = _get_json(
        client,
        action="query",
        list="search",
        srsearch=query,
        srlimit=6,
    )
    hits = [
        hit
        for hit in (search.get("query") or {}).get("search") or []
        if isinstance(hit, dict)
    ]

    # A title match alone is not enough: a TV episode can share the name, and
    # the first hit may be a cover by someone else. Try the plausible pages in
    # order and keep the first whose lead actually names the artist.
    for page, ratio in _rank_pages(hits, search_title)[:3]:
        page_title = page["title"]
        sleep(PAUSE_S)
        details = _get_json(
            client,
            action="query",
            prop="extracts|info",
            inprop="url",
            explaintext=1,
            redirects=1,
            titles=page_title,
        )
        pages = [
            item
            for item in (details.get("query") or {}).get("pages") or []
            if isinstance(item, dict) and not item.get("missing")
        ]
        if not pages:
            continue
        page_data = pages[0]
        extract = page_data.get("extract") or ""
        url = (
            page_data.get("fullurl")
            or f"https://en.wikipedia.org/wiki/"
            f"{quote(page_title.replace(' ', '_'))}"
        )

        intro, sections = _top_sections(extract)
        if clean_artist and not _mentions_any(intro, clean_artist):
            continue
        summary = _truncate(intro, SUMMARY_LIMIT)
        story = _story_for(sections)
        if not summary and not story:
            continue

        charts: list[ChartData] = []
        sleep(PAUSE_S)
        try:
            parsed = _get_json(
                client,
                action="parse",
                page=page_title,
                prop="wikitext",
                redirects=1,
            )
            wikitext = (parsed.get("parse") or {}).get("wikitext") or ""
            charts = parse_charts(wikitext, url)
        except (httpx.HTTPError, ProviderError):
            # Prose is the valuable part; chart templates are a bonus.
            charts = []

        return WikipediaData(
            title=page_title,
            url=url,
            summary=summary,
            story=story,
            charts=charts,
            confidence="exact" if ratio == 1.0 else "fuzzy",
        )
    return None
