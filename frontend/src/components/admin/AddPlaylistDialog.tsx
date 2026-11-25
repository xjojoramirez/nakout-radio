import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, MouseEvent } from "react";
import { createPortal } from "react-dom";
import { api } from "../../api/client";
import { messageFor } from "../../utils/errors";
import { parsePlaylistId } from "../../utils/playlist";
import { cssCover } from "../../utils/profile";
import { GenreChipRadio } from "./GenreChipRadio";
import type {
  AddedPlaylist,
  ChannelPlaylist,
  ChannelSource,
  Genre,
} from "../../types";

type Mode = "link" | "channel";

interface AddedResult {
  id: number;
  youtube_playlist_id: string;
  synced: number;
  sync_error: string | null;
}

interface Props {
  genres: Genre[];
  /** When set, the playlist is added straight to this genre. */
  lockedGenreId?: number | null;
  onClose: () => void;
  onAdded: (genreId: number, result: AddedResult) => Promise<void> | void;
  onSchedule?: (genreId: number) => void;
}

interface Success {
  genreId: number;
  genreName: string;
  synced: number;
  syncError: string | null;
}

export function AddPlaylistDialog({
  genres,
  lockedGenreId = null,
  onClose,
  onAdded,
  onSchedule,
}: Props) {
  const locked = lockedGenreId != null;
  const [mode, setMode] = useState<Mode>("link");
  const [genreId, setGenreId] = useState<number | null>(lockedGenreId);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState("");
  const [success, setSuccess] = useState<Success | null>(null);
  const [added, setAdded] = useState<AddedPlaylist[]>([]);

  const [channel, setChannel] = useState<ChannelSource | null>(null);
  const [channelChecked, setChannelChecked] = useState(false);
  const [channelInput, setChannelInput] = useState("");
  const [channelError, setChannelError] = useState("");
  const [channelLoading, setChannelLoading] = useState(false);
  const [channelPlaylists, setChannelPlaylists] = useState<ChannelPlaylist[]>([]);
  const [genreById, setGenreById] = useState<Record<string, number>>({});
  const [search, setSearch] = useState("");
  const [addingId, setAddingId] = useState<string | null>(null);
  const [lastAdded, setLastAdded] = useState<{
    genreId: number;
    genreName: string;
  } | null>(null);

  const linkRef = useRef<HTMLInputElement | null>(null);
  const channelLoaded = useRef(false);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const rows = await api.listPlaylists();
        if (active && Array.isArray(rows)) setAdded(rows);
      } catch {
        /* duplicate detection is a convenience; the add call still validates */
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    linkRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const selectedGenre =
    genres.find((g) => g.id === genreId) ?? null;

  const loadChannel = async () => {
    setChannelLoading(true);
    try {
      const source = await api.getChannelSource();
      setChannel(source);
      if (source.channel_id) {
        setChannelPlaylists(await api.listChannelPlaylists());
        setChannelError("");
      } else {
        setChannelPlaylists([]);
      }
    } catch (err) {
      setChannelError(messageFor(err));
    } finally {
      setChannelLoading(false);
      setChannelChecked(true);
    }
  };

  useEffect(() => {
    if (mode !== "channel" || channelLoaded.current) return;
    channelLoaded.current = true;
    void loadChannel();
  }, [mode]);

  const urlTrimmed = url.trim();
  const parsedId = urlTrimmed ? parsePlaylistId(urlTrimmed) : null;
  const duplicate = parsedId
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
    if (duplicate) {
      return {
        className: "hint err",
        text: `This is already a Nakout playlist under ${duplicate.genre_name}.`,
      };
    }
    return {
      className: "hint ok",
      text: `Playlist ID found: ${parsedId}`,
    };
  })();

  const why = (() => {
    if (!genreId) return "Choose a genre to continue.";
    if (!urlTrimmed) return "Paste a YouTube playlist link to continue.";
    if (!parsedId) return "Fix the link to continue.";
    if (duplicate) return "This playlist is already in the Studio.";
    return "";
  })();

  const addByUrl = async () => {
    if (!genreId || !parsedId || duplicate || busy) return;
    const genreName =
      genres.find((g) => g.id === genreId)?.name ?? "this genre";
    setBusy(true);
    setFormError("");
    try {
      const result = await api.createPlaylist(genreId, urlTrimmed, "");
      setSuccess({
        genreId,
        genreName,
        synced: result.synced,
        syncError: result.sync_error,
      });
      setUrl("");
      try {
        setAdded(await api.listPlaylists());
      } catch {
        /* keep going; the success panel is the source of truth here */
      }
      await onAdded(genreId, result);
    } catch (err) {
      setFormError(messageFor(err));
    } finally {
      setBusy(false);
    }
  };

  const saveChannel = async () => {
    try {
      const source = await api.setChannelSource(channelInput.trim());
      setChannel(source);
      setChannelInput("");
      setChannelPlaylists(await api.listChannelPlaylists());
      setChannelError("");
    } catch (err) {
      setChannelError(messageFor(err));
    }
  };

  const addFromChannel = async (playlist: ChannelPlaylist) => {
    const targetId = lockedGenreId ?? genreById[playlist.youtube_playlist_id];
    if (!targetId) {
      setChannelError("Choose a genre for this playlist first.");
      return;
    }
    const genreName =
      genres.find((g) => g.id === targetId)?.name ?? "this genre";
    setAddingId(playlist.youtube_playlist_id);
    setChannelError("");
    try {
      const result = await api.createPlaylist(
        targetId,
        `https://www.youtube.com/playlist?list=${playlist.youtube_playlist_id}`,
        "",
      );
      setAdded((prev) => [
        ...prev.filter(
          (p) => p.youtube_playlist_id !== playlist.youtube_playlist_id,
        ),
        {
          id: result.id,
          genre_id: targetId,
          genre_name: genreName,
          youtube_playlist_id: playlist.youtube_playlist_id,
          label: "",
          track_count: result.synced,
          synced_at: new Date().toISOString(),
        },
      ]);
      setLastAdded({ genreId: targetId, genreName });
      await onAdded(targetId, result);
    } catch (err) {
      setChannelError(messageFor(err));
    } finally {
      setAddingId(null);
    }
  };

  const filteredChannel = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return channelPlaylists;
    return channelPlaylists.filter((p) => p.title.toLowerCase().includes(q));
  }, [channelPlaylists, search]);

  const closeOnOverlay = (event: MouseEvent<HTMLDivElement>) => {
    if (event.target === event.currentTarget) onClose();
  };

  const title = locked && selectedGenre
    ? `Add to ${selectedGenre.name}`
    : "Add a Nakout playlist";

  return createPortal(
    <div className="modal-overlay" onMouseDown={closeOnOverlay}>
      <div
        className="modal-card addpl-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-playlist-title"
      >
        <div className="addpl-head">
          <div>
            <h2 id="add-playlist-title" className="modal-title">
              {title}
            </h2>
            <p className="addpl-sub">
              {locked && selectedGenre
                ? `Add a YouTube playlist to ${selectedGenre.name}.`
                : "Turn a YouTube playlist into a Nakout playlist."}
            </p>
          </div>
          <button
            type="button"
            className="addpl-close"
            aria-label="Close add playlist dialog"
            onClick={onClose}
          >
            &times;
          </button>
        </div>

        {success ? (
          <div className="addpl-success">
            <span className="addpl-success-mark" aria-hidden="true">
              ✓
            </span>
            <div>
              <b>Nakout playlist added to {success.genreName}.</b>
              <p>
                {success.syncError
                  ? `Saved, but the YouTube sync failed: ${success.syncError}. Retry from Nakout playlists.`
                  : `Synced ${success.synced} ${
                      success.synced === 1 ? "track" : "tracks"
                    } so far.`}
              </p>
            </div>
            <div className="addpl-success-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  setSuccess(null);
                  setTimeout(() => linkRef.current?.focus(), 0);
                }}
              >
                Add another
              </button>
              {onSchedule && (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => onSchedule(success.genreId)}
                >
                  Schedule this genre
                </button>
              )}
              <button
                type="button"
                className="btn btn-secondary"
                onClick={onClose}
              >
                Done
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="seg addpl-modes" role="group" aria-label="Add mode">
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
                From the Nakout channel
              </button>
            </div>

            {mode === "link" ? (
              <form
                className="addpl-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  void addByUrl();
                }}
              >
                <label className="field">
                  YouTube playlist link
                  <input
                    ref={linkRef}
                    aria-label="YouTube playlist link"
                    placeholder="Paste a link like youtube.com/playlist?list=…"
                    inputMode="url"
                    value={url}
                    onChange={(event) => {
                      setUrl(event.target.value);
                      setFormError("");
                    }}
                  />
                </label>
                <div className={hint.className}>{hint.text}</div>

                {locked && selectedGenre ? (
                  <div className="addpl-dest">
                    <span className="addpl-dest-label">Will play in</span>
                    <span
                      className="gchip addpl-dest-chip"
                      style={
                        {
                          "--gc": selectedGenre.color || "var(--amber)",
                        } as CSSProperties
                      }
                    >
                      <i className="dot" aria-hidden="true" />
                      {selectedGenre.name}
                    </span>
                  </div>
                ) : (
                  <>
                    <div className="lab">Which genre does it play in?</div>
                    <GenreChipRadio
                      label="Genre"
                      genres={genres}
                      value={genreId}
                      onChange={(id) => {
                        setGenreId(id);
                        setFormError("");
                      }}
                    />
                  </>
                )}

                {formError && (
                  <p className="error banner" role="alert">
                    {formError}
                  </p>
                )}
                {why && <div className="addpl-why">{why}</div>}
                <div className="addpl-footer">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={onClose}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={!genreId || !parsedId || Boolean(duplicate) || busy}
                  >
                    {busy
                      ? "Adding…"
                      : selectedGenre
                        ? `Add to ${selectedGenre.name}`
                        : "Add Nakout playlist"}
                  </button>
                </div>
              </form>
            ) : (
              <div className="addpl-channel">
                {channelError && (
                  <p className="error banner" role="alert">
                    {channelError}
                  </p>
                )}
                {!channelChecked ? (
                  <p className="hint">Checking the Nakout channel…</p>
                ) : channel?.channel_id ? (
                  <>
                    <div className="addpl-channel-head">
                      <div>
                        <b>{channel.title || channel.channel_id}</b>
                        <span className="mono">Nakout channel</span>
                      </div>
                      <div className="addpl-channel-actions">
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => {
                            setChannel(null);
                            setChannelPlaylists([]);
                            setChannelError("");
                          }}
                        >
                          Change
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          disabled={channelLoading}
                          onClick={() => void loadChannel()}
                        >
                          {channelLoading ? "Reloading…" : "Reload list"}
                        </button>
                      </div>
                    </div>
                    {locked && selectedGenre && (
                      <div className="addpl-dest">
                        <span className="addpl-dest-label">Will play in</span>
                        <span
                          className="gchip addpl-dest-chip"
                          style={
                            {
                              "--gc": selectedGenre.color || "var(--amber)",
                            } as CSSProperties
                          }
                        >
                          <i className="dot" aria-hidden="true" />
                          {selectedGenre.name}
                        </span>
                      </div>
                    )}
                    {lastAdded && (
                      <div className="addpl-channel-note" role="status">
                        Added to {lastAdded.genreName}.
                        {onSchedule && (
                          <button
                            type="button"
                            className="btn-link"
                            onClick={() => onSchedule(lastAdded.genreId)}
                          >
                            Schedule this genre
                          </button>
                        )}
                      </div>
                    )}
                    <label className="field addpl-search">
                      Search the channel
                      <input
                        type="search"
                        aria-label="Search channel playlists"
                        placeholder="Search playlists…"
                        value={search}
                        onChange={(event) => setSearch(event.target.value)}
                      />
                    </label>
                    {channelLoading ? (
                      <p className="hint">Loading channel playlists…</p>
                    ) : filteredChannel.length === 0 ? (
                      <p className="hint">
                        {search.trim()
                          ? `No channel playlists match “${search.trim()}”.`
                          : "No playlists found on this channel."}
                      </p>
                    ) : (
                      <div className="browse addpl-browse">
                        {filteredChannel.map((playlist) => {
                          const addedTo = added.find(
                            (p) =>
                              p.youtube_playlist_id ===
                              playlist.youtube_playlist_id,
                          );
                          return (
                            <div
                              className="pcard"
                              key={playlist.youtube_playlist_id}
                            >
                              <div className="pc">
                                <img
                                  src={playlist.thumbnail_url}
                                  alt=""
                                  style={
                                    playlist.thumbnail_url
                                      ? undefined
                                      : { backgroundImage: cssCover(playlist.title) }
                                  }
                                />
                              </div>
                              <b>{playlist.title}</b>
                              <span className="chip">
                                {playlist.item_count} tracks
                              </span>
                              {addedTo ? (
                                <span className="added-badge">
                                  Added to <b>{addedTo.genre_name}</b>
                                </span>
                              ) : locked && selectedGenre ? (
                                <button
                                  type="button"
                                  className="btn btn-primary btn-sm"
                                  disabled={
                                    addingId === playlist.youtube_playlist_id
                                  }
                                  onClick={() => void addFromChannel(playlist)}
                                >
                                  {addingId === playlist.youtube_playlist_id
                                    ? "Adding…"
                                    : "Add"}
                                </button>
                              ) : (
                                <>
                                  <select
                                    aria-label={`Genre for ${playlist.title}`}
                                    value={String(
                                      genreById[playlist.youtube_playlist_id] ??
                                        "",
                                    )}
                                    onChange={(event) =>
                                      setGenreById((prev) => ({
                                        ...prev,
                                        [playlist.youtube_playlist_id]: Number(
                                          event.target.value,
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
                                    disabled={
                                      !genreById[
                                        playlist.youtube_playlist_id
                                      ] ||
                                      addingId === playlist.youtube_playlist_id
                                    }
                                    onClick={() => void addFromChannel(playlist)}
                                  >
                                    {addingId === playlist.youtube_playlist_id
                                      ? "Adding…"
                                      : "Add"}
                                  </button>
                                </>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </>
                ) : (
                  <div className="addpl-channel-setup">
                    <p className="addpl-sub">
                      Connect the YouTube channel that hosts the Nakout
                      playlists, then pick one to add.
                    </p>
                    <form
                      onSubmit={(event) => {
                        event.preventDefault();
                        void saveChannel();
                      }}
                    >
                      <label className="field">
                        YouTube channel
                        <input
                          aria-label="YouTube channel"
                          placeholder="@handle or channel URL"
                          value={channelInput}
                          onChange={(event) =>
                            setChannelInput(event.target.value)
                          }
                        />
                      </label>
                      <div className="addpl-footer">
                        <button
                          type="button"
                          className="btn btn-secondary"
                          onClick={onClose}
                        >
                          Cancel
                        </button>
                        <button
                          type="submit"
                          className="btn btn-primary"
                          disabled={!channelInput.trim()}
                        >
                          Connect channel
                        </button>
                      </div>
                    </form>
                  </div>
                )}
                {channel?.channel_id && (
                  <div className="addpl-footer">
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={onClose}
                    >
                      Done
                    </button>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>,
    document.body,
  );
}
