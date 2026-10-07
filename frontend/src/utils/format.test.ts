import { describe, expect, it } from "vitest";
import { formatDuration, secondsUntilNextMinute } from "./format";

describe("formatDuration", () => {
  it("formats seconds as m:ss", () => {
    expect(formatDuration(0)).toBe("0:00");
    expect(formatDuration(65)).toBe("1:05");
    expect(formatDuration(3605)).toBe("60:05");
  });
});

describe("secondsUntilNextMinute", () => {
  it("returns seconds to the next minute boundary", () => {
    expect(secondsUntilNextMinute(new Date(2026, 0, 1, 6, 30, 15))).toBe(45);
  });
});
