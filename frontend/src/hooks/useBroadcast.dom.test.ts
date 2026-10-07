import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useBroadcast } from "./useBroadcast";

function nowResponse(overrides: Record<string, unknown> = {}) {
  return new Response(
    JSON.stringify({
      genre: null,
      track: null,
      offset_seconds: 0,
      server_time: "2026-01-01T00:00:00+00:00",
      source: "none",
      ...overrides,
    }),
    { status: 200 },
  );
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("useBroadcast", () => {
  it("loads the broadcast on mount", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(nowResponse({ source: "schedule" })),
    );
    const { result } = renderHook(() => useBroadcast());
    await waitFor(() => expect(result.current.state?.source).toBe("schedule"));
  });

  it("records the fetch time and round-trip time", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(nowResponse()));
    const { result } = renderHook(() => useBroadcast());
    await waitFor(() => expect(result.current.state).not.toBeNull());
    expect(result.current.state?.fetchedAt).toBeGreaterThan(0);
    expect(result.current.state?.rttMs).toBeGreaterThanOrEqual(0);
  });

  it("polls again after the interval", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValue(nowResponse());
    vi.stubGlobal("fetch", fetchMock);
    renderHook(() => useBroadcast());
    await act(async () => {
      await Promise.resolve();
    });
    const initial = fetchMock.mock.calls.length;
    await act(async () => {
      vi.advanceTimersByTime(5000);
      await Promise.resolve();
    });
    expect(fetchMock.mock.calls.length).toBeGreaterThan(initial);
  });

  it("keeps the previous state when a poll fails", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(nowResponse({ source: "schedule" }))
      .mockRejectedValueOnce(new Error("boom"));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useBroadcast());
    await waitFor(() => expect(result.current.state?.source).toBe("schedule"));
    await act(async () => {
      result.current.refresh();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(result.current.state?.source).toBe("schedule");
  });

  it("flags failure when a poll fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")));
    const { result } = renderHook(() => useBroadcast());
    await waitFor(() => expect(result.current.failed).toBe(true));
    expect(result.current.state).toBeNull();
  });
});

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  close = vi.fn();
  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }
}

describe("useBroadcast (radio socket)", () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("opens a radio socket on mount", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(nowResponse()));
    renderHook(() => useBroadcast());
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    expect(FakeWebSocket.instances[0].url).toContain("/api/ws/radio");
  });

  it("applies a pushed frame immediately", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(nowResponse()));
    const { result } = renderHook(() => useBroadcast());
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    act(() => {
      FakeWebSocket.instances[0].onmessage?.({
        data: JSON.stringify({
          genre: null,
          track: {
            youtube_video_id: "b",
            title: "B",
            artist: "A",
            thumbnail_url: "",
            duration_seconds: 200,
            position: 1,
          },
          offset_seconds: 0,
          server_time: "2026-01-01T00:00:00+00:00",
          source: "manual",
        }),
      });
    });
    await waitFor(() =>
      expect(result.current.state?.track?.youtube_video_id).toBe("b"),
    );
    expect(result.current.state?.source).toBe("manual");
    expect(result.current.state?.rttMs).toBe(0);
  });

  it("ignores malformed socket frames", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(nowResponse()));
    const { result } = renderHook(() => useBroadcast());
    await waitFor(() => expect(result.current.state).not.toBeNull());
    act(() => {
      FakeWebSocket.instances[0].onmessage?.({ data: "not-json" });
    });
    expect(result.current.state?.source).toBe("none");
  });

  it("reconnects after the socket closes", () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(nowResponse()));
    renderHook(() => useBroadcast());
    expect(FakeWebSocket.instances).toHaveLength(1);
    act(() => {
      FakeWebSocket.instances[0].onclose?.();
    });
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(FakeWebSocket.instances.length).toBeGreaterThanOrEqual(2);
  });
});
