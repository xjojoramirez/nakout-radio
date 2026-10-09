import { useState } from "react";
import type { CSSProperties } from "react";
import { api } from "../../api/client";
import { messageFor } from "../../utils/errors";
import { GENRE_PALETTE } from "../../palette";
import { ConfirmDialog } from "../ConfirmDialog";
import { PaletteSwatches } from "./PaletteSwatches";
import type { Genre } from "../../types";

interface Props {
  genres: Genre[];
  onGenresChanged: () => Promise<void> | void;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
  onJump?: (
    tab: string,
    intent?: { playlistsGenre?: number; scheduleGenre?: number },
  ) => void;
}

interface Draft {
  name: string;
  slug: string;
  color: string;
  is_default: boolean;
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "")
    .slice(0, 14);
}

function nextColor(used: string[]): string {
  const free = GENRE_PALETTE.find((c) => !used.includes(c));
  return free ?? GENRE_PALETTE[used.length % GENRE_PALETTE.length];
}

export function GenresPanel({
  genres,
  onGenresChanged,
  onNotice,
  onError,
  onJump,
}: Props) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [color, setColor] = useState<string>(
    GENRE_PALETTE[GENRE_PALETTE.length - 1],
  );
  const [editId, setEditId] = useState<number | null>(null);
  const [draft, setDraft] = useState<Draft>({
    name: "",
    slug: "",
    color: "",
    is_default: false,
  });
  const [pendingDelete, setPendingDelete] = useState<Genre | null>(null);
  const [flashId, setFlashId] = useState<number | null>(null);

  const flash = (id: number) => {
    setFlashId(id);
    window.setTimeout(
      () => setFlashId((current) => (current === id ? null : current)),
      1500,
    );
  };

  const addGenre = async () => {
    const trimmedName = name.trim();
    const trimmedSlug = slug.trim();
    if (!trimmedName || !trimmedSlug) return;
    try {
      const created = await api.createGenre(trimmedName, trimmedSlug, color);
      setName("");
      setSlug("");
      setSlugTouched(false);
      setColor(nextColor([...genres.map((g) => g.color), color]));
      flash(created.id);
      onNotice(
        `${created.name} added. Add a playlist and a schedule slot to put it on air.`,
      );
      await onGenresChanged();
    } catch (err) {
      onError(messageFor(err));
    }
  };

  const startEdit = (genre: Genre) => {
    setEditId(genre.id);
    setDraft({
      name: genre.name,
      slug: genre.slug,
      color: genre.color,
      is_default: genre.is_default,
    });
  };

  const saveEdit = async () => {
    if (editId === null) return;
    try {
      const updated = await api.updateGenre(editId, {
        name: draft.name,
        slug: draft.slug,
        is_default: draft.is_default,
        color: draft.color,
      });
      setEditId(null);
      flash(updated.id);
      onNotice("Genre updated.");
      await onGenresChanged();
    } catch (err) {
      onError(messageFor(err));
    }
  };

  const removeGenre = async (genre: Genre) => {
    try {
      await api.deleteGenre(genre.id);
      onNotice("Genre deleted.");
      await onGenresChanged();
    } catch (err) {
      onError(messageFor(err));
    }
  };

  const playGenre = async (genre: Genre) => {
    try {
      const tracks = await api.genreTracks(genre.id);
      if (!tracks.length) {
        onError(`"${genre.name}" has no tracks yet. Add a playlist.`);
        return;
      }
      await api.play(genre.id, tracks[0].youtube_video_id);
      onNotice(`Now playing ${genre.name}.`);
      onJump?.("now");
    } catch (err) {
      onError(messageFor(err));
    }
  };

  return (
    <section className="admin-panel" aria-label="Genres">
      <div>
        <h2 className="sec">Genres</h2>
        <p className="sub">
          A genre is a mood. Playlists feed it, and the schedule decides when it
          plays.
        </p>
      </div>

      <form
        className="card gform"
        onSubmit={(e) => {
          e.preventDefault();
          void addGenre();
        }}
      >
        <h3 className="ttl">New genre</h3>
        <div className="gf-grid">
          <label className="field">
            Genre name
            <input
              aria-label="Genre name"
              placeholder="Name"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                if (!slugTouched) setSlug(slugify(e.target.value));
              }}
            />
          </label>
          <label className="field">
            Genre slug
            <span className="pre">
              <span>/</span>
              <input
                aria-label="Genre slug"
                placeholder="Slug"
                value={slug}
                onChange={(e) => {
                  setSlug(e.target.value);
                  setSlugTouched(e.target.value.trim() !== "");
                }}
              />
            </span>
          </label>
        </div>
        <PaletteSwatches label="Genre colour" value={color} onChange={setColor} />
        <div>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={!name.trim() || !slug.trim()}
          >
            Add genre
          </button>
        </div>
      </form>

      {genres.length === 0 ? (
        <div className="empty">No genres yet. Create your first one above.</div>
      ) : (
        <div className="ggrid">
          {genres.map((g) =>
            editId === g.id ? (
              <article
                key={g.id}
                className={flashId === g.id ? "gcard flash" : "gcard"}
                style={
                  {
                    "--gc": draft.color || g.color || "var(--amber)",
                  } as CSSProperties
                }
              >
                <div className="gedit">
                  <label className="field">
                    Genre name
                    <input
                      aria-label="Edit genre name"
                      placeholder="Name"
                      value={draft.name}
                      onChange={(e) =>
                        setDraft((prev) => ({ ...prev, name: e.target.value }))
                      }
                    />
                  </label>
                  <label className="field">
                    Genre slug
                    <span className="pre">
                      <span>/</span>
                      <input
                        aria-label="Edit genre slug"
                        placeholder="Slug"
                        value={draft.slug}
                        onChange={(e) =>
                          setDraft((prev) => ({ ...prev, slug: e.target.value }))
                        }
                      />
                    </span>
                  </label>
                  <label className="field field-inline">
                    <input
                      type="checkbox"
                      aria-label="Default genre"
                      checked={draft.is_default}
                      onChange={(e) =>
                        setDraft((prev) => ({
                          ...prev,
                          is_default: e.target.checked,
                        }))
                      }
                    />
                    Default
                  </label>
                  <PaletteSwatches
                    label="Genre colour"
                    value={draft.color}
                    onChange={(c) =>
                      setDraft((prev) => ({ ...prev, color: c }))
                    }
                  />
                  <div className="gact">
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      onClick={() => void saveEdit()}
                      disabled={!draft.name.trim() || !draft.slug.trim()}
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => setEditId(null)}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              </article>
            ) : (
              <article
                key={g.id}
                className={flashId === g.id ? "gcard flash" : "gcard"}
                style={
                  { "--gc": g.color || "var(--amber)" } as CSSProperties
                }
              >
                <div className="gtop">
                  <i className="dot big" aria-hidden="true" />
                  <div>
                    <b>{g.name}</b>
                    <span className="mono">/{g.slug}</span>
                  </div>
                </div>
                <div className="gstats">
                  <span className="chip">{g.track_count} tracks</span>
                  {g.is_default && <span className="chip">default</span>}
                </div>
                {g.track_count === 0 && (
                  <div className="gwarn">
                    <span className="chip warn">No playlists</span>
                    <button
                      type="button"
                      className="btn-link"
                      onClick={() =>
                        onJump?.("playlists", { playlistsGenre: g.id })
                      }
                    >
                      Add one
                    </button>
                    <button
                      type="button"
                      className="btn-link"
                      onClick={() =>
                        onJump?.("schedule", { scheduleGenre: g.id })
                      }
                    >
                      Schedule it
                    </button>
                  </div>
                )}
                <div className="gact">
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    aria-label={`Play now ${g.name}`}
                    onClick={() => void playGenre(g)}
                  >
                    Play now
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    aria-label={`Edit ${g.name}`}
                    onClick={() => startEdit(g)}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger btn-sm"
                    aria-label={`Delete ${g.name}`}
                    onClick={() => setPendingDelete(g)}
                  >
                    Delete
                  </button>
                </div>
              </article>
            ),
          )}
        </div>
      )}

      {pendingDelete && (
        <ConfirmDialog
          title="Delete genre"
          message={`Delete “${pendingDelete.name}” and all of its playlists, tracks, and schedule slots?`}
          confirmLabel="Delete"
          danger
          onConfirm={() => {
            const genre = pendingDelete;
            setPendingDelete(null);
            void removeGenre(genre);
          }}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </section>
  );
}
