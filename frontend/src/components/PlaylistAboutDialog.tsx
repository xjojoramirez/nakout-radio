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
  const closeRef = useRef<HTMLButtonElement | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setDetail(await api.getGenre(slug));
    } catch (err) {
      setError(messageFor(err));
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const description = detail?.description?.trim() ?? "";

  return createPortal(
    <div
      className="modal-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
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
                onClick={() => void load()}
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
            {detail && detail.top_artists.length > 0 && (
              <section className="pa-artists">
                <h3>Top artists in this playlist</h3>
                <ul>
                  {detail.top_artists.map((artist) => (
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
            onClick={onClose}
          >
            Close
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
