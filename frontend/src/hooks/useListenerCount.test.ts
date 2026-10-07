import { describe, expect, it } from "vitest";
import { listenerSocketUrl } from "./useListenerCount";

describe("listenerSocketUrl", () => {
  it("uses ws scheme on http", () => {
    expect(listenerSocketUrl("http:", "example.com")).toBe(
      "ws://example.com/api/ws/listeners",
    );
  });
  it("uses wss scheme on https", () => {
    expect(listenerSocketUrl("https:", "example.com")).toBe(
      "wss://example.com/api/ws/listeners",
    );
  });
});
