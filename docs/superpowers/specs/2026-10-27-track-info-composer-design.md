# Track info composer and reviewer

Date: 2026-10-27

## Problem

Track details can be enriched automatically from Deezer, MusicBrainz and
Wikipedia, but the prose is an article slice and empty facts stay empty. An
agent can research a specific recording better than the generic pipeline, yet
it must not be allowed to run arbitrary SQL or invent values. The reviewer also
needs a read path that does not depend on fragile one-line SQLite commands.

## Design

Two subagents with one shared, narrow CLI:

- `track-info-composer` researches a recording and writes the summary, story
  highlight and missing facts through `app.detail_tools apply`.
- `track-details-reviewer` is read-only. It uses `find` and `show`, checks the
  story, facts and charts against their sources, and proposes a highlight
  without saving it.

### Write rules

`app.composer.compose_detail` is the only write path:

- `summary` (20-600 characters) and `story` (40-900 characters) may replace an
  empty or provider-written value. A manually entered value without a lock is
  left alone and reported.
- `album`, `release_year`, `label`, `isrc` and `credits` are fill-only. A
  non-empty value is a conflict, never an overwrite.
- Every field written is added to `locked_fields`, so a later enrichment pass
  (including `force=True`) cannot replace it.
- Every field written gets a `sources` entry with the evidence URL, provider
  and fetch time. `apply` requires an http(s) source URL.
- A story write refreshes `story_at`; a summary-only write does not mark the
  story as checked.
- `--dry-run` returns the planned changes without creating or updating a row.

### CLI

```
python -m app.detail_tools find "<query>"
python -m app.detail_tools show <video_id>
python -m app.detail_tools apply <video_id> --source-url URL \
  [--summary TEXT] [--story TEXT] [--album TEXT] [--release-year YEAR] \
  [--label TEXT] [--isrc CODE] [--credit "Role=Name"] [--dry-run]
```

`find` and `show` print JSON so an agent can read the complete record, charts,
sources and locks without printing secrets. `apply` prints the applied and
skipped fields with reasons.

## Boundaries

- The composer cannot edit files, run arbitrary Python, unlock a field, or call
  a mutating API endpoint.
- The reviewer cannot write at all; its permissions only allow `detail_tools
  find/show`, `curl -k`, and `docker compose logs`.
- Neither agent touches `.env`, playlists, schedules or non-detail tables.

## Testing

`backend/tests/test_composer.py` covers fill-only facts, prose replacement,
locks, source records, dry runs, validation, enrichment non-overwrite, provider
inference, and the CLI. `backend/tests/test_story.py` keeps the Wikipedia and
chart parser coverage.
