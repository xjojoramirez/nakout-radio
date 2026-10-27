import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { TrackDetail, TrackDetailStatus } from "../types";

interface State {
  videoId: string | null;
  detail: TrackDetail | null;
  status: TrackDetailStatus;
}

function isNotFound(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "status" in error &&
    (error as { status?: unknown }).status === 404
  );
}

/**
 * Details for the track on air, fetched once per video and cached for the
 * session. A track without details is a normal "missing" state, not an error.
 */
export function useTrackDetails(videoId: string | null) {
  const cache = useRef(new Map<string, TrackDetail>());
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<State>({
    videoId: null,
    detail: null,
    status: "idle",
  });

  useEffect(() => {
    if (!videoId) {
      setState({ videoId: null, detail: null, status: "idle" });
      return;
    }
    const cached = cache.current.get(videoId);
    if (cached) {
      setState({ videoId, detail: cached, status: "ready" });
      return;
    }

    let active = true;
    setState({ videoId, detail: null, status: "loading" });
    api.trackDetail(videoId).then(
      (detail) => {
        if (!active) return;
        cache.current.set(videoId, detail);
        setState({ videoId, detail, status: "ready" });
      },
      (error: unknown) => {
        if (!active) return;
        setState({
          videoId,
          detail: null,
          status: isNotFound(error) ? "missing" : "error",
        });
      },
    );

    return () => {
      active = false;
    };
  }, [videoId, attempt]);

  const retry = useCallback(() => setAttempt((count) => count + 1), []);

  const current = state.videoId === videoId;
  return {
    detail: current ? state.detail : null,
    status: !videoId ? "idle" : current ? state.status : "loading",
    retry,
  } satisfies {
    detail: TrackDetail | null;
    status: TrackDetailStatus;
    retry: () => void;
  };
}
