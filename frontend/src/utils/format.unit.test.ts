import { describe, expect, it } from "vitest";
import { fmtMin, minutesOf, timeAgo, twelveHour } from "./format";

describe("schedule time helpers", () => {
  it("minutesOf()", () => {
    expect(minutesOf("06:05")).toBe(365);
    expect(minutesOf("00:00")).toBe(0);
  });

  it("twelveHour()", () => {
    expect(twelveHour(0)).toBe("Midnight");
    expect(twelveHour(390)).toBe("6:30 AM");
    expect(twelveHour(810)).toBe("1:30 PM");
    expect(twelveHour(1439)).toBe("11:59 PM");
    expect(twelveHour(1440)).toBe("Midnight");
  });

  it("fmtMin()", () => {
    expect(fmtMin(90)).toBe("1h 30m");
    expect(fmtMin(45)).toBe("45m");
    expect(fmtMin(120)).toBe("2h");
  });

  it("timeAgo()", () => {
    const now = Date.parse("2026-10-09T12:00:00Z");
    expect(timeAgo("2026-10-09T11:59:31Z", now)).toBe("just now");
    expect(timeAgo("2026-10-09T11:55:00Z", now)).toBe("5 min ago");
    expect(timeAgo("2026-10-09T10:00:00Z", now)).toBe("2h ago");
    expect(timeAgo("2026-10-06T12:00:00Z", now)).toBe("3d ago");
    expect(timeAgo(null, now)).toBe("never");
    expect(timeAgo("2026-10-09T11:55:00", now)).toBe("5 min ago"); // tolerant of missing Z
    expect(timeAgo("2026-10-09T11:55:00+00:00", now)).toBe("5 min ago");
    expect(timeAgo("2026-10-09T11:55:00+02:00", now)).toBe("2h ago"); // offset honoured
  });
});
