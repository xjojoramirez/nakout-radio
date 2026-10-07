import type { Track } from "../types";

interface Props {
  track: Track | null;
  progress: number;
}

export function NowPlaying({ track, progress }: Props) {
  if (!track) {
    return (
      <div className="now-playing empty" role="status">
        Genre off air
      </div>
    );
  }
  const pct =
    track.duration_seconds > 0
      ? Math.min(100, Math.max(0, (progress / track.duration_seconds) * 100))
      : 0;
  return (
    <div className="now-playing">
      {track.thumbnail_url && (
        <img className="art" src={track.thumbnail_url} alt="" />
      )}
      <div className="meta">
        <div className="title">{track.title}</div>
        <div className="artist">{track.artist}</div>
        <div className="progress-track">
          <div
            className="progress-fill"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(pct)}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
    </div>
  );
}
