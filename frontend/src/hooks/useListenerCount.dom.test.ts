import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useListenerCount } from "./useListenerCount";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  close = vi.fn();

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }
}

describe("useListenerCount (dom)", () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    (globalThis as unknown as { WebSocket: unknown }).WebSocket = FakeWebSocket;
  });

  afterEach(() => {
    vi.useRealTimers();
    delete (globalThis as unknown as { WebSocket?: unknown }).WebSocket;
  });

  it("opens exactly one socket on mount", () => {
    renderHook(() => useListenerCount());
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("updates the count from socket messages", async () => {
    const { result } = renderHook(() => useListenerCount());
    act(() => {
      FakeWebSocket.instances[0].onmessage?.({
        data: JSON.stringify({ count: 5 }),
      });
    });
    await waitFor(() => expect(result.current).toBe(5));
  });

  it("ignores malformed frames", async () => {
    const { result } = renderHook(() => useListenerCount());
    act(() => {
      FakeWebSocket.instances[0].onmessage?.({ data: "not-json" });
    });
    expect(result.current).toBe(0);
  });

  it("reconnects after the socket closes", () => {
    vi.useFakeTimers();
    renderHook(() => useListenerCount());
    expect(FakeWebSocket.instances).toHaveLength(1);
    act(() => {
      FakeWebSocket.instances[0].onclose?.();
    });
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(FakeWebSocket.instances.length).toBeGreaterThanOrEqual(2);
  });

  it("closes the socket and stops reconnecting on unmount", () => {
    vi.useFakeTimers();
    const { unmount } = renderHook(() => useListenerCount());
    const first = FakeWebSocket.instances[0];
    unmount();
    expect(first.close).toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(60000);
    });
    expect(FakeWebSocket.instances).toHaveLength(1);
  });
});
