# Library Track Details Nakout Playlist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a read-only “Nakout playlist” section in the Studio library track-details modal, listing the genre queue(s) used by Now Playing that include the track.

**Architecture:** Add a derived `nakout_playlists` array to the existing studio track-detail response, built by joining the track's cached rows through `Playlist` to `Genre` and deduplicating by genre. Render it in `TrackDetailEditor` above the editorial Facts fields; the existing editable Genres field is untouched.

**Tech Stack:** FastAPI, SQLModel, Pydantic, pytest; React 18, TypeScript, Vitest, Testing Library; plain CSS in `vintage.css`.

---

## File Structure

- `backend/app/schemas.py` — define `NakoutPlaylistOut` and add `nakout_playlists` to `TrackDetailOut`.
- `backend/app/track_details.py` — query the track's distinct Nakout genres in `admin_detail()`.
- `backend/tests/test_track_details.py` — cover dedupe, multiple genres, and standalone tracks.
- `frontend/src/types.ts` — add the `NakoutPlaylist` type and `StudioTrackDetail` field.
- `frontend/src/components/admin/TrackDetailEditor.tsx` — render the read-only section.
- `frontend/src/components/admin/TrackLibraryPanel.dom.test.tsx` — cover populated and empty states plus unchanged editorial genres.
- `frontend/src/styles/vintage.css` — style the read-only list.
- `docs/changelog.md` — record the change, files, restart and verification.

---

### Task 1: Expose Nakout playlists on the studio detail API

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/track_details.py`
- Test: `backend/tests/test_track_details.py`

- [ ] **Step 1: Write the failing backend tests**

At the top of `backend/tests/test_track_details.py`, change the SQLModel import to include `select`:

```python
from sqlmodel import Session, SQLModel, create_engine, select
```

Add these two tests after `test_studio_get_returns_an_empty_shell_for_a_known_track`:

```python
def test_studio_detail_lists_each_nakout_playlist_once(tmp_path):
    client, engine = _seed(tmp_path)
    with Session(engine) as s:
        jazz = s.exec(select(Genre).where(Genre.slug == "jazz")).one()
        jazz.color = "#f2a33a"
        blues = Genre(
            name="Blues",
            slug="blues",
            sort_order=-1,
            color="#5fb3b3",
        )
        s.add(blues)
        s.commit()
        s.refresh(blues)
        playlist = Playlist(genre_id=blues.id, youtube_playlist_id="PL3")
        s.add(playlist)
        s.commit()
        s.refresh(playlist)
        s.add(
            TrackCache(
                playlist_id=playlist.id,
                youtube_video_id="vid1",
                title="Blue in Green",
                artist="Miles Davis",
                position=0,
            )
        )
        s.commit()

    body = client.get("/api/studio/tracks/vid1").json()

    assert body["nakout_playlists"] == [
        {"slug": "blues", "name": "Blues", "color": "#5fb3b3"},
        {"slug": "jazz", "name": "Jazz", "color": "#f2a33a"},
    ]


def test_studio_detail_has_no_nakout_playlist_for_standalone_track(tmp_path):
    client, engine = _seed(tmp_path)
    with Session(engine) as s:
        s.add(
            TrackCache(
                playlist_id=None,
                youtube_video_id="solo",
                title="Solo",
                artist="Nobody",
                position=0,
            )
        )
        s.commit()

    body = client.get("/api/studio/tracks/solo").json()

    assert body["nakout_playlists"] == []
```

The first test also covers deduplication: `vid1` is already in two Jazz source playlists (`PL1` and `PL2`) in `_seed`, but Jazz must appear only once.

- [ ] **Step 2: Run the tests to verify they fail**

Run from `backend/`:

```bash
python -m pytest tests/test_track_details.py -k nakout -q
```

Expected: both tests fail because the response has no `nakout_playlists` key (`KeyError`).

- [ ] **Step 3: Add the response model**

In `backend/app/schemas.py`, after `SimilarTrackOut`, add:

```python
class NakoutPlaylistOut(BaseModel):
    slug: str
    name: str
    color: str = ""
```

Add the field to `TrackDetailOut`:

```python
class TrackDetailOut(TrackDetailBase):
    dj_note_public: bool = True
    sources: dict = Field(default_factory=dict)
    locked_fields: list[str] = Field(default_factory=list)
    needs_review: bool = False
    enriched_at: datetime | None = None
    enrich_error: str | None = None
    story_at: datetime | None = None
    story_error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    status: Literal["empty", "auto", "curated"] = "empty"
    completeness: int = 0
    nakout_playlists: list[NakoutPlaylistOut] = Field(default_factory=list)
