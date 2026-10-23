import { describe, expect, it } from "vitest";
import { formatClock, hourLabel, slotRange, todayScheduleRows } from "./deck";

const today = {
  current_id: 2,
  slots: [
    { id: 1, genre_id: 1, genre_name: "Morning", start_time: "05:00" },
    { id: 2, genre_id: 2, genre_name: "Evening", start_time: "17:00" },
  ],
};

describe("deck formatting helpers", () => {
  it("formats mm:ss clock", () => {
    expect(formatClock(0)).toBe("0:00");
    expect(formatClock(73)).toBe("1:13");
    expect(formatClock(-5)).toBe("0:00");
  });

  it("formats hours", () => {
    expect(hourLabel("05:00")).toBe("5 am");
    expect(hourLabel("17:30")).toBe("5:30 pm");
    expect(hourLabel("00:15")).toBe("12:15 am");
  });

  it("renders slot ranges with wraparound for the last slot", () => {
    const rows = todayScheduleRows(today);
    expect(rows[0]).toEqual({
      id: 1,
      name: "Morning",
      range: "5 am – 5 pm",
      isNow: false,
    });
    expect(rows[1]).toEqual({
      id: 2,
      name: "Evening",
      range: "5 pm – 5 am",
      isNow: true,
    });
  });

  it("renders a single slot without a range", () => {
    expect(
      todayScheduleRows({
        current_id: null,
        slots: [today.slots[0]],
      }),
    ).toEqual([
      { id: 1, name: "Morning", range: "5 am", isNow: false },
    ]);
  });

  it("prepends a carry-over slot that is still playing", () => {
    const rows = todayScheduleRows({
      current_id: 9,
      slots: [today.slots[0]],
      carry: {
        id: 9,
        genre_id: 3,
        genre_name: "Night",
        start_time: "22:00",
      },
    });
    expect(rows).toEqual([
      { id: 9, name: "Night", range: "10 pm – 5 am", isNow: true },
      { id: 1, name: "Morning", range: "5 am", isNow: false },
    ]);
  });

  it("renders a lone carry-over slot without a range", () => {
    const rows = todayScheduleRows({
      current_id: 9,
      slots: [],
      carry: {
        id: 9,
        genre_id: 3,
        genre_name: "Night",
        start_time: "22:00",
      },
    });
    expect(rows).toEqual([
      { id: 9, name: "Night", range: "10 pm", isNow: true },
    ]);
  });

  it("returns no rows before data arrives", () => {
    expect(todayScheduleRows(null)).toEqual([]);
  });
});
