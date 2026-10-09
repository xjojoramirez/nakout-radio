import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { api } from "../../api/client";
import { useBroadcast } from "../../hooks/useBroadcast";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { messageFor } from "../../utils/errors";
import { formatClock, formatDuration } from "../../utils/format";
import { reorder, shuffle } from "../../utils/queue";
import { ConfirmDialog } from "../ConfirmDialog";
import { VUMeter } from "../VUMeter";
import { TurntableDeck } from "../deck/TurntableDeck";
import type { Genre, Track } from "../../types";

interface Props {
  genres: Genre[];
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}

const SOURCE_LABELS: Record<string, string> = {
  schedule: "Schedule",
  default: "Default",
  manual: "Manual",
  none: "Off air",
};

const MOBILE_QUEUE_QUERY = "(max-width: 600px)";

export function NowPlayingPanel({ genres, onNotice, onError }: Props) {
  const isMobileView = useMediaQuery(MOBILE_QUEUE_QUERY);
  const { state, failed, refresh } = useBroadcast();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [loading, setLoading] = useState(false);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [reload, setReload] = useState(0);
  const [pendingTrack, setPendingTrack] = useState<Track | null>(null);
  const queueRef = useRef<HTMLOListElement | null>(null);
  const currentRowRef = useRef<HTMLLIElement | null>(null);
  const didFirstScrollRef = useRef(false);
  const userSelectedRef = useRef(false);

  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const liveGenre = state?.genre ?? null;
  const knownLiveId =
    liveGenre && genres.some((s) => s.id === liveGenre.id)
      ? liveGenre.id
      : null;

  useEffect(() => {
    if (userSelectedRef.current) return;
    if (knownLiveId !== null) {
      setSelectedId(knownLiveId);
      return;
    }
    if (selectedId === null) {
      const initial = genres[0]?.id ?? null;
      if (initial !== null) setSelectedId(initial);
    }
  }, [selectedId, knownLiveId, genres]);

  useEffect(() => {
    if (selectedId === null) {
      setTracks([]);
      return;
    }
    let active = true;
    setLoading(true);
    setTracks([]);
    api
      .genreTracks(selectedId)
      .then((rows) => {
        if (active) setTracks(rows);
      })
      .catch((err) => {
        if (active) onErrorRef.current(messageFor(err));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [selectedId, reload]);

  const currentVideoId =
    state?.genre?.id === selectedId
      ? (state?.track?.youtube_video_id ?? null)
      : null;
  const currentIndex = currentVideoId
    ? tracks.findIndex((t) => t.youtube_video_id === currentVideoId)
    : -1;

  useEffect(() => {
    const list = queueRef.current;
    const row = currentRowRef.current;
    if (!list || !row || currentIndex < 0) return;
    if (isMobileView) {
      if (didFirstScrollRef.current) return;
      didFirstScrollRef.current = true;
      row.scrollIntoView({ block: "start" });
      return;
    }
    list.scrollTop +=
      row.getBoundingClientRect().top - list.getBoundingClientRect().top;
  }, [currentIndex, tracks, loading, isMobileView]);

  const syncAll = async () => {
    try {
      const result = await api.syncAll();
      setReload((n) => n + 1);
      const failedSync = result.results.filter((r) => r.error).length;
      onNotice(
        failedSync === 0
          ? `Synced ${result.results.length} playlist(s).`
          : `Synced ${result.results.length - failedSync} of ${result.results.length} playlist(s); ${failedSync} failed.`,
      );
    } catch (err) {
      onError(messageFor(err));
    }
  };

  const saveOrder = async (next: Track[]) => {
    if (selectedId === null) return;
    const previous = tracks;
    setTracks(next);
    try {
      await api.setGenreOrder(
        selectedId,
        next.map((t) => t.youtube_video_id),
      );
      refresh();
    } catch (err) {
      setTracks(previous);
      onError(messageFor(err));
    }
  };

  const playNow = async (genreId: number, track: Track) => {
    try {
      await api.play(genreId, track.youtube_video_id);
      onNotice(`Now playing "${track.title}".`);
      refresh();
    } catch (err) {
      onError(messageFor(err));
    }
  };

  const playTrack = (track: Track) => {
    if (selectedId === null) return;
    if (state?.track) {
      setPendingTrack(track);
      return;
    }
    void playNow(selectedId, track);
  };

  const transport = async (direction: "next" | "prev") => {
    if (selectedId === null) return;
    try {
      await (direction === "next"
        ? api.playbackNext(selectedId)
        : api.playbackPrev(selectedId));
      refresh();
    } catch (err) {
      onError(messageFor(err));
    }
  };

  const goAuto = async () => {
    try {
      await api.playbackAuto();
      onNotice("Returned to the schedule.");
      refresh();
    } catch (err) {
      onError(messageFor(err));
    }
  };

  const stopPlayback = async () => {
    try {
      await api.playbackStop();
      onNotice("Stopped playback.");
      refresh();
    } catch (err) {
      onError(messageFor(err));
    }
  };

  const syncButton = (
    <button type="button" className="btn btn-secondary" onClick={syncAll}>
      Sync all playlists
    </button>
  );

  return (
    <section className="admin-panel np-panel" aria-label="Now playing">
      <div className="panel-head">
        <h2>Now playing</h2>
        {syncButton}
      </div>

      <div className="deck-grid admin-deck">
        <div className="deck-side admin-deck-side">
          <TurntableDeck
            playing={Boolean(state?.track)}
            artUrl={state?.track?.thumbnail_url ?? null}
          />
          <div className="mixer">
            <div className="dj">
              <small>On the decks</small>
              <strong>{state?.genre?.name ?? "Station"}</strong>
            </div>
            <VUMeter playing={Boolean(state?.track)} seed={1} />
            <div className="knob-row" aria-hidden="true">
              <span className="deck-knob" />
              <span
                className="deck-knob"
                style={{ "--r": "20deg" } as CSSProperties}
              />
              <span
                className="deck-knob"
                style={{ "--r": "70deg" } as CSSProperties}
              />
            </div>
          </div>
        </div>

        <div className="np-col admin-np-col">
          {genres.length > 0 && (
            <label className="field admin-genre-field">
              Genre
              <select
                aria-label="Genre to control"
                value={selectedId ?? ""}
                onChange={(e) => {
                  userSelectedRef.current = true;
                  setSelectedId(Number(e.target.value));
                }}
              >
                {genres.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
          )}

          {state?.genre && state.track ? (
            <>
              <div className="sleeve admin-sleeve">
                {state.track.thumbnail_url && (
                  <img
                    className="np-cover"
                    src={state.track.thumbnail_url}
                    alt=""
                  />
                )}
                <div>
                  <div className="kicker">Genre: {state.genre.name}</div>
                  <h2 className="np-title">{state.track.title}</h2>
                  <div className="np-artist">{state.track.artist}</div>
                </div>
              </div>
              <div>
                <div className="np-bar">
                  <div
                    className="np-bar-fill"
                    style={{
                      width: `${Math.min(
                        100,
                        Math.max(
                          0,
                          ((state.offset / (state.track.duration_seconds || 1)) *
                            100),
                        ),
                      )}%`,
                    }}
                  />
                </div>
                <div className="np-times">
                  <span>{formatClock(state.offset)}</span>
                  <span className={`badge source-${state.source}`}>
                    {SOURCE_LABELS[state.source] ?? state.source}
                  </span>
                </div>
              </div>
            </>
          ) : (
            <p className="muted">
              {failed ? "Could not load playback status." : "Nothing scheduled."}
            </p>
          )}

              <div className="transport">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => transport("prev")}
              disabled={tracks.length === 0}
            >
              Prev
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => transport("next")}
              disabled={tracks.length === 0}
            >
              Next
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={stopPlayback}
              disabled={!state?.track}
            >
              Stop
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={goAuto}
              disabled={
                state == null ||
                state.source === "schedule" ||
                state.source === "default"
              }
            >
              Auto
            </button>
          </div>

          <div className="queue-head">
            <h3>Queue</h3>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => saveOrder(shuffle(tracks))}
              disabled={tracks.length < 2}
            >
              Shuffle
            </button>
          </div>

          {loading ? (
            <p className="muted">Loading…</p>
          ) : (
            <ol className="queue-list" ref={queueRef}>
              {tracks.map((t, i) => {
                const isCurrent = i === currentIndex;
                return (
                  <li
                    key={`${t.youtube_video_id}-${i}`}
                    ref={isCurrent ? currentRowRef : undefined}
                    className={isCurrent ? "queue-row current" : "queue-row"}
                    draggable
                    onDragStart={() => setDragIndex(i)}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={() => {
                      if (dragIndex !== null && dragIndex !== i) {
                        saveOrder(reorder(tracks, dragIndex, i));
                      }
                      setDragIndex(null);
                    }}
                    onDragEnd={() => setDragIndex(null)}
                  >
                    <span className="drag-handle" aria-hidden="true">
                      ⋮⋮
                    </span>
                    {t.thumbnail_url && (
                      <img className="art small" src={t.thumbnail_url} alt="" />
                    )}
                    <span className="queue-title">{t.title}</span>
                    <span className="queue-artist">{t.artist}</span>
                    <span className="queue-duration">
                      {formatDuration(t.duration_seconds)}
                    </span>
                    {isCurrent &&
                      (isMobileView ? (
                        <span
                          className="on-air-dot"
                          role="img"
                          aria-label="On air"
                        />
                      ) : (
                        <span className="badge">On air</span>
                      ))}
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => playTrack(t)}
                    >
                      Play
                    </button>
                  </li>
                );
              })}
            </ol>
          )}

          {pendingTrack && selectedId !== null && (
            <ConfirmDialog
              title="Interrupt playback?"
              message={`A song is playing — play "${pendingTrack.title}" now?`}
              confirmLabel="Play now"
              onConfirm={() => {
                const track = pendingTrack;
                const genreId = selectedId;
                setPendingTrack(null);
                void playNow(genreId, track);
              }}
              onCancel={() => setPendingTrack(null)}
            />
          )}
        </div>
      </div>
    </section>
  );
}