```

- [ ] **Step 4: Implement the derived query**

In `backend/app/track_details.py`, import the new schema:

```python
from app.schemas import (
    ChartEntryOut,
    NakoutPlaylistOut,
    SimilarTrackOut,
    TrackDetailBase,
    TrackDetailIn,
    TrackDetailOut,
    TrackLibraryItem,
    TrackLibraryOut,
)
```

Add this helper after `_similar_tracks`:

```python
def _nakout_playlists(
    session: Session, video_id: str
) -> list[NakoutPlaylistOut]:
    genres = session.exec(
        select(Genre)
        .join(Playlist, Playlist.genre_id == Genre.id)
        .join(TrackCache, TrackCache.playlist_id == Playlist.id)
        .where(TrackCache.youtube_video_id == video_id)
        .distinct()
        .order_by(Genre.sort_order, Genre.name)
    ).all()
    return [
        NakoutPlaylistOut(
            slug=genre.slug,
            name=genre.name,
            color=genre.color or "",
        )
        for genre in genres
    ]
```

Add the field to the payload built by `admin_detail()`:

```python
    payload.update(
        {
            "dj_note": row.dj_note if row else None,
            "dj_note_public": row.dj_note_public if row else True,
            "sources": dict(row.sources or {}) if row else {},
            "locked_fields": list(row.locked_fields or []) if row else [],
            "needs_review": row.needs_review if row else False,
            "enriched_at": row.enriched_at if row else None,
            "enrich_error": row.enrich_error if row else None,
            "story_at": row.story_at if row else None,
            "story_error": row.story_error if row else None,
            "created_at": row.created_at if row else None,
            "updated_at": row.updated_at if row else None,
            "status": status_for(row, chart_total),
            "completeness": completeness_for(row, chart_total),
            "nakout_playlists": _nakout_playlists(session, video_id),
        }
    )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run from `backend/`:

```bash
python -m pytest tests/test_track_details.py -q
```

Expected: all tests in the file pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas.py backend/app/track_details.py backend/tests/test_track_details.py
git commit -m "feat: expose Nakout playlists on studio track details"
```

---

### Task 2: Render the Nakout playlist section in the details modal

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/admin/TrackDetailEditor.tsx`
- Modify: `frontend/src/components/admin/TrackLibraryPanel.dom.test.tsx`
- Modify: `frontend/src/styles/vintage.css`

- [ ] **Step 1: Add the type and write the failing frontend tests**

In `frontend/src/types.ts`, add this interface near `SimilarTrack`:

```typescript
export interface NakoutPlaylist {
  slug: string;
  name: string;
  color: string;
}
```

Add the field to `StudioTrackDetail`:

```typescript
export interface StudioTrackDetail extends TrackDetail {
  dj_note_public: boolean;
  sources: Record<string, Record<string, string>>;
  locked_fields: string[];
  needs_review: boolean;
  enriched_at: string | null;
  enrich_error: string | null;
  story_at: string | null;
  story_error: string | null;
  created_at: string | null;
  updated_at: string | null;
  status: "empty" | "auto" | "curated";
  completeness: number;
  nakout_playlists: NakoutPlaylist[];
}
```

In `frontend/src/components/admin/TrackLibraryPanel.dom.test.tsx`, add the default to the `detail()` fixture:

```typescript
    status: "curated",
    completeness: 4,
    metadata_sources: [],
    nakout_playlists: [],
    ...overrides,
```

Add these tests inside the `describe("TrackLibraryPanel", ...)` block, after the “opens the editor and saves manual edits with protection” test:

