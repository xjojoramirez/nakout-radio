import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { messageFor } from "../../utils/errors";
import { ConfirmDialog } from "../ConfirmDialog";
import type { Genre, ScheduleSlot } from "../../types";
import { GenreSelect } from "./GenreSelect";

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

interface Props {
  genres: Genre[];
  onNotice: (message: string) => void;
  onError: (message: string) => void;
  onCountChange?: (count: number) => void;
}

interface Draft {
  genre_id: string;
  days_of_week: number[];
  start_time: string;
}

function formatDays(days: number[]): string {
  if (days.length === 0) return "No days";
  const sorted = [...days].sort((a, b) => a - b);
  if (sorted.length === 7) return "Every day";
  if (sorted.join(",") === "0,1,2,3,4") return "Weekdays";
  if (sorted.join(",") === "5,6") return "Weekends";
  return sorted.map((d) => DAY_LABELS[d]).join(", ");
}

export function SchedulePanel({ genres, onNotice, onError, onCountChange }: Props) {
  const [slots, setSlots] = useState<ScheduleSlot[]>([]);
  const [slotsError, setSlotsError] = useState("");

  const [genre, setGenre] = useState("");
  const [days, setDays] = useState<number[]>([0, 1, 2, 3, 4]);
  const [start, setStart] = useState("06:00");

  const [editId, setEditId] = useState<number | null>(null);
  const [draft, setDraft] = useState<Draft>({
    genre_id: "",
    days_of_week: [],
    start_time: "",
  });
  const [pendingDelete, setPendingDelete] = useState<ScheduleSlot | null>(null);

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
    loadSlots();
  }, [loadSlots]);

  const toggleDay = (day: number) => {
    setDays((prev) =>
      prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day],
    );
  };

  const toggleDraftDay = (day: number) => {
    setDraft((prev) => ({
      ...prev,
      days_of_week: prev.days_of_week.includes(day)
        ? prev.days_of_week.filter((d) => d !== day)
        : [...prev.days_of_week, day],
    }));
  };

  const addSlot = async () => {
    try {
      await api.createSlot({
        genre_id: Number(genre),
        days_of_week: days,
        start_time: start,
      });
      onNotice("Schedule slot added.");
      await loadSlots();
    } catch (err) {
      onError(messageFor(err));
    }
  };

  const startEdit = (slot: ScheduleSlot) => {
    setEditId(slot.id);
    setDraft({
      genre_id: String(slot.genre_id),
      days_of_week: [...slot.days_of_week],
      start_time: slot.start_time,
    });
  };

  const saveEdit = async () => {
    if (editId === null) return;
    try {
      await api.updateSlot(editId, {
        genre_id: Number(draft.genre_id),
        days_of_week: [...draft.days_of_week].sort((a, b) => a - b),
        start_time: draft.start_time,
      });
      setEditId(null);
      onNotice("Schedule slot updated.");
      await loadSlots();
    } catch (err) {
      onError(messageFor(err));
    }
  };

  const removeSlot = async (slot: ScheduleSlot) => {
    try {
      await api.deleteSlot(slot.id);
      onNotice("Schedule slot deleted.");
      await loadSlots();
    } catch (err) {
      onError(messageFor(err));
    }
  };

  return (
    <section className="admin-panel" aria-label="Schedule">
      <h2>Add schedule slot</h2>
      <GenreSelect
        label="Slot genre"
        genres={genres}
        value={genre}
        onChange={setGenre}
      />
      <div className="days">
        {DAY_LABELS.map((label, i) => (
          <button
            type="button"
            key={label}
            className={days.includes(i) ? "active" : ""}
            aria-pressed={days.includes(i)}
            onClick={() => toggleDay(i)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="time-pair">
        <label className="field">
          Start
          <input
            type="time"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </label>
      </div>
      <div className="slot-form-actions">
        <button
          type="button"
          className="btn btn-primary"
          onClick={addSlot}
          disabled={!genre || days.length === 0}
        >
          Add slot
        </button>
      </div>

      <h2>Schedule slots</h2>

      {slotsError && (
        <p className="error banner" role="alert">
          {slotsError}
        </p>
      )}
      {slots.length === 0 && !slotsError && (
        <p className="muted">No schedule slots yet.</p>
      )}
      <ul className="genre-admin-list">
        {slots.map((slot) =>
          editId === slot.id ? (
            <li key={slot.id} className="slot-editing">
              <div className="slot-edit-head">
                <span className="st-name">{slot.genre_name}</span>
                <span className="edit-badge">Editing</span>
              </div>
              <GenreSelect
                label="Edit slot genre"
                genres={genres}
                value={draft.genre_id}
                onChange={(value) =>
                  setDraft((prev) => ({ ...prev, genre_id: value }))
                }
              />
              <div className="days">
                {DAY_LABELS.map((label, i) => (
                  <button
                    type="button"
                    key={label}
                    className={draft.days_of_week.includes(i) ? "active" : ""}
                    aria-label={`Edit slot ${label}`}
                    aria-pressed={draft.days_of_week.includes(i)}
                    onClick={() => toggleDraftDay(i)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="time-pair">
                <label className="field">
                  Start
                  <input
                    type="time"
                    aria-label="Edit slot start"
                    value={draft.start_time}
                    onChange={(e) =>
                      setDraft((prev) => ({
                        ...prev,
                        start_time: e.target.value,
                      }))
                    }
                  />
                </label>
              </div>
              <div className="slot-form-actions">
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  onClick={saveEdit}
                  disabled={!draft.genre_id || draft.days_of_week.length === 0}
                >
                  Save
                </button>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setEditId(null)}
                >
                  Cancel
                </button>
              </div>
            </li>
          ) : (
            <li key={slot.id}>
              <span className="st-name">{slot.genre_name}</span>
              <span className="st-slug">{formatDays(slot.days_of_week)}</span>
              <span className="count-pill">from {slot.start_time}</span>
              <div className="row-actions">
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => startEdit(slot)}
                >
                  Edit
                </button>
                <button
                  type="button"
                  className="btn btn-danger btn-sm"
                  onClick={() => setPendingDelete(slot)}
                >
                  Delete
                </button>
              </div>
            </li>
          ),
        )}
      </ul>

      {pendingDelete && (
        <ConfirmDialog
          title="Delete schedule slot"
          message={`Delete the ${pendingDelete.genre_name} slot (${formatDays(
            pendingDelete.days_of_week,
          )}, from ${pendingDelete.start_time})?`}
          confirmLabel="Delete"
          danger
          onConfirm={() => {
            const slot = pendingDelete;
            setPendingDelete(null);
            void removeSlot(slot);
          }}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </section>
  );
}
