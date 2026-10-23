import { useCallback, useEffect, useRef, useState } from "react";
import type { Track } from "../types";
import { applyVolumeOffset } from "../utils/loudness";
import type { BroadcastState } from "./useBroadcast";

const VOLUME_KEY = "nakout.volume";
const MUTED_KEY = "nakout.muted";
const DRIFT_THRESHOLD = 3;
const AUTOPLAY_FALLBACK_MS = 1500;
const RESUME_THROTTLE_MS = 3000;
const POST_SWAP_GRACE_MS = 3000;

interface YTPlayer {
  loadVideoById: (opts: { videoId: string; startSeconds?: number }) => void;
  playVideo: () => void;
  pauseVideo: () => void;
  mute: () => void;
  unMute: () => void;
  setVolume: (v: number) => void;
  seekTo: (seconds: number, allowSeekAhead: boolean) => void;
  getPlayerState: () => number;
  getCurrentTime: () => number;
  destroy: () => void;
}

interface YTNamespace {
  Player: new (element: string | HTMLElement, options: unknown) => YTPlayer;
  PlayerState: {
    PLAYING: number;
    ENDED: number;
    PAUSED: number;
    CUED: number;
  };
}

const PRELOAD_CONTAINER_ID = "yt-preload";

declare global {
  interface Window {
    YT?: YTNamespace;
    onYouTubeIframeAPIReady?: () => void;
  }
}

let apiPromise: Promise<void> | null = null;

function loadIframeApi(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.YT?.Player) return Promise.resolve();
  if (apiPromise) return apiPromise;
  apiPromise = new Promise((resolve) => {
    const previous = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      previous?.();
      resolve();
    };
    const existing = document.querySelector(
      'script[src="https://www.youtube.com/iframe_api"]',
    );
    if (!existing) {
      const script = document.createElement("script");
      script.src = "https://www.youtube.com/iframe_api";
      document.body.appendChild(script);
    }
  });
  return apiPromise;
}

export function storedVolume(): number {
  const raw = window.localStorage.getItem(VOLUME_KEY);
  const n = raw === null ? NaN : Number(raw);
  return Number.isFinite(n) ? Math.min(100, Math.max(0, n)) : 70;
}

export function storedMuted(): boolean {
  return window.localStorage.getItem(MUTED_KEY) !== "false";
}

export function liveTarget(broadcast: BroadcastState, now = Date.now()): number {
  const elapsed = (now - broadcast.fetchedAt) / 1000;
  return Math.max(0, broadcast.offset + broadcast.rttMs / 2000 + elapsed);
}

function isPlayerReady(player: YTPlayer | null): player is YTPlayer {
  return (
    player != null &&
    typeof player.getPlayerState === "function" &&
    typeof player.getCurrentTime === "function"
  );
}

/** True while the page is backgrounded (app switch, screen lock, other tab). */
function isPageHidden(): boolean {
  return document.visibilityState !== "visible";
}

/**
 * A hidden page whose player is paused/cued has most likely lost the
 * phone's audio focus to another app (the listener opened a video, etc.).
 * Starting playback from here would take focus back and stop that app.
 */
function pausedWhileHidden(player: YTPlayer | null): boolean {
  if (document.visibilityState === "visible" || !isPlayerReady(player)) {
    return false;
  }
  const yt = window.YT;
  if (!yt) return false;
  const state = player.getPlayerState();
  return state === yt.PlayerState.PAUSED || state === yt.PlayerState.CUED;
}

function targetFor(broadcast: BroadcastState, now = Date.now()): number {
  const duration = broadcast.track?.duration_seconds ?? 0;
  const target = liveTarget(broadcast, now);
  return duration > 0 ? Math.min(target, duration - 1) : target;
}

/**
 * Loudness offset for the video a player is on: the broadcast's current or
 * upcoming track, or 0 when unknown (no data → no correction).
 */
function trackOffset(
  broadcast: BroadcastState | null,
  videoId: string | null,
): number {
  if (!broadcast || !videoId) return 0;
  if (broadcast.track?.youtube_video_id === videoId) {
    return broadcast.track.volume_offset_db ?? 0;
  }
  if (broadcast.nextTrack?.youtube_video_id === videoId) {
    return broadcast.nextTrack.volume_offset_db ?? 0;
  }
  return 0;
}