```typescript
  it("shows the Nakout playlists a track belongs to", async () => {
    mocked.studioTrack.mockResolvedValue(
      detail({
        genres: ["jazz", "modal jazz"],
        nakout_playlists: [
          { slug: "jazz", name: "Jazz", color: "#f2a33a" },
          { slug: "opm", name: "OPM", color: "#5fb3b3" },
        ],
      }),
    );
    renderPanel();

    fireEvent.click(
      await screen.findByRole("button", { name: /Blue in Green/ }),
    );

    const section = await screen.findByRole("group", {
      name: "Nakout playlist",
    });
    expect(within(section).getByText("Jazz")).toBeInTheDocument();
    expect(within(section).getByText("OPM")).toBeInTheDocument();
    expect(
      within(section).getByText("Genre queue used in Now Playing."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Genres")).toHaveValue(
      "jazz, modal jazz",
    );
  });

  it("says when a track is not on a Nakout playlist", async () => {
    mocked.studioTrack.mockResolvedValue(detail({ nakout_playlists: [] }));
    renderPanel();

    fireEvent.click(
      await screen.findByRole("button", { name: /Blue in Green/ }),
    );

    expect(
      await screen.findByText("Not on a Nakout playlist."),
    ).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run from `frontend/`:

```bash
npx vitest run src/components/admin/TrackLibraryPanel.dom.test.tsx
```

Expected: the new tests fail because the modal has no “Nakout playlist” group and no empty-state text.

- [ ] **Step 3: Render the section in the editor**

In `frontend/src/components/admin/TrackDetailEditor.tsx`, insert this fieldset as the first child of the `<form className="track-editor-form">`, before the Facts fieldset:

```tsx
            <fieldset className="track-editor-section">
              <legend>Nakout playlist</legend>
              {detail && detail.nakout_playlists.length > 0 ? (
                <ul className="te-nakout-list">
                  {detail.nakout_playlists.map((playlist) => (
                    <li key={playlist.slug}>
                      <i
                        className="dot"
                        style={{
                          background: playlist.color || "var(--amber)",
                        }}
                        aria-hidden="true"
                      />
                      <span>{playlist.name}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="hint">Not on a Nakout playlist.</p>
              )}
              <p className="hint">Genre queue used in Now Playing.</p>
            </fieldset>
```

- [ ] **Step 4: Add the list styles**

In `frontend/src/styles/vintage.css`, after the `.te-grid` rule, add:

```css
.te-nakout-list {
  display: grid;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.te-nakout-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.9rem;
}
```

- [ ] **Step 5: Run the frontend tests to verify they pass**

Run from `frontend/`:

```bash
npx vitest run src/components/admin/TrackLibraryPanel.dom.test.tsx
```

Expected: all tests in the file pass.

- [ ] **Step 6: Typecheck and lint**

Run from `frontend/`:

```bash
npm run typecheck
npm run lint
```

Expected: both complete with no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types.ts frontend/src/components/admin/TrackDetailEditor.tsx frontend/src/components/admin/TrackLibraryPanel.dom.test.tsx frontend/src/styles/vintage.css
git commit -m "feat: show Nakout playlist in library track details"
```

---

### Task 3: Record the change and run full verification

**Files:**
- Modify: `docs/changelog.md`

- [ ] **Step 1: Add the changelog entry**

At the top of `docs/changelog.md`, directly under the intro paragraph, add:

```markdown
## 2026-11-13 - show Nakout playlist in library track details

The Studio library's track-details modal now has a read-only **Nakout
playlist** section listing the genre queue(s) used in Now Playing that
include the track, with each genre's colour. YouTube source playlist labels
are not shown, and the editable **Genres** field still holds the track's
original editorial genres.

- Files touched:
  - `backend/app/schemas.py`
  - `backend/app/track_details.py`
  - `backend/tests/test_track_details.py`
  - `frontend/src/types.ts`
  - `frontend/src/components/admin/TrackDetailEditor.tsx`
  - `frontend/src/components/admin/TrackLibraryPanel.dom.test.tsx`
  - `frontend/src/styles/vintage.css`
  - `docs/changelog.md`
- **Container restart required?** Yes - frontend and backend:
  `docker compose up -d --build backend frontend`
- **Verification:** targeted backend track-details tests pass; the full
  frontend suite, typecheck and lint pass.
```

- [ ] **Step 2: Run the full backend suite**

Run from `backend/`:

```bash
python -m pytest -q
```

Expected: the full suite passes. Ruff is not installed in this local
environment; CI runs it.

- [ ] **Step 3: Run the full frontend suite**

Run from `frontend/`:

```bash
npm test
npm run typecheck
npm run lint
```

Expected: all three commands pass.

- [ ] **Step 4: Commit**

```bash
git add docs/changelog.md
git commit -m "docs: record Nakout playlist track details"
```

- [ ] **Step 5: Show the branch state**

```bash
git status --short
git log --oneline -4
```

Expected: a clean working tree with the spec, backend, frontend and changelog commits on `feat/library-nakout-playlist`.

---

### Task 4: Push the branch and open the pull request

**Files:** none

- [ ] **Step 1: Confirm the GitHub account and push**

Run from the repository root:

```bash
gh auth switch --user xjojoramirez
gh auth status
git push -u origin feat/library-nakout-playlist
```

Expected: `gh` reports `xjojoramirez` as the active account and the branch is
published.

- [ ] **Step 2: Open the pull request**

```bash
gh pr create --title "feat: show Nakout playlist in library track details" --body "## Summary

The Studio library track-details modal now shows a read-only **Nakout
playlist** section with the genre queue(s) used by Now Playing that include
the track. YouTube source playlists are not shown, and the editable Genres
field still holds the track's original editorial genres.

## Verification

- Targeted `backend/tests/test_track_details.py` tests pass.
- Full backend pytest suite passes.
- Full frontend Vitest suite, TypeScript typecheck and oxlint pass.

## Container restart

Yes — backend and frontend: \`docker compose up -d --build backend frontend\`"
```

Expected: a pull request URL is printed.

---

## Notes for the implementer

- Do not add YouTube playlist labels, IDs or URLs to the new section.
- Do not change the existing editable **Genres** field or `TrackDetailIn`.
- `Nakout playlist` entries are deduplicated genres; several YouTube source
  playlists under one genre must produce one row.
- If a genre has no colour, render the dot with `var(--amber)`.
