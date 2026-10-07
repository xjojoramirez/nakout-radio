import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { BroadcastNow, Genre, Track } from "../types";

export const POLL_MS = 5000;
const MIN_RETRY_MS = 1000;
const MAX_RETRY_MS = 30000;

export interface BroadcastState {
  track: Track | null;
  genre: Genre | null;
  source: string;
  /** Seconds into the current track as reported by the server. */
  offset: number;
  /** `Date.now()` when the state was received. */
  fetchedAt: number;
  /** Approximate round-trip time in milliseconds. */
  rttMs: number;
}

export function radioSocketUrl(protocol: string, host: string): string {
  const scheme = protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${host}/api/ws/radio`;
}

function toState(data: BroadcastNow, rttMs: number): BroadcastState {
  return {
    track: data.track,
    genre: data.genre,
    source: data.source,
    offset: data.offset_seconds,
    fetchedAt: Date.now(),
    rttMs,
  };
}

export function useBroadcast(): {
  state: BroadcastState | null;
  failed: boolean;
  refresh: () => void;
} {
  const [state, setState] = useState<BroadcastState | null>(null);
  const [failed, setFailed] = useState(false);
  const [tick, setTick] = useState(0);

  const refresh = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    let timer: number | null = null;

    const load = async () => {
      const started = Date.now();
      try {
        const data = await api.now();
        if (cancelled) return;
        setFailed(false);
        setState(toState(data, Date.now() - started));
      } catch {
        if (!cancelled) setFailed(true);
        // keep the last known state; the next tick retries
      }
    };

    void load();
    timer = window.setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      if (timer !== null) window.clearInterval(timer);
    };
  }, [tick]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let closed = false;
    let reconnectTimer: number | null = null;
    let retryDelay = MIN_RETRY_MS;

    const scheduleReconnect = () => {
      if (closed) return;
      const jitter = 0.85 + Math.random() * 0.3;
      const delay = Math.min(MAX_RETRY_MS, retryDelay) * jitter;
      retryDelay = Math.min(MAX_RETRY_MS, retryDelay * 2);
      reconnectTimer = window.setTimeout(connect, delay);
    };

    function connect() {
      if (closed) return;
      let next: WebSocket;
      try {
        next = new WebSocket(radioSocketUrl(location.protocol, location.host));
      } catch {
        scheduleReconnect();
        return;
      }
      socket = next;
      next.onopen = () => {
        retryDelay = MIN_RETRY_MS;
      };
      next.onmessage = (event) => {
        if (closed) return;
        try {
          const data = JSON.parse(event.data) as BroadcastNow;
          setFailed(false);
          setState(toState(data, 0));
        } catch {
          // ignore malformed frames
        }
      };
      next.onclose = () => {
        if (socket === next) socket = null;
        scheduleReconnect();
      };
    }

    connect();
    return () => {
      closed = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, []);

  return { state, failed, refresh };
}
