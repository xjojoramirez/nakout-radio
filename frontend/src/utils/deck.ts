import type { ScheduleToday } from "../types";

export function formatClock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function hourLabel(hhmm: string): string {
  const [h, m] = hhmm.split(":").map(Number);
  const suffix = h < 12 ? "am" : "pm";
  const hour12 = h % 12 === 0 ? 12 : h % 12;
  return m === 0
    ? `${hour12} ${suffix}`
    : `${hour12}:${String(m).padStart(2, "0")} ${suffix}`;
}

export function slotRange(times: string[], index: number): string {
  const start = hourLabel(times[index]);
  if (times.length === 1) return start;
  const next = times[(index + 1) % times.length];
  return `${start} – ${hourLabel(next)}`;
}

export interface ScheduleRow {
  id: number;
  name: string;
  range: string;
  isNow: boolean;
}

export function todayScheduleRows(
  today: ScheduleToday | null,
): ScheduleRow[] {
  if (!today) return [];
  const times = today.slots.map((s) => s.start_time);
  return today.slots.map((slot, index) => ({
    id: slot.id,
    name: slot.genre_name,
    range: slotRange(times, index),
    isNow: today.current_id === slot.id,
  }));
}
