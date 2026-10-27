import type { TrackDetail } from "../../types";

/** Album · year · label line under the artist, when the facts are known. */
export function TrackFacts({ detail }: { detail: TrackDetail | null }) {
  if (!detail) return null;
  const parts = [
    detail.album,
    detail.release_year ? String(detail.release_year) : null,
    detail.label,
  ].filter(Boolean);

  if (parts.length === 0) return null;
  return <div className="np-facts">{parts.join(" · ")}</div>;
}
