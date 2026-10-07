import { useState } from "react";
import { api } from "../../api/client";
import { messageFor } from "../../utils/errors";
import { ConfirmDialog } from "../ConfirmDialog";
import type { Genre } from "../../types";

interface Props {
  genres: Genre[];
  onGenresChanged: () => Promise<void> | void;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}

interface Draft {
  name: string;
  slug: string;
  is_default: boolean;
}

export function GenresPanel({
  genres,
  onGenresChanged,
  onNotice,
  onError,
}: Props) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [editId, setEditId] = useState<number | null>(null);
  const [draft, setDraft] = useState<Draft>({
    name: "",
    slug: "",
    is_default: false,
  });
  const [pendingDelete, setPendingDelete] = useState<Genre | null>(null);

  const addGenre = async () => {
    try {
      await api.createGenre(name, slug);
      setName("");
      setSlug("");
      onNotice("Genre added.");
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
      is_default: genre.is_default,
    });
  };

  const saveEdit = async () => {
    if (editId === null) return;
    try {
      await api.updateGenre(editId, {
        name: draft.name,
        slug: draft.slug,
        is_default: draft.is_default,
      });
      setEditId(null);
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

  return (
    <section className="admin-panel" aria-label="Genres">
      <h2>Genres</h2>
      <div className="form-grid">
        <label className="field">
          Genre name
          <input
            aria-label="Genre name"
            placeholder="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="field">
          Genre slug
          <input
            aria-label="Genre slug"
            placeholder="Slug"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
          />
        </label>
        <button
          type="button"
          className="btn btn-primary"
          onClick={addGenre}
          disabled={!name || !slug}
        >
          Add genre
        </button>
      </div>
      <ul className="genre-admin-list">
        {genres.map((s) =>
          editId === s.id ? (
            <li key={s.id}>
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
                <input
                  aria-label="Edit genre slug"
                  placeholder="Slug"
                  value={draft.slug}
                  onChange={(e) =>
                    setDraft((prev) => ({ ...prev, slug: e.target.value }))
                  }
                />
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
              <div className="row-actions">
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  onClick={saveEdit}
                  disabled={!draft.name || !draft.slug}
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
            </li>
          ) : (
            <li key={s.id}>
              <span className="st-name">{s.name}</span>
              <span className="st-slug">/{s.slug}</span>
              {s.is_default && <span className="count-pill">default</span>}
              <span className="count-pill">{s.track_count} tracks</span>
              <div className="row-actions">
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => startEdit(s)}
                >
                  Edit
                </button>
                <button
                  type="button"
                  className="btn btn-danger btn-sm"
                  onClick={() => setPendingDelete(s)}
                >
                  Delete
                </button>
              </div>
            </li>
          ),
        )}
      </ul>
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
