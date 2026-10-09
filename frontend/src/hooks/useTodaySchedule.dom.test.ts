import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SlotToday } from "../types";
import { api } from "../api/client";
import { REFRESH_MS, useTodaySchedule } from "./useTodaySchedule";

vi.mock("../api/client", () => ({
  api: { scheduleToday: vi.fn() },
}));

const mocked = api as unknown as {
  scheduleToday: ReturnType<typeof vi.fn>;
};

const slot = (id: number): SlotToday => ({
  id,
  genre_id: 1,
  genre_name: "Morning",
  start_time: "05:00",
});

describe("useTodaySchedule", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("loads the schedule on mount", async () => {
    mocked.scheduleToday.mockResolvedValue({ current_id: 1, slots: [slot(1)] });
    const { result } = renderHook(() => useTodaySchedule());
    await waitFor(() => expect(result.current.today?.current_id).toBe(1));
    await waitFor(() => expect(result.current.today?.slots).toHaveLength(1));
  });

  it("refreshes on an interval", async () => {
    vi.useFakeTimers();
    mocked.scheduleToday.mockResolvedValue({ current_id: null, slots: [] });
    renderHook(() => useTodaySchedule());
    await vi.advanceTimersByTimeAsync(0);
    expect(mocked.scheduleToday).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(REFRESH_MS);
    expect(mocked.scheduleToday).toHaveBeenCalledTimes(2);
  });

  it("keeps the last good schedule when a refresh fails", async () => {
    vi.useFakeTimers();
    mocked.scheduleToday
      .mockResolvedValueOnce({ current_id: 2, slots: [slot(2)] })
      .mockRejectedValue(new Error("boom"));
    const { result } = renderHook(() => useTodaySchedule());
    await vi.advanceTimersByTimeAsync(0);
    await waitFor(() => expect(result.current.today?.current_id).toBe(2));
    await vi.advanceTimersByTimeAsync(REFRESH_MS);
    expect(result.current.today?.current_id).toBe(2);
  });
});
