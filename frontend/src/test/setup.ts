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

// jsdom does not implement PointerEvent constructors (jsdom#2527); RTL's
// fireEvent.pointer* falls back to a plain Event and drops pointerId/clientY.
// Polyfill on the test window via MouseEvent so coordinates flow through.
if (typeof window.PointerEvent !== "function") {
  class PointerEventPolyfill extends MouseEvent {
    readonly pointerId: number;
    readonly pointerType: string;
    readonly isPrimary: boolean;
    constructor(type: string, init: { pointerId?: number; pointerType?: string; isPrimary?: boolean } & MouseEventInit = {}) {
      const { pointerId = 0, pointerType = "", isPrimary = false, ...rest } = init;
      super(type, rest);
      this.pointerId = pointerId;
      this.pointerType = pointerType;
      this.isPrimary = isPrimary;
    }
  }
  window.PointerEvent = PointerEventPolyfill as unknown as typeof PointerEvent;
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
