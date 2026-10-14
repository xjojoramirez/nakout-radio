import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BroadcastState } from "./useBroadcast";
import { useYouTubePlayer } from "./useYouTubePlayer";

function broadcast(overrides: Partial<BroadcastState> = {}): BroadcastState {
  return {
    track: {
      youtube_video_id: "a",
      title: "a",
      artist: "",
      thumbnail_url: "",
      duration_seconds: 200,
      position: 0,
    },
    genre: null,
    source: "schedule",
    offset: 0,
    fetchedAt: Date.now(),
    rttMs: 0,
    phase: "playing",
    nextTrack: null,
    secondsUntilStart: null,
    preloadLead: 0,
    ...overrides,
  };
}

function nextTrack() {
  return { ...broadcast().track!, youtube_video_id: "b", title: "b" };
}

describe("useYouTubePlayer", () => {
  let players: any[];

  beforeEach(() => {
    window.localStorage.clear();
    players = [];
    if (!document.getElementById("yt-preload")) {
      const preloadEl = document.createElement("div");
      preloadEl.id = "yt-preload";
      document.body.appendChild(preloadEl);
    }
    class FakePlayer {
      opts: any;
      loadVideoById = vi.fn();
      playVideo = vi.fn();
      pauseVideo = vi.fn();
      mute = vi.fn();
      unMute = vi.fn();
      setVolume = vi.fn();
      seekTo = vi.fn();
      getPlayerState = vi.fn(() => 1);
      getCurrentTime = vi.fn(() => 0);
      destroy = vi.fn();
      constructor(_el: string, opts: any) {
        this.opts = opts;
        players.push(this);
      }
    }
    (window as unknown as { YT: unknown }).YT = {
      PlayerState: { PLAYING: 1, ENDED: 8, PAUSED: 2, CUED: 5 },
      Player: FakePlayer,
    };
  });

  afterEach(() => {
    delete (window as unknown as { YT?: unknown }).YT;
    vi.useRealTimers();
  });

  it("creates a muted autoplay player for the live track", async () => {
    renderHook(() => useYouTubePlayer("yt-player", broadcast(), vi.fn()));
    await waitFor(() => expect(players.length).toBe(1));
    expect(players[0].opts.videoId).toBe("a");
    expect(players[0].opts.playerVars.autoplay).toBe(1);
    expect(players[0].opts.playerVars.mute).toBe(1);
  });

  it("does not create a player while off air", async () => {
    renderHook(() =>
      useYouTubePlayer("yt-player", broadcast({ track: null }), vi.fn()),
    );
    await Promise.resolve();
    expect(players.length).toBe(0);
  });

  it("loads a changed track at the broadcast offset", async () => {
    const { rerender } = renderHook(
      ({ b }: { b: BroadcastState }) =>
        useYouTubePlayer("yt-player", b, vi.fn()),
      { initialProps: { b: broadcast() } },
    );
    await waitFor(() => expect(players.length).toBe(1));
    rerender({
      b: broadcast({
        track: { ...broadcast().track!, youtube_video_id: "b" },
        offset: 12,
      }),
    });
    await waitFor(() =>
      expect(players[0].loadVideoById).toHaveBeenCalledWith({
        videoId: "b",
        startSeconds: expect.any(Number),
      }),
    );
  });

  it("seeks when the broadcast offset drifts from playback", async () => {
    const { rerender } = renderHook(
      ({ b }: { b: BroadcastState }) =>
        useYouTubePlayer("yt-player", b, vi.fn()),
      { initialProps: { b: broadcast() } },
    );
    await waitFor(() => expect(players.length).toBe(1));
    players[0].getCurrentTime = vi.fn(() => 0);
    rerender({ b: broadcast({ offset: 30, fetchedAt: Date.now() }) });
    await waitFor(() => expect(players[0].seekTo).toHaveBeenCalled());
  });

  it("requests a resync when the track ends", async () => {
    const onEnded = vi.fn();
    renderHook(() => useYouTubePlayer("yt-player", broadcast(), onEnded));
    await waitFor(() => expect(players.length).toBe(1));
    act(() => {
      players[0].opts.events.onStateChange({ data: 8 });
    });
    expect(onEnded).toHaveBeenCalled();
  });

  it("auto-reloads the current track after the player errors", async () => {
    vi.useFakeTimers();
    renderHook(() => useYouTubePlayer("yt-player", broadcast(), vi.fn()));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    act(() => {
      players[0].opts.events.onError();
    });
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(players[0].loadVideoById).toHaveBeenCalledWith({
      videoId: "a",
      startSeconds: expect.any(Number),
    });
  });

  it("backs off between repeated errors", async () => {
    vi.useFakeTimers();
    renderHook(() => useYouTubePlayer("yt-player", broadcast(), vi.fn()));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    const onError = players[0].opts.events.onError;
    act(() => {
      onError();
    });
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(players[0].loadVideoById).toHaveBeenCalledTimes(1);
    act(() => {
      onError();
    });
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(players[0].loadVideoById).toHaveBeenCalledTimes(1);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(players[0].loadVideoById).toHaveBeenCalledTimes(2);
  });

  it("resets the retry backoff once playback resumes", async () => {
    vi.useFakeTimers();
    renderHook(() => useYouTubePlayer("yt-player", broadcast(), vi.fn()));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    act(() => {
      players[0].opts.events.onError();
    });
    act(() => {
      players[0].opts.events.onStateChange({ data: 1 });
    });
    act(() => {
      players[0].opts.events.onError();
    });
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(players[0].loadVideoById).toHaveBeenCalledTimes(1);
  });

  it("starts muted on first visit", () => {
    const { result } = renderHook(() =>
      useYouTubePlayer("yt-player", broadcast(), vi.fn()),
    );
    expect(result.current.muted).toBe(true);
  });

  it("toggleMute updates state and storage", async () => {
    const { result } = renderHook(() =>
      useYouTubePlayer("yt-player", broadcast(), vi.fn()),
    );
    await waitFor(() => expect(players.length).toBe(1));
    act(() => {
      result.current.toggleMute();
    });
    await waitFor(() => expect(result.current.muted).toBe(false));
    expect(window.localStorage.getItem("nakout.muted")).toBe("false");
  });

  it("setVolume clamps, persists, and unmutes", async () => {
    const { result } = renderHook(() =>
      useYouTubePlayer("yt-player", broadcast(), vi.fn()),
    );
    await waitFor(() => expect(players.length).toBe(1));
    act(() => {
      result.current.setVolume(150);
    });
    await waitFor(() => expect(result.current.volume).toBe(100));
    expect(window.localStorage.getItem("nakout.volume")).toBe("100");
    expect(result.current.muted).toBe(false);
  });

  it("falls back to muted when autoplay with sound is blocked", async () => {
    vi.useFakeTimers();
    window.localStorage.setItem("nakout.muted", "false");
    const { result } = renderHook(() =>
      useYouTubePlayer("yt-player", broadcast(), vi.fn()),
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    players[0].getPlayerState.mockReturnValue(0);
    act(() => {
      players[0].opts.events.onReady();
    });
    act(() => {
      vi.advanceTimersByTime(1600);
    });
    expect(players[0].mute).toHaveBeenCalled();
    expect(result.current.muted).toBe(true);
    expect(window.localStorage.getItem("nakout.muted")).toBe("true");
  });

  it("starts playback at the server offset", async () => {
    renderHook(() =>
      useYouTubePlayer("yt-player", broadcast({ offset: 42 }), vi.fn()),
    );
    await waitFor(() => expect(players.length).toBe(1));
    expect(players[0].opts.playerVars.start).toBeGreaterThanOrEqual(42);
  });

  it("does not seek while the player is not playing", async () => {
    vi.useFakeTimers();
    renderHook(() =>
      useYouTubePlayer("yt-player", broadcast({ offset: 0 }), vi.fn()),
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    players[0].getPlayerState.mockReturnValue(0);
    players[0].getCurrentTime.mockReturnValue(0);
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(players[0].seekTo).not.toHaveBeenCalled();
  });

  it("resumes a player the mobile OS paused while the track is still live", async () => {
    vi.useFakeTimers();
    renderHook(() =>
      useYouTubePlayer("yt-player", broadcast({ offset: 10 }), vi.fn()),
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    players[0].getPlayerState.mockReturnValue(2);
    players[0].getCurrentTime.mockReturnValue(5);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(players[0].seekTo).toHaveBeenCalledWith(expect.any(Number), true);
    expect(players[0].playVideo).toHaveBeenCalledTimes(1);
  });

  it("throttles resume attempts while the player stays non-playing", async () => {
    vi.useFakeTimers();
    renderHook(() => useYouTubePlayer("yt-player", broadcast(), vi.fn()));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    players[0].getPlayerState.mockReturnValue(2);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(players[0].playVideo).toHaveBeenCalledTimes(1);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(players[0].playVideo).toHaveBeenCalledTimes(1);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(players[0].playVideo).toHaveBeenCalledTimes(1);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(players[0].playVideo).toHaveBeenCalledTimes(2);
  });

  it("resumes immediately again after playback stops a second time", async () => {
    vi.useFakeTimers();
    renderHook(() => useYouTubePlayer("yt-player", broadcast(), vi.fn()));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    players[0].getPlayerState.mockReturnValue(2);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(players[0].playVideo).toHaveBeenCalledTimes(1);
    players[0].getPlayerState.mockReturnValue(1);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    players[0].getPlayerState.mockReturnValue(5);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(players[0].playVideo).toHaveBeenCalledTimes(2);
  });

  it("does not interfere while the player is buffering", async () => {
    vi.useFakeTimers();
    renderHook(() =>
      useYouTubePlayer("yt-player", broadcast({ offset: 0 }), vi.fn()),
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    players[0].getPlayerState.mockReturnValue(3);
    players[0].getCurrentTime.mockReturnValue(0);
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(players[0].seekTo).not.toHaveBeenCalled();
    expect(players[0].playVideo).not.toHaveBeenCalled();
  });

  it("clears the autoplay fallback timer on unmount", async () => {
    vi.useFakeTimers();
    window.localStorage.setItem("nakout.muted", "false");
    const { unmount } = renderHook(() =>
      useYouTubePlayer("yt-player", broadcast(), vi.fn()),
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    act(() => {
      players[0].opts.events.onReady();
    });
    const player = players[0];
    unmount();
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(player.mute).not.toHaveBeenCalled();
  });

  it("reloads the same track when it ends and the server restarts it", async () => {
    const { rerender } = renderHook(
      ({ b }: { b: BroadcastState }) =>
        useYouTubePlayer("yt-player", b, vi.fn()),
      { initialProps: { b: broadcast() } },
    );
    await waitFor(() => expect(players.length).toBe(1));
    players[0].getPlayerState.mockReturnValue(8);
    players[0].getCurrentTime.mockReturnValue(200);
    rerender({ b: broadcast({ offset: 0, fetchedAt: Date.now() }) });
    await waitFor(() =>
      expect(players[0].loadVideoById).toHaveBeenCalledWith({
        videoId: "a",
        startSeconds: expect.any(Number),
      }),
    );
  });

  it("keeps requesting a resync while the track has ended", async () => {
    vi.useFakeTimers();
    const onEnded = vi.fn();
    renderHook(() => useYouTubePlayer("yt-player", broadcast(), onEnded));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    players[0].getPlayerState.mockReturnValue(8);
    act(() => {
      players[0].opts.events.onStateChange({ data: 8 });
    });
    expect(onEnded).toHaveBeenCalledTimes(1);
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(onEnded.mock.calls.length).toBeGreaterThan(1);
  });

  it("does not call player methods before the player is ready", async () => {
    vi.useFakeTimers();
    class LazyPlayer {
      opts: any;
      loadVideoById = vi.fn();
      playVideo = vi.fn();
      mute = vi.fn();
      unMute = vi.fn();
      setVolume = vi.fn();
      seekTo = vi.fn();
      destroy = vi.fn();
      // The real YouTube API only exposes these once the player is ready.
      getCurrentTime?: () => number;
      getPlayerState?: () => number;
      constructor(_el: string, opts: any) {
        this.opts = opts;
        players.push(this);
      }
      bind() {
        this.getCurrentTime = vi.fn(() => 0);
        this.getPlayerState = vi.fn(() => 1);
      }
    }
    (window as unknown as { YT: unknown }).YT = {
      PlayerState: { PLAYING: 1, ENDED: 8, PAUSED: 2, CUED: 5 },
      Player: LazyPlayer,
    };

    const { rerender } = renderHook(
      ({ b }: { b: BroadcastState }) =>
        useYouTubePlayer("yt-player", b, vi.fn()),
      { initialProps: { b: broadcast() } },
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    const player = players[0] as LazyPlayer;

    expect(() => {
      rerender({ b: broadcast({ offset: 20, fetchedAt: Date.now() }) });
    }).not.toThrow();
    expect(() => {
      act(() => {
        vi.advanceTimersByTime(3000);
      });
    }).not.toThrow();
    expect(player.seekTo).not.toHaveBeenCalled();

    act(() => {
      player.bind();
      player.opts.events.onReady();
    });
    rerender({ b: broadcast({ offset: 30, fetchedAt: Date.now() }) });
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    expect(player.seekTo).toHaveBeenCalled();
  });

  it("preloads the next track muted and paused during a gap", async () => {
    const { rerender } = renderHook(
      ({ b }: { b: BroadcastState }) =>
        useYouTubePlayer("yt-player", b, vi.fn()),
      { initialProps: { b: broadcast() } },
    );
    await waitFor(() => expect(players.length).toBe(1));
    rerender({
      b: broadcast({
        phase: "gap",
        nextTrack: nextTrack(),
        secondsUntilStart: 2,
        fetchedAt: Date.now(),
      }),
    });
    await waitFor(() =>
      expect(players[0].loadVideoById).toHaveBeenCalledWith({
        videoId: "b",
        startSeconds: 0,
      }),
    );
    expect(players[0].mute).toHaveBeenCalled();
    expect(players[0].pauseVideo).toHaveBeenCalled();
    expect(players[0].playVideo).not.toHaveBeenCalled();
  });

  it("does not drift-correct or auto-resume during a gap", async () => {
    vi.useFakeTimers();
    const { rerender } = renderHook(
      ({ b }: { b: BroadcastState }) =>
        useYouTubePlayer("yt-player", b, vi.fn()),
      { initialProps: { b: broadcast({ offset: 10 }) } },
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    rerender({
      b: broadcast({
        phase: "gap",
        nextTrack: nextTrack(),
        secondsUntilStart: 5,
        fetchedAt: Date.now(),
      }),
    });
    players[0].seekTo.mockClear();
    players[0].playVideo.mockClear();
    players[0].getPlayerState.mockReturnValue(2); // PAUSED during preload
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(players[0].seekTo).not.toHaveBeenCalled();
    expect(players[0].playVideo).not.toHaveBeenCalled();
  });

  it("stops requesting a resync while the gap is on", async () => {
    vi.useFakeTimers();
    const onEnded = vi.fn();
    const { rerender } = renderHook(
      ({ b }: { b: BroadcastState }) =>
        useYouTubePlayer("yt-player", b, onEnded),
      { initialProps: { b: broadcast() } },
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    act(() => {
      players[0].opts.events.onStateChange({ data: 8 });
    });
    expect(onEnded).toHaveBeenCalledTimes(1);
    rerender({
      b: broadcast({
        phase: "gap",
        nextTrack: nextTrack(),
        secondsUntilStart: 5,
        fetchedAt: Date.now(),
      }),
    });
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(onEnded).toHaveBeenCalledTimes(1);
  });

  it("retries the upcoming track when preloading fails during a gap", async () => {
    vi.useFakeTimers();
    const { rerender } = renderHook(
      ({ b }: { b: BroadcastState }) =>
        useYouTubePlayer("yt-player", b, vi.fn()),
      { initialProps: { b: broadcast() } },
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    rerender({
      b: broadcast({
        phase: "gap",
        nextTrack: nextTrack(),
        secondsUntilStart: 10,
        fetchedAt: Date.now(),
      }),
    });
    act(() => {
      players[0].opts.events.onError();
    });
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(players[0].loadVideoById).toHaveBeenLastCalledWith({
      videoId: "b",
      startSeconds: 0,
    });
  });

  it("starts the preloaded track when the gap ends", async () => {
    vi.useFakeTimers();
    const { rerender } = renderHook(
      ({ b }: { b: BroadcastState }) =>
        useYouTubePlayer("yt-player", b, vi.fn()),
      { initialProps: { b: broadcast() } },
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    act(() => {
      rerender({
        b: broadcast({
          phase: "gap",
          nextTrack: nextTrack(),
          secondsUntilStart: 2,
          fetchedAt: Date.now(),
          rttMs: 0,
        }),
      });
    });
    expect(players[0].loadVideoById).toHaveBeenCalledWith({
      videoId: "b",
      startSeconds: 0,
    });
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(players[0].seekTo).toHaveBeenCalledWith(0, true);
    expect(players[0].playVideo).toHaveBeenCalledTimes(1);
  });

  it("cancels a pending gap start when a playing frame arrives", async () => {
    vi.useFakeTimers();
    const { rerender } = renderHook(
      ({ b }: { b: BroadcastState }) =>
        useYouTubePlayer("yt-player", b, vi.fn()),
      { initialProps: { b: broadcast() } },
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    act(() => {
      rerender({
        b: broadcast({
          phase: "gap",
          nextTrack: nextTrack(),
          secondsUntilStart: 2,
          fetchedAt: Date.now(),
        }),
      });
    });
    act(() => {
      vi.advanceTimersByTime(500);
    });
    act(() => {
      rerender({
        b: broadcast({
          track: nextTrack(),
          offset: 0,
          fetchedAt: Date.now(),
        }),
      });
    });
    expect(players[0].playVideo).toHaveBeenCalledTimes(1);
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(players[0].playVideo).toHaveBeenCalledTimes(1);
  });

  it("reuses the preloaded video instead of reloading it when it goes live", async () => {
    const { rerender } = renderHook(
      ({ b }: { b: BroadcastState }) =>
        useYouTubePlayer("yt-player", b, vi.fn()),
      { initialProps: { b: broadcast() } },
    );
    await waitFor(() => expect(players.length).toBe(1));
    rerender({
      b: broadcast({
        phase: "gap",
        nextTrack: nextTrack(),
        secondsUntilStart: 2,
        fetchedAt: Date.now(),
      }),
    });
    await waitFor(() =>
      expect(players[0].loadVideoById).toHaveBeenCalledWith({
        videoId: "b",
        startSeconds: 0,
      }),
    );
    rerender({
      b: broadcast({ track: nextTrack(), offset: 0, fetchedAt: Date.now() }),
    });
    await waitFor(() => expect(players[0].seekTo).toHaveBeenCalled());
    expect(players[0].loadVideoById).toHaveBeenCalledTimes(1);
  });

  it("joins mid-gap with the next video paused and starts it at the boundary", async () => {
    vi.useFakeTimers();
    renderHook(() =>
      useYouTubePlayer(
        "yt-player",
        broadcast({
          phase: "gap",
          nextTrack: nextTrack(),
          secondsUntilStart: 2,
          fetchedAt: Date.now(),
        }),
        vi.fn(),
      ),
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    expect(players[0].opts.videoId).toBe("b");
    expect(players[0].opts.playerVars.start).toBe(0);
    act(() => {
      players[0].opts.events.onReady();
    });
    expect(players[0].pauseVideo).toHaveBeenCalled();
    expect(players[0].loadVideoById).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(players[0].playVideo).toHaveBeenCalledTimes(1);
  });

  it("pre-rolls the next track muted inside the lead window", async () => {
    vi.useFakeTimers();
    renderHook(() =>
      useYouTubePlayer(
        "yt-player",
        broadcast({
          nextTrack: nextTrack(),
          secondsUntilStart: 25,
          preloadLead: 20,
        }),
        vi.fn(),
      ),
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    act(() => {
      vi.advanceTimersByTime(5000); // crosses boundaryAt - 20 s
    });
    expect(players.length).toBe(2);
    expect(players[1].loadVideoById).toHaveBeenCalledWith({
      videoId: "b",
      startSeconds: 0,
    });
    expect(players[1].mute).toHaveBeenCalled();
    expect(players[1].playVideo).toHaveBeenCalled();
    expect(players[0].loadVideoById).not.toHaveBeenCalled();
  });

  it("does not pre-roll when the lead is disabled", async () => {
    vi.useFakeTimers();
    renderHook(() =>
      useYouTubePlayer(
        "yt-player",
        broadcast({
          nextTrack: nextTrack(),
          secondsUntilStart: 5,
          preloadLead: 0,
        }),
        vi.fn(),
      ),
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    act(() => {
      vi.advanceTimersByTime(30000);
    });
    expect(players.length).toBe(1);
  });

  it("swaps to the preloaded player at the boundary", async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() =>
      useYouTubePlayer(
        "yt-player",
        broadcast({
          nextTrack: nextTrack(),
          secondsUntilStart: 25,
          preloadLead: 20,
        }),
        vi.fn(),
      ),
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    act(() => {
      players[0].opts.events.onStateChange({ data: 1 }); // on air
    });
    act(() => {
      vi.advanceTimersByTime(5000); // arm
    });
    expect(players.length).toBe(2);
    act(() => {
      vi.advanceTimersByTime(20000); // reach the boundary
    });
    expect(players[1].seekTo).toHaveBeenCalled();
    expect(players[1].playVideo).toHaveBeenCalled();
    expect(players[1].setVolume).toHaveBeenCalledWith(70);
    expect(players[0].pauseVideo).toHaveBeenCalled();
    expect(result.current.playing).toBe(true);
  });

  it("ignores state events from the demoted player after a swap", async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() =>
      useYouTubePlayer(
        "yt-player",
        broadcast({
          nextTrack: nextTrack(),
          secondsUntilStart: 25,
          preloadLead: 20,
        }),
        vi.fn(),
      ),
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    act(() => {
      players[0].opts.events.onStateChange({ data: 1 });
    });
    act(() => {
      vi.advanceTimersByTime(25000); // arm + swap
    });
    act(() => {
      players[0].opts.events.onStateChange({ data: 2 }); // late PAUSED
    });
    expect(result.current.playing).toBe(true);
  });

  it("keeps the active player idle during a gap when the preload is healthy", async () => {
    vi.useFakeTimers();
    const { rerender } = renderHook(
      ({ b }: { b: BroadcastState }) =>
        useYouTubePlayer("yt-player", b, vi.fn()),
      {
        initialProps: {
          b: broadcast({
            nextTrack: nextTrack(),
            secondsUntilStart: 25,
            preloadLead: 20,
          }),
        },
      },
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    act(() => {
      vi.advanceTimersByTime(5000); // arm
    });
    expect(players.length).toBe(2);
    players[0].loadVideoById.mockClear();
    act(() => {
      rerender({
        b: broadcast({
          phase: "gap",
          nextTrack: nextTrack(),
          secondsUntilStart: 2,
          preloadLead: 20,
          fetchedAt: Date.now(),
        }),
      });
    });
    expect(players[0].loadVideoById).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(players[1].playVideo).toHaveBeenCalled();
  });
});
