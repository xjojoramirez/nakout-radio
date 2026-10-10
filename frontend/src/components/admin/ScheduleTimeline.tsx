import type { CSSProperties, MouseEvent } from "react";
import type { ScheduleSlot } from "../../types";
import { minutesOf, twelveHour } from "../../utils/format";

/** Full weekday names indexed by the app's day ints (0 = Monday). */
const DAY_FULL = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

interface Seg {
  kind: "slot" | "carry" | "gap";
  from: number;
  to: number;
  slot: ScheduleSlot | null;
  fromDay: number;
}

export function slotsForDay(
  all: ScheduleSlot[],
  day: number,
): ScheduleSlot[] {
  return all
    .filter((s) => s.days_of_week.includes(day))
    .sort((a, b) => a.start_time.localeCompare(b.start_time));
}

/** Last slot starting strictly before `day` (searches the previous six days). */
export function lastBefore(
  all: ScheduleSlot[],
  day: number,
): { slot: ScheduleSlot; day: number } | null {
  for (let off = 1; off <= 6; off++) {
    const d = (day - off + 7) % 7;
    const list = slotsForDay(all, d);
    if (list.length) return { slot: list[list.length - 1], day: d };
  }
  return null;
}

export function buildSegs(all: ScheduleSlot[], day: number): Seg[] {
  const list = slotsForDay(all, day);
  const first = list.length
    ? minutesOf(list[0].start_time)
    : 1440;
  const segs: Seg[] = [];
  if (first > 0) {
    const carry = lastBefore(all, day);
    segs.push(
      carry
        ? { kind: "carry", from: 0, to: first, slot: carry.slot, fromDay: carry.day }
        : { kind: "gap", from: 0, to: first, slot: null, fromDay: -1 },
    );
  }
  list.forEach((s, i) => {
    const from = minutesOf(s.start_time);
    const to = i < list.length - 1 ? minutesOf(list[i + 1].start_time) : 1440;
    segs.push({ kind: "slot", from, to, slot: s, fromDay: -1 });
  });
  return segs;
}

function tickLabel(h: number): string {
  return `${h % 12 || 12} ${h % 24 >= 12 ? "PM" : "AM"}`;
}

interface Props {
  day: number;
  slots: ScheduleSlot[];
  colours: Map<number, string>;
  nowMinutes: number | null;
  onOpenSlot: (id: number) => void;
  onOpenNew: (minute: number) => void;
}

export function ScheduleTimeline({
  day,
  slots,
  colours,
  nowMinutes,
  onOpenSlot,
  onOpenNew,
}: Props) {
  const segs = buildSegs(slots, day);

  const handleStripClick = (e: MouseEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    if (target.closest("button")) return;
    const rect = e.currentTarget.getBoundingClientRect();
    if (!rect.width) return;
    const raw = ((e.clientX - rect.left) / rect.width) * 1440;
    const min = Math.round(raw / 30) * 30;
    onOpenNew(Math.min(1410, Math.max(0, min)));
  };

  return (
    <div className="tlscroll">
      <div className="tlinner">
        <div
          className="tl"
          aria-label={`Timeline for ${DAY_FULL[day]}`}
          onClick={handleStripClick}
        >
          {segs.map((seg, i) => {
            if (seg.kind === "slot") {
              const s = seg.slot as ScheduleSlot;
              return (
                <button
                  key={s.id}
                  type="button"
                  className="blk"
                  title={`${s.genre_name} · ${twelveHour(seg.from)} to ${twelveHour(seg.to)}`}
                  style={
                    {
                      left: `${(seg.from / 1440) * 100}%`,
                      width: `${((seg.to - seg.from) / 1440) * 100}%`,
                      "--gc": colours.get(s.genre_id) ?? "var(--amber)",
                    } as CSSProperties
                  }
                  onClick={() => onOpenSlot(s.id)}
                >
                  <span className="bn">{s.genre_name}</span>
                  <span className="bt">{twelveHour(seg.from)}</span>
                </button>
              );
            }
            if (seg.kind === "carry") {
              const s = seg.slot as ScheduleSlot;
              return (
                <div
                  key={`carry-${i}`}
                  className="blk carry"
                  title={`Continues from ${DAY_FULL[seg.fromDay]}`}
                  style={
                    {
                      left: `${(seg.from / 1440) * 100}%`,
                      width: `${((seg.to - seg.from) / 1440) * 100}%`,
                      "--gc": colours.get(s.genre_id) ?? "var(--amber)",
                    } as CSSProperties
                  }
                >
                  <span className="bn">{s.genre_name}</span>
                  <span className="bt">continues</span>
                </div>
              );
            }
            return (
              <div
                key={`gap-${i}`}
                className="blk none"
                style={{
                  left: `${(seg.from / 1440) * 100}%`,
                  width: `${((seg.to - seg.from) / 1440) * 100}%`,
                }}
              >
                <span className="bn">Nothing scheduled</span>
              </div>
            );
          })}
          {nowMinutes != null && (
            <i
              className="nowl"
              style={{ left: `${(nowMinutes / 1440) * 100}%` }}
            >
              <b>Now</b>
            </i>
          )}
        </div>
        <div className="ticks" aria-hidden="true">
          {Array.from({ length: 9 }, (_, i) => i * 3).map((h) => (
            <span
              key={h}
              className={h === 0 ? "f" : h === 24 ? "l" : ""}
              style={{ left: `${(h / 24) * 100}%` }}
            >
              {tickLabel(h)}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
