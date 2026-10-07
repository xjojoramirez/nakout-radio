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
    ...overrides,
  };
}

describe("useYouTubePlayer", () => {
  let players: any[];

  beforeEach(() => {
    window.localStorage.clear();
    players = [];
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
      PlayerState: { PLAYING: 1, ENDED: 8 },
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
});
