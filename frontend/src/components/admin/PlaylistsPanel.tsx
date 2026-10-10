import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { api } from "../../api/client";
import { messageFor } from "../../utils/errors";
import { timeAgo } from "../../utils/format";
import { cssCover } from "../../utils/profile";
import { ConfirmDialog } from "../ConfirmDialog";
import { GenreChipRadio } from "./GenreChipRadio";
import type {
  AddedPlaylist,
  ChannelPlaylist,
  ChannelSource,
  Genre,
} from "../../types";

interface Props {
  genres: Genre[];
  onGenresChanged: () => Promise<void> | void;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
  onCountChange?: (count: number) => void;
  /** Genre id preset by a cross-tab jump from the Genres panel. */
  initialGenre?: number | null;
  /** Fired when the panel has consumed its `initialGenre` intent. */
  onIntentConsumed?: () => void;
  /** Cross-tab navigation, mirroring GenresPanel. */
  onJump?: (
    tab: string,
    intent?: { playlistsGenre?: number; scheduleGenre?: number },
  ) => void;
}

function parsePlaylistId(value: string): string | null {
  const match =
    value.match(/[?&]list=([\w-]+)/) ?? value.match(/^(PL[\w-]{6,})$/);
  return match ? match[1] : null;
}

type AddMode = "link" | "channel";

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
  initialGenre,
  onIntentConsumed,
  onJump,
}: Props) {
  const [added, setAdded] = useState<AddedPlaylist[]>([]);
  const [addedError, setAddedError] = useState("");

  const [mode, setMode] = useState<AddMode>("link");
  const [addGenre, setAddGenre] = useState<number | null>(null);
  const [url, setUrl] = useState("");

  const [channel, setChannel] = useState<ChannelSource | null>(null);
  const [channelInput, setChannelInput] = useState("");
  const [channelError, setChannelError] = useState("");
  const [channelPlaylists, setChannelPlaylists] = useState<ChannelPlaylist[]>(
    [],
  );
  const [playlistError, setPlaylistError] = useState("");
  const [genreById, setGenreById] = useState<Record<string, number>>({});
  const [filter, setFilter] = useState("");
  const [syncingIds, setSyncingIds] = useState<number[]>([]);
  const [busyGroup, setBusyGroup] = useState<number | null>(null);
  const [pendingRemove, setPendingRemove] = useState<AddedPlaylist | null>(
    null,
  );
  const [flashId, setFlashId] = useState<number | null>(null);

  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const consumedIntent = useRef(false);

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

  const loadChannel = useCallback(async () => {
    try {
      const source = await api.getChannelSource();
      setChannel(source);
      if (source.channel_id) {
        setChannelPlaylists(await api.listChannelPlaylists());
        setPlaylistError("");
      } else {
        setChannelPlaylists([]);
      }
    } catch (err) {
      setPlaylistError(messageFor(err));
    }
  }, []);

  useEffect(() => {
    loadAdded();
    loadChannel();
  }, [loadAdded, loadChannel]);

  useEffect(() => {
    if (initialGenre != null && !consumedIntent.current) {
      consumedIntent.current = true;
      setMode("link");
      setAddGenre(initialGenre);
      onIntentConsumed?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const reportResult = (result: { synced: number; sync_error: string | null }) => {
    onNotice(
      result.sync_error
        ? `Playlist saved, but sync failed: ${result.sync_error}`
        : `Playlist synced (${result.synced} tracks).`,
    );
  };

  const urlTrimmed = url.trim();
  const parsedId = urlTrimmed ? parsePlaylistId(urlTrimmed) : null;
  const addToGenre = parsedId
    ? added.find((p) => p.youtube_playlist_id === parsedId)
    : undefined;
  const hint = (() => {
    if (!urlTrimmed) {
      return {
        className: "hint",
        text: "Open the playlist on YouTube, copy the address and paste it here.",
      };
    }
    if (!parsedId) {
      return {
        className: "hint err",
        text: "That doesn't look like a playlist link. It should contain list= followed by the playlist ID.",
      };
    }
    if (addToGenre) {
      return {
        className: "hint err",
        text: `This playlist is already added under ${addToGenre.genre_name}.`,
      };
    }
    return { className: "hint ok", text: `Playlist ID found: ${parsedId}` };
  })();

  const addByUrl = async () => {
    if (!addGenre || !parsedId || addToGenre) return;
    try {
      const result = await api.createPlaylist(addGenre, urlTrimmed, "");
      reportResult(result);
      setUrl("");
      setAddGenre(null);
      const newId = result.id;
      await onGenresChanged();
      await loadAdded();
      flash(newId);
    } catch (err) {
      onError(messageFor(err));
    }
  };

  const movePlaylist = async (p: AddedPlaylist, genreId: number) => {
    if (genreId === p.genre_id) return;
    try {
      await api.updatePlaylist(p.id, { genre_id: genreId });
      const target = genres.find((g) => g.id === genreId);
      onNotice(`Moved to ${target?.name ?? String(genreId)}.`);
      await loadAdded();
      await onGenresChanged();
      flash(p.id);
    } catch (err) {
      await loadAdded();
      await onGenresChanged();
      onError(messageFor(err));
    }
  };

  const refresh = async (id: number) => {
    if (syncingIds.includes(id)) return;
    setSyncingIds((ids) => [...ids, id]);
    try {
      const result = await api.refreshPlaylist(id);
      onNotice(`Refreshed playlist (${result.synced} tracks).`);
      await loadAdded();
      await onGenresChanged();
    } catch (err) {
      onError(messageFor(err));
    } finally {
      setSyncingIds((ids) => ids.filter((x) => x !== id));
    }
  };

  const refreshGroup = async (g: Group) => {
    if (!g.items.length || busyGroup !== null) return;
    const ids = g.items.map((p) => p.id);
    setBusyGroup(g.genre.id);
    setSyncingIds((prev) => Array.from(new Set([...prev, ...ids])));
    onNotice(`Refreshing ${g.genre.name}...`);
    const settled = await Promise.allSettled(
      ids.map((id) => api.refreshPlaylist(id)),
    );
    const ok = settled.filter(
      (r): r is PromiseFulfilledResult<{ id: number; synced: number }> =>
        r.status === "fulfilled",
    );
    const failed = settled.find(
      (r): r is PromiseRejectedResult => r.status === "rejected",
    );
    if (failed) {
      onError(messageFor(failed.reason));
    } else {
      const synced = ok.reduce((acc, r) => acc + r.value.synced, 0);
      onNotice(
        `Refreshed ${g.genre.name} (${ok.length} ${ok.length === 1 ? "playlist" : "playlists"}, ${synced} tracks).`,
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
      onNotice("Playlist removed.");
      await loadAdded();
      await onGenresChanged();
    } catch (err) {
      onError(messageFor(err));
    }
  };

  const saveChannel = async () => {
    try {
      const source = await api.setChannelSource(channelInput.trim());
      setChannel(source);
      setChannelInput("");
      setChannelPlaylists(await api.listChannelPlaylists());
      setChannelError("");
      setPlaylistError("");
    } catch (err) {
      setChannelError(messageFor(err));
    }
  };

  const addFromChannel = async (playlistId: string) => {
    const genreId = genreById[playlistId];
    if (!genreId) {
      onError("Select a genre first.");
      return;
    }
    try {
      reportResult(
        await api.createPlaylist(
          genreId,
          `https://www.youtube.com/playlist?list=${playlistId}`,
          "",
        ),
      );
      await onGenresChanged();
      await loadAdded();
      await loadChannel();
    } catch (err) {
      onError(messageFor(err));
    }
  };

  const groups = useMemo<Group[]>(() => {
    const q = filter.trim().toLowerCase();
    const matches = (g: Genre, p: AddedPlaylist) =>
      !q ||
      p.genre_name.toLowerCase().includes(q) ||
      (p.label || "").toLowerCase().includes(q) ||
      p.youtube_playlist_id.toLowerCase().includes(q);
    const visible = genres.filter(
      (g) => !q || added.some((p) => p.genre_id === g.id && matches(g, p)),
    );
    return visible.map((g) => {
      const items = added.filter((p) => p.genre_id === g.id && matches(g, p));
      return {
        genre: g,
        items,
        tracks: items.reduce((acc, p) => acc + p.track_count, 0),
      };
    });
  }, [genres, added, filter]);

  const searching = filter.trim().length > 0;
  const totalTracks = added.reduce((acc, p) => acc + p.track_count, 0);
  const noMatch = searching && groups.length === 0;

  return (
    <section className="admin-panel" aria-label="Playlists">
      <div>
        <h2 className="sec">Playlists</h2>
        <p className="sub">
          {added.length} {added.length === 1 ? "playlist" : "playlists"} ·{" "}
          {totalTracks} tracks across {genres.length} genres. Playlists are
          re-synced with YouTube when you refresh them.
        </p>
      </div>

      <div className="card">
        <div className="head">
          <h3 className="ttl">Add a playlist</h3>
          <div className="seg" role="group" aria-label="Add mode">
            <button
              type="button"
              aria-pressed={mode === "link"}
              onClick={() => setMode("link")}
            >
              Paste a link
            </button>
            <button
              type="button"
              aria-pressed={mode === "channel"}
              onClick={() => setMode("channel")}
            >
              From your channel
            </button>
          </div>
        </div>

        {mode === "link" ? (
          <form
            className="addlink"
            onSubmit={(e) => {
              e.preventDefault();
              void addByUrl();
            }}
          >
            <label className="field">
              YouTube playlist link
              <input
                aria-label="YouTube playlist link"
                placeholder="Paste a link like youtube.com/playlist?list=…"
                inputMode="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </label>
            <div className={hint.className}>{hint.text}</div>
            <GenreChipRadio
              label="Genre"
              genres={genres}
              value={addGenre}
              onChange={setAddGenre}
            />
            <div>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={!addGenre || !parsedId || Boolean(addToGenre)}
              >
                Add playlist
              </button>
            </div>
          </form>
        ) : channel?.channel_id ? (
          <div className="addchannel">
            <div className="head">
              <b>{channel.title || channel.channel_id}</b>
              <span className="mono">channel playlists</span>
              <span className="sp" />
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => {
                  setChannel(null);
                  setChannelError("");
                }}
              >
                Change
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => void loadChannel()}
              >
                Refresh list
              </button>
            </div>
            {playlistError && (
              <p className="error banner" role="alert">
                {playlistError}
              </p>
            )}
            {channelPlaylists.length === 0 && !playlistError ? (
              <p className="muted">No playlists found.</p>
            ) : (
              <div className="browse">
                {channelPlaylists.map((p) => {
                  const addedTo = added.find(
                    (a) => a.youtube_playlist_id === p.youtube_playlist_id,
                  );
                  return (
                    <div
                      key={p.youtube_playlist_id}
                      className="pcard"
                    >
                      <div className="pc">
                        <img
                          src={p.thumbnail_url}
                          alt=""
                          style={
                            p.thumbnail_url
                              ? undefined
                              : { backgroundImage: cssCover(p.title) }
                          }
                        />
                      </div>
                      <b>{p.title}</b>
                      <span className="chip">{p.item_count} tracks</span>
                      {addedTo ? (
                        <span className="added-badge">
                          Added to <b>{addedTo.genre_name}</b>
                        </span>
                      ) : (
                        <>
                          <select
                            aria-label={`Genre for ${p.title}`}
                            value={String(genreById[p.youtube_playlist_id] ?? "")}
                            onChange={(e) =>
                              setGenreById((prev) => ({
                                ...prev,
                                [p.youtube_playlist_id]: Number(
                                  e.target.value,
                                ),
                              }))
                            }
                          >
                            <option value="">Add to a genre…</option>
                            {genres.map((g) => (
                              <option key={g.id} value={g.id}>
                                {g.name}
                              </option>
                            ))}
                          </select>
                          <button
                            type="button"
                            className="btn btn-primary btn-sm"
                            onClick={() =>
                              void addFromChannel(p.youtube_playlist_id)
                            }
                            disabled={!genreById[p.youtube_playlist_id]}
                          >
                            Add
                          </button>
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ) : (
          <div className="channel-setup">
            <label className="field">
              YouTube channel
              <input
                aria-label="YouTube channel"
                placeholder="@handle or channel URL"
                value={channelInput}
                onChange={(e) => setChannelInput(e.target.value)}
              />
            </label>
            <div className="form-actions">
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => void saveChannel()}
                disabled={!channelInput.trim()}
              >
                Save channel
              </button>
            </div>
            {channelError && (
              <p className="error banner" role="alert">
                {channelError}
              </p>
            )}
          </div>
        )}
      </div>

      <div className="head">
        <h3 className="ttl">Your playlists</h3>
        <input
          type="search"
          className="filter-input"
          aria-label="Search playlists"
          placeholder="Search playlists…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>

      {addedError && (
        <p className="error banner" role="alert">
          {addedError}
        </p>
      )}

      {genres.length === 0 ? (
        <div className="empty">
          Create a genre first, then add playlists to it.{" "}
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => onJump?.("genres")}
          >
            Go to Genres
          </button>
        </div>
      ) : noMatch ? (
        <div className="empty">No playlists match "{filter.trim()}".</div>
      ) : (
        <div className="groups">
          {groups.map((g) => (
            <section
              key={g.genre.id}
              className="group"
              style={
                { "--gc": g.genre.color || "var(--amber)" } as CSSProperties
              }
            >
              <div className="ghead">
                <i className="dot big" aria-hidden="true" />
                <b>{g.genre.name}</b>
                <span className="mono">
                  {g.items.length}{" "}
                  {g.items.length === 1 ? "playlist" : "playlists"} · {g.tracks}{" "}
                  tracks
                </span>
                <span className="sp" />
                {g.items.length > 0 && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={
                      busyGroup === g.genre.id || syncingIds.length > 0
                    }
                    onClick={() => void refreshGroup(g)}
                  >
                    Refresh all
                  </button>
                )}
              </div>
              {g.items.length === 0 ? (
                <div className="gempty">
                  <span>No playlists yet.</span>{" "}
                  <button
                    type="button"
                    className="btn-link"
                    onClick={() => {
                      setMode("link");
                      setAddGenre(g.genre.id);
                    }}
                  >
                    Add one
                  </button>
                </div>
              ) : (
                g.items.map((p) => {
                  const title = p.label || p.youtube_playlist_id;
                  const syncing = syncingIds.includes(p.id);
                  return (
                    <div
                      key={p.id}
                      className={flashId === p.id ? "prow flash" : "prow"}
                    >
                      <div className="pm">
                        <a
                          className={
                            p.label ? "pid" : "pid idonly"
                          }
                          href={`https://www.youtube.com/playlist?list=${encodeURIComponent(
                            p.youtube_playlist_id,
                          )}`}
                          target="_blank"
                          rel="noreferrer"
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
                              {p.track_count} tracks
                            </span>
                            <span className="mono">
                              Synced {timeAgo(p.synced_at)}
                            </span>
                          </>
                        )}
                      </div>
                      <div className="act">
                        <select
                          aria-label={`Genre for ${title}`}
                          value={String(p.genre_id)}
                          disabled={busyGroup !== null}
                          onChange={(e) =>
                            void movePlaylist(p, Number(e.target.value))
                          }
                        >
                          {genres.map((x) => (
                            <option key={x.id} value={x.id}>
                              {x.name}
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          disabled={syncing || busyGroup !== null}
                          onClick={() => void refresh(p.id)}
                        >
                          Refresh
                        </button>
                        <button
                          type="button"
                          className="btn btn-danger btn-sm"
                          onClick={() => setPendingRemove(p)}
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
          title="Remove playlist"
          message={`Remove "${pendingRemove.label || pendingRemove.youtube_playlist_id}" and its tracks from ${pendingRemove.genre_name}?`}
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
    </section>
  );
}
