import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import type { EnrichmentStatus, TrackLibraryPage } from "../../types";
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
  const [unassigned, setUnassigned] = useState(false);
  const [page, setPage] = useState(0);
  const [data, setData] = useState<TrackLibraryPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [enrichStatus, setEnrichStatus] = useState<EnrichmentStatus | null>(
    null,
  );
  const [polling, setPolling] = useState(false);
  const [startingEnrichment, setStartingEnrichment] = useState(false);

  const errorRef = useRef(onError);
  errorRef.current = onError;
  const countRef = useRef(onCountChange);
  countRef.current = onCountChange;
  const noticeRef = useRef(onNotice);
  noticeRef.current = onNotice;

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
        unassigned: unassigned || undefined,
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
  }, [search, status, unassigned, page, reload]);

  useEffect(() => {
    if (data) countRef.current?.(data.total);
  }, [data]);

  useEffect(() => {
    let active = true;
    api.enrichmentStatus().then(
      (status) => {
        if (!active) return;
        setEnrichStatus(status);
        if (status.running) setPolling(true);
      },
      () => {},
    );
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!polling) return;
    let active = true;
    let timer = 0;

    const tick = async () => {
      try {
        const status = await api.enrichmentStatus();
        if (!active) return;
        setEnrichStatus(status);
        if (status.running) {
          timer = window.setTimeout(tick, 2000);
        } else {
          setPolling(false);
          setReload((current) => current + 1);
          noticeRef.current(
            `Enriched ${status.enriched} of ${status.total} tracks · ` +
              `${status.stories} ${
                status.stories === 1 ? "story" : "stories"
              } checked`,
          );
        }
      } catch {
        if (active) setPolling(false);
      }
    };

    tick();
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [polling]);

  const startEnrichment = async () => {
    setStartingEnrichment(true);
    try {
      const result = await api.enrichMissing();
      if (result.started) {
        setPolling(true);
        return;
      }
      const status = await api.enrichmentStatus();
      setEnrichStatus(status);
      if (status.running) {
        setPolling(true);
      } else {
        noticeRef.current("Nothing to enrich right now.");
      }
    } catch (failure) {
      errorRef.current(messageFor(failure));
    } finally {
      setStartingEnrichment(false);
    }
  };

  const total = data?.total ?? 0;
  const start = total === 0 ? 0 : page * LIMIT + 1;
  const end = Math.min(total, (page + 1) * LIMIT);
  const busy =
    polling || startingEnrichment || Boolean(enrichStatus?.running);
  const storyRemaining = enrichStatus
    ? Math.max(
        0,
        enrichStatus.total -
          enrichStatus.stories -
          enrichStatus.stories_failed,
      )
    : 0;
  const pending = (enrichStatus?.remaining ?? 0) + storyRemaining;
  const failedCount =
    (enrichStatus?.failed ?? 0) + (enrichStatus?.stories_failed ?? 0);
  const checked = enrichStatus
    ? enrichStatus.enriched + enrichStatus.stories
    : 0;
  const progressPct =
    enrichStatus && enrichStatus.total > 0
      ? Math.round((checked / (enrichStatus.total * 2)) * 100)
      : 0;

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
        {enrichStatus && enrichStatus.total > 0 && (
          <div className="lib-enrich">
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={busy || (pending === 0 && failedCount === 0)}
              onClick={startEnrichment}
            >
              {busy
                ? "Enriching…"
                : pending > 0
                  ? `Enrich missing (${pending})`
                  : failedCount > 0
                    ? `Retry failed (${failedCount})`
                    : "All tracks checked"}
            </button>
          </div>
        )}
      </div>

      {busy && enrichStatus && (
        <div className="lib-progress">
          <div
            className="lib-progress-track"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progressPct}
            aria-label="Track enrichment progress"
          >
            <span style={{ width: `${progressPct}%` }} />
          </div>
          <small>
            {enrichStatus.enriched}/{enrichStatus.total} details ·{" "}
            {enrichStatus.stories}/{enrichStatus.total} stories
            {failedCount > 0 ? ` · ${failedCount} failed` : ""}
          </small>
        </div>
      )}

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
        <label className="lib-unassigned">
          <input
            type="checkbox"
            checked={unassigned}
            onChange={(event) => {
              setUnassigned(event.target.checked);
              setPage(0);
            }}
          />
          No playlist
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
                      <small>
                        {item.artist || "Unknown artist"}
                        {item.has_story && (
                          <span className="lib-story">story</span>
                        )}
                        {item.needs_review && (
                          <span className="lib-review">review</span>
                        )}
                        {!item.has_playlist && (
                          <span className="lib-noplist">no playlist</span>
                        )}
                      </small>
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
