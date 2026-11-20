import { useCallback, useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { createPortal } from "react-dom";
import { api } from "../api/client";
import type { GenreDetail } from "../types";
import { messageFor } from "../utils/errors";

interface Props {
  slug: string;
  onClose: () => void;
}

export function PlaylistAboutDialog({ slug, onClose }: Props) {
  const [detail, setDetail] = useState<GenreDetail | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
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
      const latest = await api.getGenre(slug);
      if (id !== requestId.current) return;
      setDetail(latest);
    } catch (err) {
      if (id !== requestId.current) return;
      setError(messageFor(err));
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    setDetail(null);
    void load();
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

  const description = detail?.description?.trim() ?? "";
  const topArtists = detail?.top_artists ?? [];

  return createPortal(
    <div
      className="modal-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onCloseRef.current();
      }}
    >
      <div
        className="modal-card playlist-about"
        role="dialog"
        aria-modal="true"
        aria-labelledby="playlist-about-title"
      >
        <div
          className="pa-head"
          style={
            { "--gc": detail?.color || "var(--amber)" } as CSSProperties
          }
        >
          <i className="dot big" aria-hidden="true" />
          <h2 id="playlist-about-title" className="modal-title">
            {detail?.name ?? "Playlist"}
          </h2>
        </div>

        {loading ? (
          <p className="muted">Loading playlist…</p>
        ) : error ? (
          <>
            <p className="error banner" role="alert">
              {error}
            </p>
            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  closeRef.current?.focus();
                  void load();
                }}
              >
                Retry
              </button>
            </div>
          </>
        ) : (
          <>
            {description ? (
              <p className="pa-desc">{description}</p>
            ) : (
              <p className="pa-empty">No description yet.</p>
            )}
            {topArtists.length > 0 && (
              <section className="pa-artists">
                <h3>Top artists in this playlist</h3>
                <ul>
                  {topArtists.map((artist) => (
                    <li key={artist} className="chip">
                      {artist}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}

        <div className="modal-actions">
          <button
            type="button"
            ref={closeRef}
            className="btn btn-secondary"
            onClick={() => onCloseRef.current()}
          >
            Close
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
