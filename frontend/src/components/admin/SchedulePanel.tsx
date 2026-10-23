import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { api } from "../../api/client";
import { messageFor } from "../../utils/errors";
import { fmtMin, minutesOf, twelveHour } from "../../utils/format";
import { ConfirmDialog } from "../ConfirmDialog";
import { GenreChipRadio } from "./GenreChipRadio";
import { ScheduleTimeline, buildSegs, lastBefore, slotsForDay } from "./ScheduleTimeline";
import type { CurrentGenre, Genre, ScheduleSlot } from "../../types";

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DAY_FULL = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];
/** Reference day order: Monday first, then the week. */
const WEEK_ORDER = [0, 1, 2, 3, 4, 5, 6];
const TICK_HOURS = Array.from({ length: 9 }, (_, i) => i * 3);
const TIME_BLOCKS = [
  { label: "Overnight", from: 0, to: 360 },
  { label: "Morning", from: 360, to: 720 },
  { label: "Afternoon", from: 720, to: 1080 },
  { label: "Evening", from: 1080, to: 1440 },
];
const VIEWS = [
  { id: "week", label: "Week" },
  { id: "day", label: "Day" },
  { id: "list", label: "By genre" },
] as const;
type ScheduleView = (typeof VIEWS)[number]["id"];
type Seg = ReturnType<typeof buildSegs>[number];

function hourLabel(hour: number): string {
  return `${hour % 12 || 12} ${hour % 24 >= 12 ? "PM" : "AM"}`;
}

interface Props {
  genres: Genre[];
  onNotice: (message: string) => void;
  onError: (message: string) => void;
  onCountChange?: (count: number) => void;
  /** Genre id preset by a cross-tab jump from the Genres panel. */
  initialGenre?: number | null;
  /** Fired when the panel has consumed its `initialGenre` intent. */
  onIntentConsumed?: () => void;
}

/** Local weekday as an app day int (0 = Monday .. 6 = Sunday). */
function appToday(): number {
  return (new Date().getDay() + 6) % 7;
}

function localNowMinutes(): number {
  const now = new Date();
  return now.getHours() * 60 + now.getMinutes();
}

function toHM(minute: number): string {
  return `${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(
    minute % 60,
  ).padStart(2, "0")}`;
}

/** First free 30-minute start from 06:00 upward on the selected day. */
function freeStart(day: number, all: ScheduleSlot[]): number {
  const used = slotsForDay(all, day).map((s) => minutesOf(s.start_time));
  for (let m = 360; m < 1440; m += 30) {
    if (!used.includes(m)) return m;
  }
  return 360;
}

function formatDays(days: number[]): string {
  if (days.length === 0) return "No days";
  const sorted = [...days].sort((a, b) => a - b);
  if (sorted.length === 7) return "Every day";
  if (sorted.join(",") === "0,1,2,3,4") return "Weekdays";
  if (sorted.join(",") === "5,6") return "Weekends";
  return sorted.map((d) => DAY_LABELS[d]).join(", ");
}

function dayPhrase(days: number[]): string {
  if (days.length === 0) return "pick at least one day";
  const label = formatDays(days);
  if (label === "Weekdays") return "on weekdays";
  if (label === "Weekends") return "on weekends";
  if (label === "Every day") return "every day";
  return `on ${label}`;
}

function nextWhen(off: number, day: number): string {
  if (off === 0) return "today";
  if (off === 1) return "tomorrow";
  return DAY_FULL[day];
}

