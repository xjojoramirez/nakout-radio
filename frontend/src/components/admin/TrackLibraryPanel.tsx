import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import type { TrackLibraryPage } from "../../types";
import { messageFor } from "../../utils/errors";
import { SkeletonList } from "./Skeleton";
import { TrackDetailEditor } from "./TrackDetailEditor";

const LIMIT = 50;
type StatusFilter = "" | "empty" | "auto" | "curated";
const STATUS_LABEL = {
  empty: "Empty",
  auto: "Auto",
  curated: "Curated",
} as const;

interface Props {
  onNotice: (message: string) => void;
  onError: (message: string) => void;
  onCountChange?: (count: number) => void;
}

export function TrackLibraryPanel({
  onNotice,
  onError,
  onCountChange,
}: Props) {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<StatusFilter>("");
  const [page, setPage] = useState(0);
  const [data, setData] = useState<TrackLibraryPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);

  const errorRef = useRef(onError);
  errorRef.current = onError;
  const countRef = useRef(onCountChange);
  countRef.current = onCountChange;

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(query.trim());
      setPage(0);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    api
      .listTracks({
        q: search || undefined,
        status: status || undefined,
        limit: LIMIT,
        offset: page * LIMIT,
      })
      .then((result) => {
        if (active) setData(result);
      })
      .catch((failure: unknown) => {
        if (!active) return;
        errorRef.current(messageFor(failure));
        setData({ items: [], total: 0, limit: LIMIT, offset: page * LIMIT });
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [search, status, page, reload]);

  useEffect(() => {
    if (data) countRef.current?.(data.total);
  }, [data]);

  const total = data?.total ?? 0;
  const start = total === 0 ? 0 : page * LIMIT + 1;
  const end = Math.min(total, (page + 1) * LIMIT);

  return (
    <section className="admin-panel track-library">
      <div className="panel-head">
        <div>
          <h2>Library</h2>
          <p className="hint">
            {total === 0
              ? "Track details for everything in the crates."
              : `${total} track${total === 1 ? "" : "s"}`}
          </p>
        </div>
      </div>

      <div className="lib-toolbar">
        <label className="field lib-search">
          Search library
          <input
            type="search"
            placeholder="Title or artist"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <label className="field lib-status">
          Filter by status
          <select
            value={status}
            onChange={(event) => {
              setStatus(event.target.value as StatusFilter);
              setPage(0);
            }}
          >
            <option value="">All tracks</option>
            <option value="empty">Empty</option>
            <option value="auto">Auto-filled</option>
            <option value="curated">Curated</option>
          </select>
        </label>
      </div>

      {loading && !data && <SkeletonList rows={6} />}

      {data && (
        <div aria-busy={loading} className="lib-body">
          {data.items.length > 0 ? (
            <ul className="lib-list">
              {data.items.map((item) => (
                <li key={item.youtube_video_id}>
                  <button
                    type="button"
                    className="lib-row"
                    onClick={() => setSelected(item.youtube_video_id)}
                  >
                    {item.thumbnail_url ? (
                      <img src={item.thumbnail_url} alt="" />
                    ) : (
                      <span className="lib-thumb" aria-hidden="true" />
                    )}
                    <span className="lib-main">
                      <strong>{item.title}</strong>
                      <small>{item.artist || "Unknown artist"}</small>
                    </span>
                    <span className="lib-album">
                      {item.album ?? "—"}
                      {item.release_year ? ` · ${item.release_year}` : ""}
                    </span>
                    <span className="lib-complete">
                      {item.completeness}/6
                    </span>
                    <span
                      className={`lib-chip lib-chip-${item.status}`}
                      aria-label={`Details status: ${STATUS_LABEL[item.status]}`}
                    >
                      {STATUS_LABEL[item.status]}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="lib-empty">No tracks match.</p>
          )}

          <div className="lib-pager">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={page === 0 || loading}
              onClick={() => setPage((current) => Math.max(0, current - 1))}
            >
              Previous
            </button>
            <span>
              {start}–{end} of {total}
            </span>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={end >= total || loading}
              onClick={() => setPage((current) => current + 1)}
            >
              Next
            </button>
          </div>
        </div>
      )}

      {selected && (
        <TrackDetailEditor
          videoId={selected}
          onClose={() => setSelected(null)}
          onSaved={(message) => {
            onNotice(message);
            setReload((current) => current + 1);
          }}
          onError={onError}
        />
      )}
    </section>
  );
}
