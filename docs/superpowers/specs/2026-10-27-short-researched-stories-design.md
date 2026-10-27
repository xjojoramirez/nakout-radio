# Short researched stories

Date: 2026-10-27

## Problem

The Story tab shows a summary and a story. Automatic Wikipedia enrichment fills
both by copying large article sections: a lead paragraph up to 900 characters
and one or two Background/Composition sections up to 900 more. The result reads
like an article dump and often includes chart positions, awards, tour dates and
release trivia. The composer can already research a track and write better prose,
but its limits (summary 600, story 900) still allow long stories, and it only
runs when an agent is asked to compose a specific track.

Listeners should get the one detail they would repeat, not the song's whole
history. Automatic enrichment still cannot call an LLM, so there are two layers:

1. the automatic path extracts a much smaller, filtered highlight;
2. the composer agent researches the web and writes the curated version.

## Design

### Automatic Wikipedia path

`app.enrichment.wikipedia` produces:

- `summary`: the first sentence of the lead, capped at 220 characters. A short
  second sentence is allowed only when the first is under 100 characters and
  the combined text still fits. Chart sentences are never added.
- `story`: one anecdote, at most three sentences from one paragraph and 400
  characters. Candidate sentences come from the existing Background/Composition/
  Writing/Recording/History sections. Sentences about chart peaks,
  certifications, awards, release formats, personnel lists, tour dates and
  cover versions are removed. Sentences with origin signals (`wrote`,
  `composed`, `inspired`, `recorded`, `interview`, `said`, `recalled`) are
  preferred, and windows that start with a bare pronoun or split a quotation
  are rejected.
- If no usable anecdote exists, `story` is empty. A forced refresh clears a
  previous provider-written story when the new extraction finds none, so old
  article dumps disappear instead of surviving because the new value is empty.

The full article is still available through the source link; the story is the
trailer, not the article.

### Composer agent

`app.composer` tightens the payload limits:

- `summary`: 40-220 characters, one sentence. Say what the song is without
  chart lists or generic "is a song by" padding.
- `story`: 80-400 characters, two or three sentences. One vivid origin or
  recording anecdote: who wrote it, where and when, what inspired it, or a human
  moment from the writing/recording.

If research finds no genuine anecdote, the composer writes only the summary and
skips the story. It never pads with history or chart facts. Facts stay fill-only
and every write stays locked with its evidence URL.

`.opencode/agents/track-info-composer.md` and
`.opencode/agents/track-details-reviewer.md` state the new limits and the
"one anecdote, no chart lists" rule.

### Existing tracks

`app.story_refresh` is a maintenance CLI:

```
python -m app.story_refresh --dry-run
python -m app.story_refresh
```

It selects tracks whose `summary` or `story` came from Wikipedia and calls
`enrich_story(..., force=True)` with chart parsing disabled, so the existing
chart rows are not replaced. Composer-locked prose is skipped by the normal
lock rules. The command is separate from `detail_tools`, so the composer and
reviewer agents cannot call it.

The rollout refreshes provider prose first, then runs the composer on a sample
of ten tracks for style approval, then batches the rest through the composer.

### Display

No frontend change. The Story tab already renders `summary` followed by
`story` and the source link. With the new limits a normal track shows at most
about 620 characters instead of roughly 1,500.

## Boundaries

- Automatic enrichment remains extractive. It does not invent or paraphrase
  beyond sentence selection and truncation.
- The composer remains the only agent write path.
- The reviewer remains read-only.
- Provider prose is only cleared when it is unlocked and has a Wikipedia source
  entry; manual text is never touched.

## Testing

- `backend/tests/test_story.py`: summary cap, one-anecdote selection, chart and
  award filtering, empty-story fallback, clearing old provider prose while
  keeping manual prose.
- `backend/tests/test_composer.py`: new length bounds, valid short payloads,
  rejection of overlong prose.
- `backend/tests/test_story_refresh.py`: provider-prose selection and dry run.
- Full backend suite, frontend tests/typecheck/build, then rebuild the backend
  container and refresh provider prose against the live volume.
