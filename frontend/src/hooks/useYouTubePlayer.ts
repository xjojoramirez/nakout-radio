import { useCallback, useEffect, useRef, useState } from "react";
import type { Track } from "../types";
import type { BroadcastState } from "./useBroadcast";

const VOLUME_KEY = "nakout.volume";
const MUTED_KEY = "nakout.muted";
const DRIFT_THRESHOLD = 3;
const AUTOPLAY_FALLBACK_MS = 1500;
const RESUME_THROTTLE_MS = 3000;

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

function targetFor(broadcast: BroadcastState, now = Date.now()): number {
  const duration = broadcast.track?.duration_seconds ?? 0;
  const target = liveTarget(broadcast, now);
  return duration > 0 ? Math.min(target, duration - 1) : target;
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
  const currentVideoRef = useRef<string | null>(null);
  const preloadedVideoRef = useRef<string | null>(null);
  const startTimerRef = useRef<number | null>(null);
  const endedRef = useRef(false);
  const retryAttemptRef = useRef(0);
  const retryTimerRef = useRef<number | null>(null);
  const lastResumeAtRef = useRef(0);
  const preloadRef = useRef<YTPlayer | null>(null);
  const preloadVideoRef = useRef<string | null>(null);
  const preloadBoundaryRef = useRef<number | null>(null);
  const preloadFailedRef = useRef(false);
  const preloadTimerRef = useRef<number | null>(null);
  const preloadSwapAtRef = useRef<number | null>(null);

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
        resetRetry();
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
    preloadBoundaryRef.current = null;
  }, []);

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
        onError: () => {
          preloadFailedRef.current = true;
          resetPreload();
        },
        onStateChange: (e: { data: number }) => {
          handleStateChange(player, e.data);
        },
      },
    });
    preloadRef.current = player;
    return player;
  }, [handleStateChange, resetPreload]);

  const clearStartTimer = useCallback(() => {
    if (startTimerRef.current !== null) {
      window.clearTimeout(startTimerRef.current);
      startTimerRef.current = null;
    }
  }, []);

  const startPreloaded = useCallback(
    (videoId: string, target: number) => {
      const player = playerRef.current;
      if (!player || !isPlayerReady(player)) return;
      preloadedVideoRef.current = null;
      currentVideoRef.current = videoId;
      endedRef.current = false;
      resetRetry();
      try {
        player.seekTo(Math.max(0, target), true);
        player.setVolume(volumeRef.current);
        if (mutedRef.current || volumeRef.current === 0) player.mute();
        else player.unMute();
        player.playVideo();
      } catch {
        // The iframe may still be initialising; the next frame retries.
      }
    },
    [resetRetry],
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
    (nextId: string, boundaryAt: number) => {
      // The 1 s tick re-arms on every frame inside the lead window. Never
      // postpone a swap that is already armed: a rescheduled timer would be
      // clamped one tick past the boundary, and boundary jitter must not push
      // the swap later. A boundary that moved earlier (e.g. the gap announces
      // a nearer start) replaces the pending timer.
      if (
        preloadTimerRef.current !== null &&
        preloadSwapAtRef.current !== null &&
        preloadSwapAtRef.current <= boundaryAt
      ) {
        return;
      }
      clearPreloadTimer();
      preloadSwapAtRef.current = boundaryAt;
      preloadTimerRef.current = window.setTimeout(() => {
        preloadTimerRef.current = null;
        preloadSwapAtRef.current = null;
        const preload = preloadRef.current;
        if (!preload || !isPlayerReady(preload)) return;
        if (preloadVideoRef.current !== nextId) return;
        const position = Math.max(0, (Date.now() - boundaryAt) / 1000);
        const previous = playerRef.current;
        try {
          preload.seekTo(position, true);
          preload.setVolume(volumeRef.current);
          if (mutedRef.current || volumeRef.current === 0) preload.mute();
          else preload.unMute();
          preload.playVideo();
        } catch {
          return;
        }
        playerRef.current = preload;
        preloadRef.current = previous;
        preloadVideoRef.current = null;
        preloadBoundaryRef.current = null;
        preloadedVideoRef.current = null;
        currentVideoRef.current = nextId;
        endedRef.current = false;
        resetRetry();
        if (previous && isPlayerReady(previous)) {
          try {
            previous.pauseVideo();
            previous.mute();
          } catch {
            // Demoting the old player is best-effort.
          }
        }
        onEndedRef.current();
      }, Math.max(0, boundaryAt - Date.now()));
    },
    [clearPreloadTimer, resetRetry],
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
        preloadBoundaryRef.current = boundaryAt;
      } catch {
        preloadFailedRef.current = true;
      }
      scheduleSwap(nextId, boundaryAt);
    },
    [ensurePreloadPlayer, scheduleSwap],
  );

  const armPreloadRef = useRef(maybeArmPreload);
  armPreloadRef.current = maybeArmPreload;

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
          player.setVolume(volumeRef.current);
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
        onError: () => scheduleRetry(),
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
      preloadBoundaryRef.current = null;
      preloadFailedRef.current = false;
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
  ]);

  useEffect(() => {
    const player = playerRef.current;
    if (!player || !broadcast?.track) return;
    if (!isPlayerReady(player)) return;
    const yt = window.YT;

    if (broadcast.phase === "gap") {
      if (yt && player.getPlayerState() === yt.PlayerState.PLAYING) {
        player.pauseVideo();
      }
      if (!broadcast.nextTrack) return;
      const nextId = broadcast.nextTrack.youtube_video_id;
      const preloadHealthy =
        !preloadFailedRef.current &&
        preloadRef.current !== null &&
        isPlayerReady(preloadRef.current) &&
        preloadVideoRef.current === nextId;
      if (preloadHealthy) {
        clearStartTimer();
        const boundaryAt =
          broadcast.fetchedAt +
          broadcast.rttMs / 2 +
          Math.max(0, broadcast.secondsUntilStart ?? 0) * 1000;
        scheduleSwap(nextId, boundaryAt);
        return;
      }
      if (preloadedVideoRef.current !== nextId) {
        preloadNext(broadcast.nextTrack);
      }
      scheduleGapStart(broadcast);
      return;
    }

    clearStartTimer();
    const videoId = broadcast.track.youtube_video_id;
    const target = targetFor(broadcast);
    if (currentVideoRef.current !== videoId) {
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
      return;
    }
    if (!yt) return;
    const state = player.getPlayerState();
    const drift = Math.abs(player.getCurrentTime() - target);
    if (state === yt.PlayerState.ENDED && drift > DRIFT_THRESHOLD) {
      player.loadVideoById({ videoId, startSeconds: target });
    } else if (state === yt.PlayerState.PLAYING && drift > DRIFT_THRESHOLD) {
      player.seekTo(target, true);
    }
  }, [
    broadcast,
    clearPreloadTimer,
    clearStartTimer,
    preloadNext,
    resetPreload,
    scheduleGapStart,
    scheduleSwap,
    startPreloaded,
    resetRetry,
  ]);

  useEffect(() => {
    const player = playerRef.current;
    if (!isPlayerReady(player)) return;
    player.setVolume(volume);
    if (muted || volume === 0) player.mute();
    else player.unMute();
  }, [volume, muted, ready, hasTrack]);

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
              const target = targetFor(current);
              if (Math.abs(player.getCurrentTime() - target) > DRIFT_THRESHOLD) {
                player.seekTo(target, true);
              }
            } else if (
              playerState === yt.PlayerState.PAUSED ||
              playerState === yt.PlayerState.CUED
            ) {
              // Mobile OSes pause the iframe player when the page is suspended
              // (screen lock, app switch). Resume at the live position so the
              // listener rejoins the broadcast; throttled in case the browser
              // keeps blocking playback.
              const now = Date.now();
              if (now - lastResumeAtRef.current >= RESUME_THROTTLE_MS) {
                lastResumeAtRef.current = now;
                player.seekTo(targetFor(current), true);
                player.playVideo();
              }
            }
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
