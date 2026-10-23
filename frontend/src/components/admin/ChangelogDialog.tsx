import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../../api/client";
import type { ChangelogEntry } from "../../types";
import { messageFor } from "../../utils/errors";

interface Props {
  onClose: () => void;
}

const DATE_FORMATTER = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC",
});

function formatDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return value;
  return DATE_FORMATTER.format(new Date(Date.UTC(year, month - 1, day)));
}

export function ChangelogDialog({ onClose }: Props) {
  const [entries, setEntries] = useState<ChangelogEntry[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const requestId = useRef(0);
  const closeRef = useRef<HTMLButtonElement | null>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    setError("");
    try {
      const latest = await api.changelog();
      if (id !== requestId.current) return;
      setEntries(latest);
    } catch (err) {
      if (id !== requestId.current) return;
      setError(messageFor(err));
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    return () => {
      requestId.current += 1;
    };
  }, [load]);

  useEffect(() => {
    returnFocusRef.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    closeRef.current?.focus();

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCloseRef.current();
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);

    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
      returnFocusRef.current?.focus();
    };
  }, []);

  return createPortal(
    <div
      className="modal-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCloseRef.current();
      }}
    >
      <div
        id="changelog-dialog"
        className="modal-card changelog-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="changelog-title"
      >
        <div className="changelog-head">
          <div>
            <h2 id="changelog-title" className="modal-title">
              Changelog
            </h2>
            <p className="changelog-sub">The latest changes to Nakout Radio.</p>
          </div>
          <button
            type="button"
            ref={closeRef}
            className="changelog-close"
            aria-label="Close changelog"
            onClick={() => onCloseRef.current()}
          >
            &times;
          </button>
        </div>

        <div className="changelog-body">
          {loading ? (
            <p className="changelog-status">Loading latest changes&hellip;</p>
          ) : error ? (
            <div className="changelog-status" role="alert">
              <p>{error}</p>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={load}
              >
                Retry
              </button>
            </div>
          ) : entries && entries.length > 0 ? (
            <ol className="changelog-list">
              {entries.map((entry, index) => (
                <li
                  key={`${entry.date}-${entry.title}-${index}`}
                  className="changelog-entry"
                >
                  <time className="changelog-date" dateTime={entry.date}>
                    {formatDate(entry.date)}
                  </time>
                  <h3>{entry.title}</h3>
                  {entry.summary && <p>{entry.summary}</p>}
                </li>
              ))}
            </ol>
          ) : (
            <p className="changelog-status">No changes yet.</p>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
