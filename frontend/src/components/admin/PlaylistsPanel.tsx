import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { api } from "../../api/client";
import { messageFor } from "../../utils/errors";
import { timeAgo } from "../../utils/format";
import { ConfirmDialog } from "../ConfirmDialog";
import { AddPlaylistDialog } from "./AddPlaylistDialog";
import type { AddedPlaylist, Genre } from "../../types";

interface Props {
  genres: Genre[];
  onGenresChanged: () => Promise<void> | void;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
  onCountChange?: (count: number) => void;
  /** Cross-tab navigation. */
  onJump?: (
    tab: string,
    intent?: { playlistsGenre?: number; scheduleGenre?: number },
  ) => void;
}

interface Group {
  genre: Genre;
  items: AddedPlaylist[];
  tracks: number;
}

export function PlaylistsPanel({
  genres,
  onGenresChanged,
  onNotice,
  onError,
  onCountChange,
  onJump,
}: Props) {
  const [added, setAdded] = useState<AddedPlaylist[]>([]);
  const [addedError, setAddedError] = useState("");
  const [filter, setFilter] = useState("");
  const [syncingIds, setSyncingIds] = useState<number[]>([]);
  const [busyGroup, setBusyGroup] = useState<number | null>(null);
  const [pendingRemove, setPendingRemove] = useState<AddedPlaylist | null>(
    null,
  );
  const [flashId, setFlashId] = useState<number | null>(null);
  const [addDialog, setAddDialog] = useState<{ genreId: number | null } | null>(
    null,
  );

  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (flashTimer.current) clearTimeout(flashTimer.current);
    };
  }, []);

  const flash = (id: number) => {
    setFlashId(id);
    if (flashTimer.current) clearTimeout(flashTimer.current);
    flashTimer.current = window.setTimeout(
      () => setFlashId((current) => (current === id ? null : current)),
      1400,
    );
  };

  const loadAdded = useCallback(async () => {
    try {
      const loaded = await api.listPlaylists();
      setAdded(loaded);
      onCountChange?.(loaded.length);
      setAddedError("");
    } catch (err) {
      setAddedError(messageFor(err));
    }
  }, [onCountChange]);

  useEffect(() => {
    loadAdded();
  }, [loadAdded]);

  const movePlaylist = async (playlist: AddedPlaylist, genreId: number) => {
    if (genreId === playlist.genre_id) return;
    try {
      await api.updatePlaylist(playlist.id, { genre_id: genreId });
      const target = genres.find((g) => g.id === genreId);
      onNotice(`Moved to ${target?.name ?? String(genreId)}.`);
      await loadAdded();
      await onGenresChanged();
      flash(playlist.id);
    } catch (err) {
      await loadAdded();
      await onGenresChanged();
      onError(messageFor(err));
    }
  };

  const syncOne = async (id: number) => {
    if (syncingIds.includes(id)) return;
    setSyncingIds((ids) => [...ids, id]);
    try {
      const result = await api.refreshPlaylist(id);
      onNotice(`Nakout playlist synced (${result.synced} tracks).`);
      await loadAdded();
      await onGenresChanged();
    } catch (err) {
      onError(messageFor(err));
    } finally {
      setSyncingIds((ids) => ids.filter((x) => x !== id));
    }
  };

  const syncGroup = async (group: Group) => {
    if (!group.items.length || busyGroup !== null) return;
    const ids = group.items.map((p) => p.id);
    setBusyGroup(group.genre.id);
    setSyncingIds((prev) => Array.from(new Set([...prev, ...ids])));
    onNotice(`Syncing ${group.genre.name}…`);
    const settled = await Promise.allSettled(
      ids.map((id) => api.refreshPlaylist(id)),
    );
    const ok = settled.filter(
      (result): result is PromiseFulfilledResult<{ id: number; synced: number }> =>
        result.status === "fulfilled",
    );
    const failed = settled.find(
      (result): result is PromiseRejectedResult => result.status === "rejected",
    );
    if (failed) {
      onError(messageFor(failed.reason));
    } else {
      const synced = ok.reduce((acc, result) => acc + result.value.synced, 0);
      onNotice(
        `Synced ${group.genre.name} (${ok.length} ${
          ok.length === 1 ? "Nakout playlist" : "Nakout playlists"
        }, ${synced} tracks).`,
      );
    }
    setBusyGroup(null);
    setSyncingIds((prev) => prev.filter((x) => !ids.includes(x)));
    await loadAdded();
    await onGenresChanged();
  };

  const remove = async (id: number) => {
    try {
      await api.deletePlaylist(id);
      onNotice("Nakout playlist removed.");
      await loadAdded();
      await onGenresChanged();
    } catch (err) {
      onError(messageFor(err));
    }
  };

  const groups = useMemo<Group[]>(() => {
    const q = filter.trim().toLowerCase();
    const matches = (genre: Genre, playlist: AddedPlaylist) =>
      !q ||
      genre.name.toLowerCase().includes(q) ||
      (playlist.label || "").toLowerCase().includes(q) ||
      playlist.youtube_playlist_id.toLowerCase().includes(q);
    const visible = genres.filter(
      (genre) =>
        !q ||
        added.some(
          (playlist) =>
            playlist.genre_id === genre.id && matches(genre, playlist),
        ),
    );
    return visible.map((genre) => {
      const items = added.filter(
        (playlist) =>
          playlist.genre_id === genre.id && matches(genre, playlist),
      );
      return {
        genre,
        items,
        tracks: items.reduce((acc, playlist) => acc + playlist.track_count, 0),
      };
    });
  }, [genres, added, filter]);

  const searching = filter.trim().length > 0;
  const totalTracks = added.reduce(
    (acc, playlist) => acc + playlist.track_count,
    0,
  );
  const noMatch = searching && groups.length === 0;
  const openAdd = (genreId: number | null = null) =>
    setAddDialog({ genreId });

  return (
    <section className="admin-panel" aria-label="Nakout playlists">
      <div className="head pl-head">
        <div>
          <h2 className="sec">Nakout playlists</h2>
          <p className="sub">
            {added.length} {added.length === 1 ? "Nakout playlist" : "Nakout playlists"}{" "}
            · {totalTracks} tracks across {genres.length} genres. Sync pulls
            the latest tracks from YouTube.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => openAdd()}
        >
          + Add Nakout playlist
        </button>
      </div>

      <div className="head pl-list-head">
        <h3 className="ttl">By genre</h3>
        <input
          type="search"
          className="filter-input"
          aria-label="Search Nakout playlists"
          placeholder="Search Nakout playlists…"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
        />
      </div>

      {addedError && (
        <p className="error banner" role="alert">
          {addedError}
        </p>
      )}

      {genres.length === 0 ? (
        <div className="empty">
          Create a genre first, then add Nakout playlists to it.{" "}
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => onJump?.("genres")}
          >
            Go to Genres
          </button>
        </div>
      ) : noMatch ? (
        <div className="empty">
          No Nakout playlists match “{filter.trim()}”.
        </div>
      ) : (
        <div className="groups">
          {groups.map((group) => (
            <section
              key={group.genre.id}
              className="group"
              style={
                { "--gc": group.genre.color || "var(--amber)" } as CSSProperties
              }
            >
              <div className="ghead">
                <i className="dot big" aria-hidden="true" />
                <b>{group.genre.name}</b>
                <span className="mono">
                  {group.items.length}{" "}
                  {group.items.length === 1
                    ? "Nakout playlist"
                    : "Nakout playlists"}{" "}
                  · {group.tracks} tracks
                </span>
                <span className="sp" />
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  aria-label={`Add a Nakout playlist to ${group.genre.name}`}
                  onClick={() => openAdd(group.genre.id)}
                >
                  + Add
                </button>
                {group.items.length > 0 && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={busyGroup === group.genre.id || syncingIds.length > 0}
                    onClick={() => void syncGroup(group)}
                  >
                    Sync all
                  </button>
                )}
              </div>
              {group.items.length === 0 ? (
                <div className="gempty">
                  <span>No Nakout playlists yet.</span>{" "}
                  <button
                    type="button"
                    className="btn-link"
                    onClick={() => openAdd(group.genre.id)}
                  >
                    Add one
                  </button>
                </div>
              ) : (
                group.items.map((playlist) => {
                  const title = playlist.label || "Nakout playlist";
                  const syncing = syncingIds.includes(playlist.id);
                  return (
                    <div
                      key={playlist.id}
                      className={flashId === playlist.id ? "prow flash" : "prow"}
                    >
                      <div className="pm">
                        <a
                          className="pid"
                          href={`https://www.youtube.com/playlist?list=${encodeURIComponent(
                            playlist.youtube_playlist_id,
                          )}`}
                          target="_blank"
                          rel="noreferrer"
                          title={`YouTube playlist ${playlist.youtube_playlist_id}`}
                        >
                          {title}
                        </a>
                        {syncing ? (
                          <span className="chip">
                            <i className="spin" aria-hidden="true" />
                            Syncing
                          </span>
                        ) : (
                          <>
                            <span className="chip">
                              {playlist.track_count} tracks
                            </span>
                            <span className="mono">
                              Synced {timeAgo(playlist.synced_at)}
                            </span>
                          </>
                        )}
                      </div>
                      <div className="act">
                        <select
                          aria-label={`Genre for ${title}`}
                          value={String(playlist.genre_id)}
                          disabled={busyGroup !== null}
                          onChange={(event) =>
                            void movePlaylist(
                              playlist,
                              Number(event.target.value),
                            )
                          }
                        >
                          {genres.map((genre) => (
                            <option key={genre.id} value={genre.id}>
                              {genre.name}
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          disabled={syncing || busyGroup !== null}
                          onClick={() => void syncOne(playlist.id)}
                        >
                          Sync
                        </button>
                        <button
                          type="button"
                          className="btn btn-danger btn-sm"
                          onClick={() => setPendingRemove(playlist)}
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </section>
          ))}
        </div>
      )}

      {pendingRemove && (
        <ConfirmDialog
          title="Remove Nakout playlist"
          message={`Remove “${
            pendingRemove.label || "Nakout playlist"
          }” from ${pendingRemove.genre_name}? Its tracks stay in the Library.`}
          confirmLabel="Remove"
          danger
          onConfirm={() => {
            const id = pendingRemove.id;
            setPendingRemove(null);
            void remove(id);
          }}
          onCancel={() => setPendingRemove(null)}
        />
      )}

      {addDialog && (
        <AddPlaylistDialog
          key={addDialog.genreId ?? "any"}
          genres={genres}
          lockedGenreId={addDialog.genreId}
          onClose={() => setAddDialog(null)}
          onAdded={async () => {
            await loadAdded();
            await onGenresChanged();
          }}
          onSchedule={(genreId) => {
            setAddDialog(null);
            onJump?.("schedule", { scheduleGenre: genreId });
          }}
        />
      )}
    </section>
  );
}