export interface PlayerControls {
  ready: boolean;
  playing: boolean;
  progress: number;
  muted: boolean;
  volume: number;
  track: Track | null;
  toggleMute: () => void;
  setVolume: (value: number) => void;
}

export function useYouTubePlayer(
  containerId: string,
  broadcast: BroadcastState | null,
  onEnded: () => void,
): PlayerControls {
  const playerRef = useRef<YTPlayer | null>(null);
  const onEndedRef = useRef(onEnded);
  onEndedRef.current = onEnded;
  const broadcastRef = useRef(broadcast);
  broadcastRef.current = broadcast;

  const [apiReady, setApiReady] = useState(false);
  const [ready, setReady] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [muted, setMuted] = useState(() => storedMuted());
  const [volume, setVolumeState] = useState(() => storedVolume());

  const volumeRef = useRef(volume);
  volumeRef.current = volume;
  const mutedRef = useRef(muted);
  mutedRef.current = muted;

  /** User volume adjusted by the loudness offset of the video in question. */
  const volumeForVideo = useCallback(
    (videoId: string | null) =>
      applyVolumeOffset(
        volumeRef.current,
        trackOffset(broadcastRef.current, videoId),
      ),
    [],
  );
  const currentVideoRef = useRef<string | null>(null);
  const preloadedVideoRef = useRef<string | null>(null);
  const startTimerRef = useRef<number | null>(null);
  const endedRef = useRef(false);
  const retryAttemptRef = useRef(0);
  const retryTimerRef = useRef<number | null>(null);
  const lastResumeAtRef = useRef(0);
  const backgroundInterruptedRef = useRef(false);
  const preloadRef = useRef<YTPlayer | null>(null);
  const preloadVideoRef = useRef<string | null>(null);
  const preloadFailedRef = useRef(false);
  const preloadTimerRef = useRef<number | null>(null);
  const preloadSwapAtRef = useRef<number | null>(null);
  const preloadSwapVideoRef = useRef<string | null>(null);
  const lastSwapAtRef = useRef<number | null>(null);

  const hasTrack = broadcast?.track != null;

  const clearRetry = useCallback(() => {
    if (retryTimerRef.current !== null) {
      window.clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
  }, []);

  const preloadNext = useCallback((next: Track) => {
    const player = playerRef.current;
    if (!player || !isPlayerReady(player)) return;
    try {
      player.mute();
      player.loadVideoById({
        videoId: next.youtube_video_id,
        startSeconds: 0,
      });
      player.pauseVideo();
    } catch {
      return;
    }
    preloadedVideoRef.current = next.youtube_video_id;
  }, []);

  const reloadCurrent = useCallback(() => {
    const player = playerRef.current;
    const current = broadcastRef.current;
    if (!player || !isPlayerReady(player)) return;
    // A retry must not take audio focus back from another app while hidden.
    if (isPageHidden() && backgroundInterruptedRef.current) return;
    if (current?.phase === "gap" && current.nextTrack) {
      preloadNext(current.nextTrack);
      return;
    }
    if (!current?.track) return;
    try {
      player.loadVideoById({
        videoId: current.track.youtube_video_id,
        startSeconds: targetFor(current),
      });
      player.playVideo();
    } catch {
      // The iframe may still be initialising; the next attempt retries.
    }
  }, [preloadNext]);

  const scheduleRetry = useCallback(() => {
    if (retryTimerRef.current !== null) return;
    const attempt = retryAttemptRef.current;
    retryAttemptRef.current = attempt + 1;
    const delay = Math.min(1000 * 2 ** attempt, 15000);
    retryTimerRef.current = window.setTimeout(() => {
      retryTimerRef.current = null;
      reloadCurrent();
    }, delay);
  }, [reloadCurrent]);

  const resetRetry = useCallback(() => {
    retryAttemptRef.current = 0;
    clearRetry();
  }, [clearRetry]);

  const handleStateChange = useCallback(
    (player: YTPlayer, data: number) => {
      if (playerRef.current !== player) return;
      const yt = window.YT;
      const isPlaying = yt != null && data === yt.PlayerState.PLAYING;
      setPlaying(isPlaying);
      if (isPlaying) {
        endedRef.current = false;
        backgroundInterruptedRef.current = false;
        resetRetry();
      } else if (
        yt != null &&
        (data === yt.PlayerState.PAUSED || data === yt.PlayerState.CUED) &&
        isPageHidden() &&
        broadcastRef.current?.phase !== "gap"
      ) {
        // A background pause is the OS handing audio focus to another app.
        // Remember it right away so a boundary cannot restart playback.
        backgroundInterruptedRef.current = true;
      }
      if (yt != null && data === yt.PlayerState.ENDED) {
        endedRef.current = true;
        onEndedRef.current();
      }
    },
    [resetRetry],
  );

  const clearPreloadTimer = useCallback(() => {
    if (preloadTimerRef.current !== null) {
      window.clearTimeout(preloadTimerRef.current);
      preloadTimerRef.current = null;
    }
    preloadSwapAtRef.current = null;
    preloadSwapVideoRef.current = null;
  }, []);

  const resetPreload = useCallback(() => {
    const preload = preloadRef.current;
    if (preload && isPlayerReady(preload)) {
      try {
        preload.pauseVideo();
      } catch {
        // The iframe may still be initialising.
      }
    }
    preloadVideoRef.current = null;
  }, []);

  const handleError = useCallback(
    (player: YTPlayer) => {
      if (playerRef.current === player) {
        scheduleRetry();
        return;
      }
      preloadFailedRef.current = true;
      resetPreload();
    },
    [scheduleRetry, resetPreload],
  );

  const ensurePreloadPlayer = useCallback((): YTPlayer | null => {
    if (preloadRef.current) return preloadRef.current;
    const yt = window.YT;
    if (!yt || !document.getElementById(PRELOAD_CONTAINER_ID)) return null;
    const player = new yt.Player(PRELOAD_CONTAINER_ID, {
      height: "1",
      width: "1",
      playerVars: {
        autoplay: 1,
        mute: 1,
        controls: 0,
        disablekb: 1,
        playsinline: 1,
      },
      events: {
        onError: () => handleError(player),
        onStateChange: (e: { data: number }) => {
          handleStateChange(player, e.data);
        },
      },
    });
    preloadRef.current = player;
    return player;
  }, [handleError, handleStateChange, resetPreload]);

  const clearStartTimer = useCallback(() => {
    if (startTimerRef.current !== null) {
      window.clearTimeout(startTimerRef.current);
      startTimerRef.current = null;
    }
  }, []);

  const performSwap = useCallback(
    (videoId: string, position: number) => {
      const preload = preloadRef.current;
      if (!preload || !isPlayerReady(preload)) return;
      if (preloadVideoRef.current !== videoId) return;
      const previous = playerRef.current;
      // While hidden, a paused active player means another app owns the
      // audio focus. Unmuting the pre-roll would take it back and stop that
      // app; keep it muted and let visibility recovery promote it instead.
      if (
        isPageHidden() &&
        (backgroundInterruptedRef.current ||
          (broadcastRef.current?.phase !== "gap" &&
            pausedWhileHidden(previous)))
      ) {
        return;
      }
      try {
        preload.seekTo(Math.max(0, position), true);
        preload.setVolume(volumeForVideo(videoId));
        if (mutedRef.current || volumeRef.current === 0) preload.mute();
        else preload.unMute();
        preload.playVideo();
      } catch {
        return;
      }
      playerRef.current = preload;
      preloadRef.current = previous;
      preloadVideoRef.current = null;
      preloadedVideoRef.current = null;
      currentVideoRef.current = videoId;
      endedRef.current = false;
      resetRetry();
      setPlaying(true);
      if (previous && isPlayerReady(previous)) {
        try {
          previous.pauseVideo();
          previous.mute();
        } catch {
          // Demoting the old player is best-effort.
        }
      }
      // Ask the page to resync so the fresh broadcast (new current track)
      // replaces the stale frame within one round-trip.
      lastSwapAtRef.current = Date.now();
      onEndedRef.current();
    },
    [resetRetry, volumeForVideo],
  );

  const startPreloaded = useCallback(
    (videoId: string, target: number) => {
      // When the active player is still on the previous video but the
      // pre-roll player already holds the next one (the page was frozen
      // over the boundary), promote it directly.
      if (
        preloadVideoRef.current === videoId &&
        currentVideoRef.current !== videoId
      ) {
        performSwap(videoId, target);
        return;
      }
      const player = playerRef.current;
      if (!player || !isPlayerReady(player)) return;
      if (
        isPageHidden() &&
        (backgroundInterruptedRef.current ||
          (broadcastRef.current?.phase !== "gap" &&
            pausedWhileHidden(player)))
      ) {
        return;
      }
      preloadedVideoRef.current = null;
      currentVideoRef.current = videoId;
      endedRef.current = false;
      resetRetry();
      try {
        player.seekTo(Math.max(0, target), true);
        player.setVolume(volumeForVideo(videoId));
        if (mutedRef.current || volumeRef.current === 0) player.mute();
        else player.unMute();
        player.playVideo();
      } catch {
        // The iframe may still be initialising; the next frame retries.
      }
    },
    [performSwap, resetRetry, volumeForVideo],
  );

  const scheduleGapStart = useCallback(
    (broadcast: BroadcastState) => {
      clearStartTimer();
      if (!broadcast.nextTrack || broadcast.secondsUntilStart === null) return;
      const boundaryAt =
        broadcast.fetchedAt +
        broadcast.rttMs / 2 +
        Math.max(0, broadcast.secondsUntilStart) * 1000;
      const delay = Math.max(0, boundaryAt - Date.now());
      startTimerRef.current = window.setTimeout(() => {
        startTimerRef.current = null;
        const current = broadcastRef.current;
        if (!current || current.phase !== "gap" || !current.nextTrack) return;
        if (preloadedVideoRef.current !== current.nextTrack.youtube_video_id) {
          return;
        }
        const position = Math.max(0, (Date.now() - boundaryAt) / 1000);
        startPreloaded(current.nextTrack.youtube_video_id, position);
      }, delay);
    },
    [clearStartTimer, startPreloaded],
  );

  const scheduleSwap = useCallback(
    (nextId: string, boundaryAt: number, maxSeconds: number) => {
      // The 1 s tick re-arms on every frame inside the lead window. Keep a
      // pending swap only when it is for the same video and would not be
      // postponed: a different video or an earlier boundary replaces it.
      if (
        preloadTimerRef.current !== null &&
        preloadSwapVideoRef.current === nextId &&
        preloadSwapAtRef.current !== null &&
        preloadSwapAtRef.current <= boundaryAt
      ) {
        return;
      }
      clearPreloadTimer();
      preloadSwapVideoRef.current = nextId;
      preloadSwapAtRef.current = boundaryAt;
      preloadTimerRef.current = window.setTimeout(() => {
        preloadTimerRef.current = null;
        preloadSwapAtRef.current = null;
        preloadSwapVideoRef.current = null;
        const position = Math.min(
          Math.max(0, (Date.now() - boundaryAt) / 1000),
          Math.max(0, maxSeconds - 1),
        );
        performSwap(nextId, position);
      }, Math.max(0, boundaryAt - Date.now()));
    },
    [clearPreloadTimer, performSwap],
  );

  const maybeArmPreload = useCallback(
    (current: BroadcastState) => {
      if (current.phase !== "playing") return;
      if (!current.track || !current.nextTrack) return;
      // A stale frame (or a pending load) must not arm: the reconcile effect
      // owns the active player until it matches the broadcast again.
      if (currentVideoRef.current !== current.track.youtube_video_id) return;
      if (current.preloadLead <= 0 || preloadFailedRef.current) return;
      if (current.secondsUntilStart === null) return;
      const boundaryAt =
        current.fetchedAt +
        current.rttMs / 2 +
        Math.max(0, current.secondsUntilStart) * 1000;
      if (Date.now() < boundaryAt - current.preloadLead * 1000) return;
      if (Date.now() >= boundaryAt) return;
      const preload = ensurePreloadPlayer();
      if (!preload || !isPlayerReady(preload)) return;
      const nextId = current.nextTrack.youtube_video_id;
      try {
        if (preloadVideoRef.current !== nextId) {
          preload.mute();
          preload.loadVideoById({ videoId: nextId, startSeconds: 0 });
          preload.playVideo();
        } else if (
          window.YT &&
          preload.getPlayerState() !== window.YT.PlayerState.PLAYING
        ) {
          preload.mute();
          preload.playVideo();
        }
        preloadVideoRef.current = nextId;
      } catch {
        preloadFailedRef.current = true;
      }
      scheduleSwap(nextId, boundaryAt, current.nextTrack.duration_seconds);
    },
    [ensurePreloadPlayer, scheduleSwap],
  );

  const armPreloadRef = useRef(maybeArmPreload);
  armPreloadRef.current = maybeArmPreload;

  /**
   * Reconcile the active player with a broadcast frame. Shared by the
   * reactive effect and the visibility recovery path so both apply the
   * same rules. `forceLive` skips the post-swap grace window, which is
   * only relevant for live frames that predate a just-completed swap.
   */
  const applyBroadcast = useCallback(
    (current: BroadcastState, forceLive = false) => {
      const player = playerRef.current;
      if (!player || !current.track) return;
      if (!isPlayerReady(player)) return;
      const yt = window.YT;

      // A frame that still announces the active video as "next" right after
      // a swap predates the swap; ignore its stale track until the resync
      // frame arrives. Bounded by POST_SWAP_GRACE_MS so a legitimate
      // back-jump (the same shape) still applies once the window has passed.
      const swappedRecently =
        lastSwapAtRef.current !== null &&
        Date.now() - lastSwapAtRef.current < POST_SWAP_GRACE_MS;
      if (
        !forceLive &&
        swappedRecently &&
        current.phase === "playing" &&
        current.track != null &&
        current.track.youtube_video_id !== currentVideoRef.current &&
        current.nextTrack?.youtube_video_id === currentVideoRef.current
      ) {
        return;
      }

      if (current.phase === "gap") {
        if (yt && player.getPlayerState() === yt.PlayerState.PLAYING) {
          player.pauseVideo();
        }
        if (!current.nextTrack) return;
        const nextId = current.nextTrack.youtube_video_id;
        const preloadHealthy =
          !preloadFailedRef.current &&
          preloadRef.current !== null &&
          isPlayerReady(preloadRef.current) &&
          preloadVideoRef.current === nextId;
        if (preloadHealthy) {
          clearStartTimer();
          const boundaryAt =
            current.fetchedAt +
            current.rttMs / 2 +
            Math.max(0, current.secondsUntilStart ?? 0) * 1000;
          scheduleSwap(nextId, boundaryAt, current.nextTrack.duration_seconds);
          return;
        }
        if (preloadedVideoRef.current !== nextId) {
          preloadNext(current.nextTrack);
        }
        scheduleGapStart(current);
        return;
      }

      clearStartTimer();
      const videoId = current.track.youtube_video_id;
      const target = targetFor(current);
      if (currentVideoRef.current !== videoId) {
        // Do not start the new live track from the background when the
        // player was paused by another app's audio focus; recovery runs on
        // visibilitychange. Keep the muted pre-roll intact for that.
        if (
          isPageHidden() &&
          (backgroundInterruptedRef.current || pausedWhileHidden(player))
        ) {
          return;
        }
        clearPreloadTimer();
        resetPreload();
        preloadFailedRef.current = false;
        if (preloadedVideoRef.current === videoId) {
          startPreloaded(videoId, target);
          return;
        }
        currentVideoRef.current = videoId;
        endedRef.current = false;
        resetRetry();
        player.loadVideoById({ videoId, startSeconds: target });
        player.playVideo();
        return;
      }
      if (!yt) return;
      const state = player.getPlayerState();
      const drift = Math.abs(player.getCurrentTime() - target);
      if (state === yt.PlayerState.ENDED && drift > DRIFT_THRESHOLD) {
        player.loadVideoById({ videoId, startSeconds: target });
        player.playVideo();
      } else if (state === yt.PlayerState.PLAYING && drift > DRIFT_THRESHOLD) {
        player.seekTo(target, true);
      }
    },
    [
      clearPreloadTimer,
      clearStartTimer,
      preloadNext,
      resetPreload,
      resetRetry,
      scheduleGapStart,
      scheduleSwap,
      startPreloaded,
    ],
  );
  const applyBroadcastRef = useRef(applyBroadcast);
  applyBroadcastRef.current = applyBroadcast;

  /**
   * Recovery for mobile suspensions: while the page is hidden the OS
   * freezes the swap/gap timers, so a track boundary can pass without the
   * transition firing. On return to the foreground, drop the stale
   * pre-roll when it no longer matches the broadcast, promote a healthy
   * preload whose boundary has passed, and refresh immediately instead of
   * waiting for the next poll.
   */
  const onVisibilityRecover = useCallback(() => {
    const current = broadcastRef.current;
    const player = playerRef.current;
    if (!current || !player || !isPlayerReady(player)) return;
    const stale = currentVideoRef.current !== current.track?.youtube_video_id;
    if (!stale) {
      // Stale swap/gap timers must not fire after recovery: a promotion or
      // the reconcile path owns the transition from here.
      clearPreloadTimer();
      clearStartTimer();
      const nextId = current.nextTrack?.youtube_video_id ?? null;
      // The pre-roll player is the source of truth for what it holds: it
      // keeps playing (muted) while the page is hidden even when the
      // reconcile path has already cleared the bookkeeping refs.
      const preloadHoldsNext =
        nextId !== null &&
        (nextId === preloadedVideoRef.current ||
          preloadVideoRef.current === nextId);
      // The boundary passed while the page was off screen: the live
      // position now runs past the current track's runtime (or the frame
      // already flags the gap). Promote the healthy pre-roll at the live
      // position instead of reloading a track that has run out.
      const liveTargetNow = targetFor(current);
      const trackRanOut =
        current.track != null &&
        current.track.duration_seconds > 0 &&
        liveTargetNow >= current.track.duration_seconds - 1;
      if (preloadHoldsNext && (current.phase === "gap" || trackRanOut)) {
        const boundaryAt =
          current.fetchedAt +
          current.rttMs / 2 +
          Math.max(0, current.secondsUntilStart ?? 0) * 1000;
        startPreloaded(
          nextId,
          Math.min(
            Math.max(0, (Date.now() - boundaryAt) / 1000),
            Math.max(0, (current.nextTrack?.duration_seconds ?? 0) - 1),
          ),
        );
        applyBroadcastRef.current(current, true);
        onEndedRef.current();
        return;
      }
    }
    applyBroadcastRef.current(current, true);
    onEndedRef.current();
  }, [clearPreloadTimer, clearStartTimer, startPreloaded]);
  const recoverRef = useRef(onVisibilityRecover);
  recoverRef.current = onVisibilityRecover;

  useEffect(() => {
    const onVisibilityChange = () => {
      if (document.visibilityState !== "visible") return;
      // The listener is back: any audio-focus interruption is over and
      // playback may resume/promote again.
      backgroundInterruptedRef.current = false;
      recoverRef.current();
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () =>
      document.removeEventListener("visibilitychange", onVisibilityChange);
  }, []);

  useEffect(() => {
    let cancelled = false;
    loadIframeApi().then(() => {
      if (!cancelled) setApiReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!apiReady || !hasTrack || playerRef.current || !window.YT) return;
    const current = broadcastRef.current;
    if (!current) return;
    const joinDuringGap = current.phase === "gap" && current.nextTrack !== null;
    const initial = joinDuringGap ? current.nextTrack : current.track;
    if (!initial) return;
    const initialId = initial.youtube_video_id;
    const start = joinDuringGap ? 0 : targetFor(current);
    const yt = window.YT;
    let fallbackTimer: number | null = null;
    const player = new yt.Player(containerId, {
      height: "1",
      width: "1",
      videoId: initialId,
      playerVars: {
        autoplay: 1,
        mute: 1,
        controls: 0,
        disablekb: 1,
        playsinline: 1,
        start: Math.floor(start),
      },
      events: {
        onReady: () => {
          setReady(true);
          player.setVolume(volumeForVideo(initialId));
          const live = broadcastRef.current;
          if (live?.phase === "gap" && live.nextTrack) {
            preloadedVideoRef.current = live.nextTrack.youtube_video_id;
            player.mute();
            player.pauseVideo();
            scheduleGapStart(live);
            return;
          }
          if (mutedRef.current) {
            player.mute();
            player.playVideo();
          } else {
            player.unMute();
            player.playVideo();
            fallbackTimer = window.setTimeout(() => {
              if (player.getPlayerState() !== yt.PlayerState.PLAYING) {
                player.mute();
                setMuted(true);
                window.localStorage.setItem(MUTED_KEY, "true");
                player.playVideo();
              }
            }, AUTOPLAY_FALLBACK_MS);
          }
        },
        onStateChange: (e: { data: number }) => {
          handleStateChange(player, e.data);
        },
        onError: () => handleError(player),
      },
    });
    playerRef.current = player;
    currentVideoRef.current = initialId;
    if (joinDuringGap) {
      preloadedVideoRef.current = initialId;
    }
    return () => {
      if (fallbackTimer !== null) window.clearTimeout(fallbackTimer);
      clearRetry();
      clearStartTimer();
      const preload = preloadRef.current;
      preloadRef.current = null;
      preloadVideoRef.current = null;
      preloadFailedRef.current = false;
      lastSwapAtRef.current = null;
      clearPreloadTimer();
      if (preload) {
        try {
          preload.destroy();
        } catch {
          // The player may already have been torn down by the iframe API.
        }
      }
      preloadedVideoRef.current = null;
      playerRef.current = null;
      currentVideoRef.current = null;
      try {
        player.destroy();
      } catch {
        // The player may already have been torn down by the iframe API.
      }
      setReady(false);
      setPlaying(false);
    };
  }, [
    apiReady,
    hasTrack,
    containerId,
    scheduleGapStart,
    clearStartTimer,
    scheduleRetry,
    resetRetry,
    clearRetry,
    clearPreloadTimer,
    handleStateChange,
    handleError,
    volumeForVideo,
  ]);

  useEffect(() => {
    if (broadcast) applyBroadcast(broadcast);
  }, [broadcast, applyBroadcast]);

  useEffect(() => {
    const player = playerRef.current;
    if (!isPlayerReady(player)) return;
    player.setVolume(volumeForVideo(currentVideoRef.current));
    if (muted || volume === 0) player.mute();
    else player.unMute();
  }, [
    volume,
    muted,
    ready,
    hasTrack,
    volumeForVideo,
    // Re-apply when the live track (or its loudness offset) changes, so a
    // correction that lands mid-track still takes effect.
    broadcast?.track?.youtube_video_id,
    broadcast?.track?.volume_offset_db,
  ]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      const player = playerRef.current;
      const yt = window.YT;
      if (!isPlayerReady(player) || !yt) return;
      const current = broadcastRef.current;
      if (current?.track) {
        setProgress(player.getCurrentTime());
        const playerState = player.getPlayerState();
        if (current.phase !== "gap") {
          armPreloadRef.current(current);
          if (currentVideoRef.current === current.track.youtube_video_id) {
            if (playerState === yt.PlayerState.PLAYING) {
              lastResumeAtRef.current = 0;
              backgroundInterruptedRef.current = false;
              const target = targetFor(current);
              if (Math.abs(player.getCurrentTime() - target) > DRIFT_THRESHOLD) {
                player.seekTo(target, true);
              }
            } else if (
              playerState === yt.PlayerState.PAUSED ||
              playerState === yt.PlayerState.CUED
            ) {
              if (isPageHidden()) {
                // The phone pauses the iframe when another app takes audio
                // focus (e.g. a video the listener opened). Calling play()
                // from the background would take focus back and stop that
                // app, so stay paused and resume on return instead.
                backgroundInterruptedRef.current = true;
              } else {
                // Mobile OSes pause the iframe player when the page is
                // suspended (screen lock, app switch). Resume at the live
                // position so the listener rejoins the broadcast; throttled
                // in case the browser keeps blocking playback.
                const now = Date.now();
                if (now - lastResumeAtRef.current >= RESUME_THROTTLE_MS) {
                  lastResumeAtRef.current = now;
                  const target = targetFor(current);
                  const duration = current.track.duration_seconds;
                  if (duration > 0 && target >= duration - 1) {
                    // The track ran out while the page was frozen: the live
                    // target is at/past the runtime, so a seek would land in
                    // a dead buffer. Reload at the live position instead.
                    player.loadVideoById({
                      videoId: current.track.youtube_video_id,
                      startSeconds: target,
                    });
                    player.playVideo();
                  } else {
                    player.seekTo(target, true);
                    player.playVideo();
                  }
                }
              }
            }
          } else if (playerState === yt.PlayerState.ENDED) {
            // A just-arrived frame already points at a different track:
            // advance instead of leaving the ended player idle.
            applyBroadcastRef.current(current);
          }
        }
      }
      if (endedRef.current && current?.phase !== "gap") onEndedRef.current();
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  const setVolume = useCallback((value: number) => {
    const clamped = Math.min(100, Math.max(0, Math.round(value)));
    setVolumeState(clamped);
    window.localStorage.setItem(VOLUME_KEY, String(clamped));
    if (clamped > 0 && mutedRef.current) {
      setMuted(false);
      window.localStorage.setItem(MUTED_KEY, "false");
    }
  }, []);

  const toggleMute = useCallback(() => {
    setMuted((previous) => {
      const next = !previous;
      window.localStorage.setItem(MUTED_KEY, String(next));
      return next;
    });
  }, []);

  return {
    ready,
    playing,
    progress,
    muted,
    volume,
    track: broadcast?.track ?? null,
    toggleMute,
    setVolume,
  };
}