export function SchedulePanel({
  genres,
  onNotice,
  onError,
  onCountChange,
  initialGenre,
  onIntentConsumed,
}: Props) {
  const [slots, setSlots] = useState<ScheduleSlot[]>([]);
  const [slotsError, setSlotsError] = useState("");
  const [onAir, setOnAir] = useState<CurrentGenre | null>(null);

  const [selDay, setSelDay] = useState(appToday);
  const [view, setView] = useState<ScheduleView>("week");
  const [filterGenres, setFilterGenres] = useState<number[]>([]);
  const [closedGenres, setClosedGenres] = useState<Record<number, boolean>>({});
  const [formOpen, setFormOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [formGenre, setFormGenre] = useState<number | null>(null);
  const [formDays, setFormDays] = useState<number[]>([]);
  const [formTime, setFormTime] = useState("06:00");
  const [formError, setFormError] = useState("");
  const [pendingDelete, setPendingDelete] = useState<ScheduleSlot | null>(null);
  const [intentGenre, setIntentGenre] = useState<number | null>(null);

  const consumedIntent = useRef(false);

  useEffect(() => {
    if (initialGenre != null && !consumedIntent.current) {
      consumedIntent.current = true;
      setIntentGenre(initialGenre);
      onIntentConsumed?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadSlots = useCallback(async () => {
    try {
      const loaded = await api.listSlots();
      setSlots(loaded);
      onCountChange?.(loaded.length);
      setSlotsError("");
    } catch (err) {
      setSlotsError(messageFor(err));
    }
  }, [onCountChange]);

  useEffect(() => {
    void loadSlots();
  }, [loadSlots]);

  const fetchNow = useCallback(async () => {
    try {
      setOnAir(await api.scheduleNow());
    } catch {
      // keep the last known on-air state
    }
  }, []);

  useEffect(() => {
    void fetchNow();
    const timer = window.setInterval(() => void fetchNow(), 60_000);
    return () => window.clearInterval(timer);
  }, [fetchNow, slots]);

  const colours = useMemo(
    () => new Map(genres.map((g) => [g.id, g.color || "var(--amber)"])),
    [genres],
  );

  const tzLabel = useMemo(() => {
    try {
      return (
        Intl.DateTimeFormat().resolvedOptions().timeZone.replace(/_/g, " ") ||
        ""
      );
    } catch {
      return "";
    }
  }, []);

  const todayIdx = appToday();
  const nowMinutes = localNowMinutes();

  const passes = (genreId: number) =>
    filterGenres.length === 0 || filterGenres.includes(genreId);

  const toggleFilter = (genreId: number) => {
    setFilterGenres((prev) =>
      prev.includes(genreId)
        ? prev.filter((id) => id !== genreId)
        : [...prev, genreId],
    );
  };

  const pickDay = (day: number) => {
    setSelDay(day);
    setView("day");
    if (formOpen && editId === null) setFormDays([day]);
  };

  const closeForm = () => {
    setFormOpen(false);
    setEditId(null);
    setFormError("");
  };

  const openAdd = (
    minute: number | null,
    day = selDay,
    genreId: number | null = intentGenre,
  ) => {
    setFormOpen(true);
    setEditId(null);
    setFormGenre(genreId);
    setFormDays([day]);
    setFormTime(toHM(minute ?? freeStart(day, slots)));
    setFormError("");
  };

  const openEdit = (id: number) => {
    const slot = slots.find((s) => s.id === id);
    if (!slot) return;
    setFormOpen(true);
    setEditId(slot.id);
    setFormGenre(slot.genre_id);
    setFormDays([...slot.days_of_week]);
    setFormTime(slot.start_time);
    setFormError("");
  };

  const toggleFormDay = (day: number) => {
    setFormDays((prev) =>
      prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day],
    );
    setFormError("");
  };

  const submit = async () => {
    if (formGenre === null || formDays.length === 0 || !formTime) return;
    const payload = {
      genre_id: formGenre,
      days_of_week: [...formDays].sort((a, b) => a - b),
      start_time: formTime,
    };
    try {
      if (editId === null) {
        await api.createSlot(payload);
        onNotice("Schedule slot added.");
      } else {
        await api.updateSlot(editId, payload);
        onNotice("Schedule slot updated.");
      }
      setFormOpen(false);
      setEditId(null);
      setFormError("");
      await loadSlots();
    } catch (err) {
      setFormError(messageFor(err));
    }
  };

  const removeSlot = async (id: number) => {
    try {
      await api.deleteSlot(id);
      onNotice("Schedule slot deleted.");
      await loadSlots();
    } catch (err) {
      onError(messageFor(err));
    }
  };

  const segs = buildSegs(slots, selDay);
  const hasSlot = segs.some((s) => s.kind === "slot");
  const visibleSegs = segs.filter(
    (s) => s.kind === "gap" || !s.slot || passes(s.slot.genre_id),
  );
  const daySlots = slotsForDay(slots, selDay);
  const visibleDaySlots = daySlots.filter((s) => passes(s.genre_id));

  const airtime = useMemo(() => {
    const byGenre = new Map<number, number>();
    for (const day of WEEK_ORDER) {
      for (const seg of buildSegs(slots, day)) {
        if (!seg.slot) continue;
        byGenre.set(
          seg.slot.genre_id,
          (byGenre.get(seg.slot.genre_id) ?? 0) + (seg.to - seg.from),
        );
      }
    }
    return byGenre;
  }, [slots]);
  const airtimeTotal = Array.from(airtime.values()).reduce(
    (sum, value) => sum + value,
    0,
  );

  const liveGenre = onAir?.genre ?? null;
  const liveColour = liveGenre?.color || "var(--amber)";
  const activeInfo = (() => {
    const today = slotsForDay(slots, todayIdx).filter(
      (s) => minutesOf(s.start_time) <= nowMinutes,
    );
    if (today.length) return { slot: today[today.length - 1], day: todayIdx };
    return lastBefore(slots, todayIdx);
  })();
  const sinceText = (() => {
    if (!activeInfo) return "";
    const at = twelveHour(minutesOf(activeInfo.slot.start_time));
    return activeInfo.day === todayIdx ? `since ${at}` : `since ${at} ${DAY_FULL[activeInfo.day]}`;
  })();
  const nextText = (() => {
    for (let off = 0; off <= 6; off++) {
      const d = (todayIdx + off) % 7;
      const list = slotsForDay(slots, d).filter(
        (s) => off > 0 || minutesOf(s.start_time) > nowMinutes,
      );
      if (list.length) {
        return `Next: ${list[0].genre_name} at ${twelveHour(
          minutesOf(list[0].start_time),
        )} ${nextWhen(off, d)}`;
      }
    }
    return "No upcoming slots.";
  })();

  const formGenreName =
    formGenre != null
      ? (genres.find((g) => g.id === formGenre)?.name ?? "")
      : "";

  const dimmedGenres = new Set(
    genres.filter((g) => !passes(g.id)).map((g) => g.id),
  );

  const renderAgendaRow = (seg: Seg, i: number) => {
    if (seg.kind === "slot") {
      const s = seg.slot as ScheduleSlot;
      return (
        <div
          key={s.id}
          className="srow"
          style={
            {
              "--gc": colours.get(s.genre_id) ?? "var(--amber)",
            } as CSSProperties
          }
        >
          <div className="sm">
            <span className="tr">
              {twelveHour(seg.from)} to {twelveHour(seg.to)}
            </span>
            <b>{s.genre_name}</b>
            <span className="chip">{fmtMin(seg.to - seg.from)}</span>
            <span className="mono">{formatDays(s.days_of_week)}</span>
          </div>
          <div className="sa">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => openEdit(s.id)}
            >
              Edit
            </button>
            <button
              type="button"
              className="btn btn-danger btn-sm"
              onClick={() => setPendingDelete(s)}
            >
              Delete
            </button>
          </div>
        </div>
      );
    }
    if (seg.kind === "carry") {
      const s = seg.slot as ScheduleSlot;
      return (
        <div key={`carry-${i}`} className="srow dim">
          <div className="sm">
            <span className="tr">
              {twelveHour(seg.from)} to {twelveHour(seg.to)}
            </span>
            <span>
              <i
                className="dot"
                style={
                  {
                    "--gc": colours.get(s.genre_id) ?? "var(--amber)",
                  } as CSSProperties
                }
                aria-hidden="true"
              />{" "}
              {s.genre_name} continues from {DAY_FULL[seg.fromDay]}
            </span>
          </div>
        </div>
      );
    }
    return (
      <div key={`gap-${i}`} className="srow dim">
        <div className="sm">
          <span className="tr">
            {twelveHour(seg.from)} to {twelveHour(seg.to)}
          </span>
          <span>Nothing scheduled</span>
        </div>
        <div className="sa">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => openAdd(seg.from)}
          >
            Add slot
          </button>
        </div>
      </div>
    );
  };

  const renderDayBody = () => (
    <>
      <div className="dayrow">
        <div className="dayseg" role="group" aria-label="Day of the week">
          {WEEK_ORDER.map((d) => (
            <button
              key={d}
              type="button"
              className="pill"
              aria-label={DAY_LABELS[d]}
              aria-pressed={d === selDay}
              onClick={() => pickDay(d)}
            >
              {DAY_LABELS[d]}
              <span className="count">{slotsForDay(slots, d).length}</span>
              {d === todayIdx && (
                <i className="tdot" title="Today" aria-hidden="true" />
              )}
            </button>
          ))}
        </div>
        <span className="hint">Pick a day to open its agenda.</span>
      </div>

      <div className="card">
        <ScheduleTimeline
          day={selDay}
          slots={slots}
          colours={colours}
          nowMinutes={selDay === todayIdx ? nowMinutes : null}
          onOpenSlot={openEdit}
          onOpenNew={(minute) => openAdd(minute)}
          dimmedGenres={dimmedGenres}
        />
        <p className="hint">
          Click an empty spot on the timeline to add a slot at that time.
        </p>
      </div>

      {!hasSlot && (
        <div className="empty">
          No slots start on {DAY_FULL[selDay]} yet.{" "}
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => openAdd(360)}
          >
            Add the first slot
          </button>
        </div>
      )}
      {hasSlot && visibleDaySlots.length === 0 && (
        <div className="empty">
          None of the selected genres start on {DAY_FULL[selDay]}.{" "}
          <button
            type="button"
            className="btn-link"
            onClick={() => setFilterGenres([])}
          >
            Show all genres
          </button>
        </div>
      )}

      <div className="daylist">
        {TIME_BLOCKS.map((block) => {
          const items = visibleSegs.filter(
            (s) => s.from >= block.from && s.from < block.to,
          );
          if (!items.length) return null;
          const count = items.filter((s) => s.kind === "slot").length;
          return (
            <div className="dp" key={block.label}>
              <div className="dph">
                <span>
                  {block.label} · {twelveHour(block.from)} to{" "}
                  {twelveHour(block.to)}
                </span>
                <span>
                  {count
                    ? `${count} ${count === 1 ? "slot" : "slots"}`
                    : "carried over"}
                </span>
              </div>
              {items.map(renderAgendaRow)}
            </div>
          );
        })}
      </div>
    </>
  );

  const renderWeekBody = () => (
    <div className="card">
      <div className="tlscroll">
        <div className="wk">
          <div className="wkrow">
            <span />
            <div className="ticks" aria-hidden="true">
              {TICK_HOURS.map((h) => (
                <span
                  key={h}
                  className={h === 0 ? "f" : h === 24 ? "l" : ""}
                  style={{ left: `${(h / 24) * 100}%` }}
                >
                  {hourLabel(h)}
                </span>
              ))}
            </div>
          </div>
          {WEEK_ORDER.map((day) => {
            const daySegs = buildSegs(slots, day);
            const dayCount = slotsForDay(slots, day).length;
            return (
              <div
                key={day}
                className={day === todayIdx ? "wkrow today" : "wkrow"}
              >
                <button
                  type="button"
                  className="wkday"
                  aria-label={`Open ${DAY_FULL[day]}`}
                  onClick={() => {
                    setSelDay(day);
                    setView("day");
                  }}
                >
                  {DAY_LABELS[day]}
                  <small>{dayCount}</small>
                </button>
                <div
                  className="wkbar"
                  role="group"
                  aria-label={`${DAY_FULL[day]} timeline`}
                  onClick={(e) => {
                    const rect = e.currentTarget.getBoundingClientRect();
                    if (!rect.width) return;
                    const raw = ((e.clientX - rect.left) / rect.width) * 1440;
                    const minute = Math.round(raw / 30) * 30;
                    setSelDay(day);
                    openAdd(
                      Math.min(1410, Math.max(0, minute)),
                      day,
                    );
                  }}
                >
                  {daySegs.map((seg, i) => {
                    const style: CSSProperties & { "--gc"?: string } = {
                      left: `${(seg.from / 1440) * 100}%`,
                      width: `${((seg.to - seg.from) / 1440) * 100}%`,
                    };
                    if (seg.kind === "gap") {
                      return (
                        <div
                          key={`gap-${day}-${i}`}
                          className="blk none"
                          style={style}
                        >
                          <span className="bn">Nothing scheduled</span>
                        </div>
                      );
                    }
                    const s = seg.slot as ScheduleSlot;
                    style["--gc"] = colours.get(s.genre_id) ?? "var(--amber)";
                    if (seg.kind === "slot") {
                      return (
                        <button
                          key={s.id}
                          type="button"
                          className={
                            passes(s.genre_id) ? "blk" : "blk dim"
                          }
                          style={style}
                          title={`${s.genre_name} · ${twelveHour(seg.from)} to ${twelveHour(seg.to)}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            openEdit(s.id);
                          }}
                        >
                          <span className="bn">{s.genre_name}</span>
                        </button>
                      );
                    }
                    return (
                      <div
                        key={`carry-${day}-${i}`}
                        className={
                          passes(s.genre_id) ? "blk carry" : "blk carry dim"
                        }
                        style={style}
                        title={`${s.genre_name} continues from ${DAY_FULL[seg.fromDay]}`}
                      >
                        <span className="bn">{s.genre_name}</span>
                      </div>
                    );
                  })}
                  {day === todayIdx && (
                    <i
                      className="nowl"
                      style={{ left: `${(nowMinutes / 1440) * 100}%` }}
                    />
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      <p className="hint">
        Click a block to edit it, empty space to add a slot, or a day name to
        open that day. The number beside a day is how many slots start on it.
      </p>
    </div>
  );

  const renderListBody = () => {
    const shareGenres = genres.filter((g) => (airtime.get(g.id) ?? 0) > 0);
    const groups = genres.filter((g) => passes(g.id));
    return (
      <>
        <div className="card">
          <div className="head">
            <span className="lab">Airtime per week</span>
            <div className="head-actions">
              <button
                type="button"
                className="btn-link"
                onClick={() => {
                  const next: Record<number, boolean> = {};
                  for (const g of genres) next[g.id] = false;
                  setClosedGenres(next);
                }}
              >
                Expand all
              </button>
              <button
                type="button"
                className="btn-link"
                onClick={() => {
                  const next: Record<number, boolean> = {};
                  for (const g of genres) next[g.id] = true;
                  setClosedGenres(next);
                }}
              >
                Collapse all
              </button>
            </div>
          </div>
          <div className="share" aria-hidden="true">
            {shareGenres.map((g) => (
              <i
                key={g.id}
                style={
                  {
                    "--gc": g.color || "var(--amber)",
                    width: `${((airtime.get(g.id) ?? 0) / (airtimeTotal || 1)) * 100}%`,
                  } as CSSProperties
                }
                title={`${g.name} · ${fmtMin(airtime.get(g.id) ?? 0)} a week`}
              />
            ))}
          </div>
        </div>

        <div className="groups">
          {groups.map((g) => {
            const genreSlots = slots
              .filter((s) => s.genre_id === g.id)
              .sort(
                (a, b) =>
                  minutesOf(a.start_time) - minutesOf(b.start_time),
              );
            const closed = Boolean(closedGenres[g.id]);
            const weekly = airtime.get(g.id) ?? 0;
            return (
              <section
                key={g.id}
                className="group"
                style={
                  {
                    "--gc": g.color || "var(--amber)",
                  } as CSSProperties
                }
              >
                <div className="ghead">
                  <i className="dot big" aria-hidden="true" />
                  <b>{g.name}</b>
                  <span className="mono">
                    {genreSlots.length}{" "}
                    {genreSlots.length === 1 ? "slot" : "slots"} ·{" "}
                    {weekly ? `${fmtMin(weekly)} a week` : "no airtime"}
                  </span>
                  <span className="sp" />
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => openAdd(null, todayIdx, g.id)}
                  >
                    Add slot
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    aria-expanded={!closed}
                    onClick={() =>
                      setClosedGenres((prev) => ({
                        ...prev,
                        [g.id]: !prev[g.id],
                      }))
                    }
                  >
                    {closed ? "Show" : "Hide"}
                  </button>
                </div>
                {!closed &&
                  (genreSlots.length ? (
                    genreSlots.map((s) => (
                      <div className="prow" key={s.id}>
                        <div className="pm">
                          <span className="tr">
                            {twelveHour(minutesOf(s.start_time))}
                          </span>
                          <b>{formatDays(s.days_of_week)}</b>
                        </div>
                        <div className="act">
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() => openEdit(s.id)}
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            className="btn btn-danger btn-sm"
                            onClick={() => setPendingDelete(s)}
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="gempty">Not scheduled yet.</div>
                  ))}
              </section>
            );
          })}
        </div>
      </>
    );
  };

  const toolbar = (
    <div className="toolbar">
      <div className="seg" role="group" aria-label="Schedule view">
        {VIEWS.map((v) => (
          <button
            key={v.id}
            type="button"
            aria-pressed={view === v.id}
            onClick={() => setView(v.id)}
          >
            {v.label}
          </button>
        ))}
      </div>
      <div className="fchips" role="group" aria-label="Filter by genre">
        {genres.map((g) => {
          const count = slots.filter((s) => s.genre_id === g.id).length;
          return (
            <button
              key={g.id}
              type="button"
              role="checkbox"
              aria-checked={filterGenres.includes(g.id)}
              className="gchip sm"
              style={{ "--gc": g.color || "var(--amber)" } as CSSProperties}
              onClick={() => toggleFilter(g.id)}
            >
              <i className="dot" aria-hidden="true" />
              {g.name}
              <span className="count">{count}</span>
            </button>
          );
        })}
        {filterGenres.length > 0 && (
          <button
            type="button"
            className="btn-link"
            onClick={() => setFilterGenres([])}
          >
            Show all
          </button>
        )}
      </div>
    </div>
  );

  const body =
    slots.length === 0 && view !== "day" ? (
      <div className="empty">
        No slots yet. Add one to start the automatic schedule.
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => openAdd(360)}
        >
          Add the first slot
        </button>
      </div>
    ) : view === "week" ? (
      renderWeekBody()
    ) : view === "list" ? (
      renderListBody()
    ) : (
      renderDayBody()
    );

  return (
    <section className="admin-panel" aria-label="Schedule">
      <div className="head">
        <div>
          <h2 className="sec">Schedule</h2>
          <p className="sub">
            Each slot starts a genre, and it plays until the next slot begins.{" "}
            {tzLabel && (
              <span className="mono">Times are shown in {tzLabel}.</span>
            )}
          </p>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => {
            if (formOpen && editId === null) closeForm();
            else openAdd(null);
          }}
        >
          {formOpen && editId === null ? "Close" : "+ Add slot"}
        </button>
      </div>

      <div className="card onair">
        {liveGenre ? (
          <>
            <span className="led live" aria-hidden="true" />
            <div>
              <div className="big">
                <i
                  className="dot"
                  style={{ "--gc": liveColour } as CSSProperties}
                  aria-hidden="true"
                />
                On air: <b>{liveGenre.name}</b>
                {sinceText && <span className="mono">{sinceText}</span>}
              </div>
              <div className="next">{nextText}</div>
            </div>
          </>
        ) : (
          <>
            <span className="led" aria-hidden="true" />
            <div>
              <div className="big">Nothing scheduled yet</div>
              <div className="next">
                Add a slot to start the automatic schedule.
              </div>
            </div>
          </>
        )}
      </div>

      {slotsError && (
        <p className="error banner" role="alert">
          {slotsError}
        </p>
      )}

      {formOpen && (
        <form
          className="card sform"
          data-testid="slot-form"
          autoComplete="off"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <h3 className="ttl">{editId === null ? "Add a slot" : "Edit slot"}</h3>
          <div className="lab">Genre</div>
          <GenreChipRadio
            label="Genre"
            genres={genres}
            value={formGenre}
            onChange={(id) => {
              setFormGenre(id);
              setFormError("");
            }}
          />
          <div className="lab">Repeat on</div>
          <div className="dayrow" role="group" aria-label="Repeat on">
            <div className="presets">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => {
                  setFormDays([0, 1, 2, 3, 4]);
                  setFormError("");
                }}
              >
                Weekdays
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => {
                  setFormDays([5, 6]);
                  setFormError("");
                }}
              >
                Weekends
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => {
                  setFormDays([0, 1, 2, 3, 4, 5, 6]);
                  setFormError("");
                }}
              >
                Every day
              </button>
            </div>
            <div className="dayrow">
              {WEEK_ORDER.map((d) => (
                <button
                  key={d}
                  type="button"
                  className="pill"
                  aria-pressed={formDays.includes(d)}
                  onClick={() => toggleFormDay(d)}
                >
                  {DAY_LABELS[d]}
                </button>
              ))}
            </div>
          </div>
          <div className="two">
            <label className="lab">
              Start time
              <input
                type="time"
                value={formTime}
                onChange={(e) => {
                  setFormTime(e.target.value);
                  setFormError("");
                }}
              />
            </label>
          </div>
          <div className="sentence" data-testid="sentence" aria-live="polite">
            {formGenre != null && formTime && formDays.length > 0 ? (
              <>
                <b>{formGenreName}</b> will start at{" "}
                <b>{twelveHour(minutesOf(formTime))}</b> {dayPhrase(formDays)}{" "}
                and play until the next slot begins.
              </>
            ) : (
              "Pick a genre and a start time."
            )}
          </div>
          {formError && <div className="hint err">{formError}</div>}
          <div className="fa">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={closeForm}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={!formGenre || formDays.length === 0 || !formTime}
            >
              {editId === null ? "Add slot" : "Save slot"}
            </button>
          </div>
        </form>
      )}

      {toolbar}

      {body}

      {pendingDelete && (
        <ConfirmDialog
          title="Delete schedule slot"
          message={`Delete the ${pendingDelete.genre_name} slot (${formatDays(
            pendingDelete.days_of_week,
          )}, from ${pendingDelete.start_time})?`}
          confirmLabel="Delete"
          danger
          onConfirm={() => {
            const id = pendingDelete.id;
            setPendingDelete(null);
            void removeSlot(id);
          }}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </section>
  );
}
