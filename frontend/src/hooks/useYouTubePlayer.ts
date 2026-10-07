import { useCallback, useEffect, useRef, useState } from "react";
import type { Track } from "../types";
import type { BroadcastState } from "./useBroadcast";

const VOLUME_KEY = "nakout.volume";
const MUTED_KEY = "nakout.muted";
const DRIFT_THRESHOLD = 3;
const AUTOPLAY_FALLBACK_MS = 1500;

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
  PlayerState: { PLAYING: number; ENDED: number };
}

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

function targetFor(broadcast: BroadcastState, now = Date.now()): number {
  const duration = broadcast.track?.duration_seconds ?? 0;
  const target = liveTarget(broadcast, now);
  return duration > 0 ? Math.min(target, duration - 1) : target;
}

export interface PlayerControls {
  ready: boolean;
  playing: boolean;
  progress: number;
  error: boolean;
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
  const [error, setError] = useState(false);
  const [muted, setMuted] = useState(() => storedMuted());
  const [volume, setVolumeState] = useState(() => storedVolume());

  const volumeRef = useRef(volume);
  volumeRef.current = volume;
  const mutedRef = useRef(muted);
  mutedRef.current = muted;
  const currentVideoRef = useRef<string | null>(null);
  const endedRef = useRef(false);

  const hasTrack = broadcast?.track != null;

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
    if (!current?.track) return;
    const initialId = current.track.youtube_video_id;
    const start = targetFor(current);
    const yt = window.YT;
    let fallbackTimer: number | null = null;
    setError(false);
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
          const isPlaying = e.data === yt.PlayerState.PLAYING;
          setPlaying(isPlaying);
          if (isPlaying) endedRef.current = false;
          if (e.data === yt.PlayerState.ENDED) {
            endedRef.current = true;
            onEndedRef.current();
          }
        },
        onError: () => setError(true),
      },
    });
    playerRef.current = player;
    currentVideoRef.current = initialId;
    return () => {
      if (fallbackTimer !== null) window.clearTimeout(fallbackTimer);
      player.destroy();
      playerRef.current = null;
      currentVideoRef.current = null;
      setReady(false);
      setPlaying(false);
    };
  }, [apiReady, hasTrack, containerId]);

  useEffect(() => {
    const player = playerRef.current;
    if (!player || !broadcast?.track) return;
    const videoId = broadcast.track.youtube_video_id;
    const target = targetFor(broadcast);
    const yt = window.YT;
    if (currentVideoRef.current !== videoId) {
      currentVideoRef.current = videoId;
      endedRef.current = false;
      setError(false);
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
  }, [broadcast]);

  useEffect(() => {
    const player = playerRef.current;
    if (!player) return;
    player.setVolume(volume);
    if (muted || volume === 0) player.mute();
    else player.unMute();
  }, [volume, muted, ready, hasTrack]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      const player = playerRef.current;
      const yt = window.YT;
      if (!player || !yt) return;
      setProgress(player.getCurrentTime());
      const current = broadcastRef.current;
      if (current && player.getPlayerState() === yt.PlayerState.PLAYING) {
        const target = targetFor(current);
        if (Math.abs(player.getCurrentTime() - target) > DRIFT_THRESHOLD) {
          player.seekTo(target, true);
        }
      }
      if (endedRef.current) onEndedRef.current();
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
    error,
    muted,
    volume,
    track: broadcast?.track ?? null,
    toggleMute,
    setVolume,
  };
}
