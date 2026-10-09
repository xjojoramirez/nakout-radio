import "@testing-library/jest-dom";
import { vi } from "vitest";

// @testing-library's `waitFor` and act() drain detect fake timers via a
// global `jest` and advance them with `jest.advanceTimersByTime`. Vitest does
// not provide one, so alias `vi` (API-compatible for these calls); the shim
// only takes effect when fake timers are installed.
(globalThis as unknown as Record<string, unknown>).jest = vi;

if (typeof Element.prototype.scrollIntoView !== "function") {
  Element.prototype.scrollIntoView = () => {};
}

if (typeof window.matchMedia !== "function") {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      onchange: null,
      dispatchEvent: () => false,
    }),
  });
}

class StubWebSocket {
  static readonly OPEN = 1;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  constructor(readonly url: string) {}
  close() {}
}
(globalThis as unknown as { WebSocket: unknown }).WebSocket = StubWebSocket;
