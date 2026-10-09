import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { messageFor } from "../../utils/errors";
import { ConfirmDialog } from "../ConfirmDialog";
import type {
  AddedPlaylist,
  ChannelPlaylist,
  ChannelSource,
  Genre,
} from "../../types";
import { GenreSelect } from "./GenreSelect";

interface Props {
  genres: Genre[];
  onGenresChanged: () => Promise<void> | void;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
  onCountChange?: (count: number) => void;
  /** Genre id preset by a cross-tab jump from the Genres panel (consumed in task 7). */
  initialGenre?: number | null;
  /** Fired when the panel has consumed its `initialGenre` intent. */
  onIntentConsumed?: () => void;
}

export function PlaylistsPanel({
  genres,
  onGenresChanged,
  onNotice,
  onError,
  onCountChange,
}: Props) {
  const [added, setAdded] = useState<AddedPlaylist[]>([]);
  const [addedError, setAddedError] = useState("");

  const [addGenre, setAddGenre] = useState("");
  const [url, setUrl] = useState("");

  const [channel, setChannel] = useState<ChannelSource | null>(null);
  const [channelInput, setChannelInput] = useState("");
  const [channelError, setChannelError] = useState("");
  const [channelPlaylists, setChannelPlaylists] = useState<ChannelPlaylist[]>(
    [],
  );
  const [playlistError, setPlaylistError] = useState("");
  const [genreById, setGenreById] = useState<Record<string, string>>({});
  const [filter, setFilter] = useState("");
  const [pendingRemove, setPendingRemove] = useState<AddedPlaylist | null>(
    null,
  );

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

  const reportResult = (result: { synced: number; sync_error: string | null }) => {
    onNotice(
      result.sync_error
        ? `Playlist saved, but sync failed: ${result.sync_error}`
        : `Playlist synced (${result.synced} tracks).`,
    );
  };

  const addByUrl = async () => {
    try {
      reportResult(await api.createPlaylist(Number(addGenre), url, ""));
      setUrl("");
      await onGenresChanged();
      await loadAdded();
    } catch (err) {
      onError(messageFor(err));
    }
  };

  const refresh = async (id: number) => {
    try {
      const result = await api.refreshPlaylist(id);
      onNotice(`Refreshed playlist (${result.synced} tracks).`);
      await loadAdded();
      await onGenresChanged();
    } catch (err) {
      onError(messageFor(err));
    }
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
      setPlaylistError("");
    } catch (err) {
      setChannelError(messageFor(err));
    }
  };

  const addFromChannel = async (playlistId: string) => {
    const genreId = Number(genreById[playlistId] ?? "");
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

  const filtered = added.filter((p) => {
    const q = filter.trim().toLowerCase();
    if (!q) return true;
    return (
      p.genre_name.toLowerCase().includes(q) ||
      (p.label || "").toLowerCase().includes(q) ||
      p.youtube_playlist_id.toLowerCase().includes(q)
    );
  });

  return (
    <section className="admin-panel" aria-label="Playlists">
      <div className="playlists-layout">
        <div className="playlists-main">
          <div className="panel-head">
            <h2>Added playlists</h2>
            {added.length > 0 && (
              <input
                type="search"
                className="filter-input"
                aria-label="Filter playlists"
                placeholder="Filter by genre or playlist…"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              />
            )}
          </div>
          {addedError && (
            <p className="error banner" role="alert">
              {addedError}
            </p>
          )}
          {added.length === 0 && !addedError && (
            <p className="muted">No playlists added yet.</p>
          )}
          {added.length > 0 && filtered.length === 0 && (
            <p className="muted">No playlists match your filter.</p>
          )}
          <ul className="added-playlists">
            {filtered.map((p) => (
              <li key={p.id}>
                <div className="pl-main">
                  <span className="pl-genre">{p.genre_name}</span>
                  <span className="pl-id">
                    {p.label || p.youtube_playlist_id}
                  </span>
                  <span className="count-pill">{p.track_count} tracks</span>
                </div>
                <div className="pl-actions">
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => refresh(p.id)}
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
              </li>
            ))}
          </ul>
        </div>

        <aside className="playlists-side">
          <div className="card side-block">
            <h2>Add playlist by URL</h2>
            <GenreSelect
              label="Playlist genre"
              genres={genres}
              value={addGenre}
              onChange={setAddGenre}
            />
            <label className="field">
              YouTube playlist URL
              <input
                aria-label="YouTube playlist URL"
                placeholder="YouTube playlist URL"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </label>
            <div className="form-actions">
              <button
                type="button"
                className="btn btn-primary"
                onClick={addByUrl}
                disabled={!addGenre || !url}
              >
                Add playlist
              </button>
            </div>
          </div>
        </aside>
      </div>

      <div className="card channel-block">
        <h2>Browse channel playlists</h2>
        {channel?.channel_id ? (
          <div>
            <div className="panel-head channel-head">
              <span className="channel-name">
                {channel.title || channel.channel_id}
              </span>
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
                onClick={loadChannel}
              >
                Refresh
              </button>
            </div>
            {playlistError && (
              <p className="error banner" role="alert">
                {playlistError}
              </p>
            )}
            {channelPlaylists.length === 0 && !playlistError && (
              <p className="muted">No playlists found.</p>
            )}
            <div className="channel-scroll">
              <ul className="channel-grid">
                {channelPlaylists.map((p) => (
                  <li key={p.youtube_playlist_id} className="channel-card">
                    {p.thumbnail_url && <img src={p.thumbnail_url} alt="" />}
                    <span className="ch-title">{p.title}</span>
                    <span className="count-pill">({p.item_count} tracks)</span>
                    {p.already_added ? (
                      <span className="added-badge">Added</span>
                    ) : (
                      <>
                        <select
                          aria-label={`Genre for ${p.title}`}
                          value={genreById[p.youtube_playlist_id] ?? ""}
                          onChange={(e) =>
                            setGenreById((prev) => ({
                              ...prev,
                              [p.youtube_playlist_id]: e.target.value,
                            }))
                          }
                        >
                          <option value="">Select a genre…</option>
                          {genres.map((s) => (
                            <option key={s.slug} value={s.id}>
                              {s.name}
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          className="btn btn-primary btn-sm"
                          onClick={() => addFromChannel(p.youtube_playlist_id)}
                          disabled={!genreById[p.youtube_playlist_id]}
                        >
                          Add
                        </button>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            </div>
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
                onClick={saveChannel}
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
