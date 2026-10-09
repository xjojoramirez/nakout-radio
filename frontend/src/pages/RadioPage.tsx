import type { CSSProperties } from "react";
import { OfflineNotice } from "../components/OfflineNotice";
import { VUMeter } from "../components/VUMeter";
import { TurntableDeck } from "../components/deck/TurntableDeck";
import { VolumeKnob } from "../components/deck/VolumeKnob";
import { useBroadcast } from "../hooks/useBroadcast";
import { useListenerCount } from "../hooks/useListenerCount";
import { useTodaySchedule } from "../hooks/useTodaySchedule";
import { useYouTubePlayer } from "../hooks/useYouTubePlayer";
import { formatClock, todayScheduleRows } from "../utils/deck";

export function RadioPage() {
  const listeners = useListenerCount();
  const { today } = useTodaySchedule();
  const { state, refresh } = useBroadcast();
  const player = useYouTubePlayer("yt-player", state, refresh);

  const offline = state != null && (state.source === "none" || !state.track);
  const track = player.error ? null : player.track;
  const genreName = state?.genre?.name ?? null;
  const duration = track?.duration_seconds ?? 0;
  const pct =
    duration > 0
      ? Math.min(100, Math.max(0, (player.progress / duration) * 100))
      : 0;
  const rows = todayScheduleRows(today);

  return (
    <div className={offline ? "radio-page offline" : "radio-page"}>
      <header className="radio-top">
        <div className="brand">
          Nakout<span>.</span>Radio
        </div>
        <div className="onair">
          <span
            className={player.playing ? "led on" : "led"}
            aria-hidden="true"
          />
          <span>{player.playing ? "On air" : "Standing by"}</span>
          <span>{listeners} listening</span>
        </div>
      </header>

      <div id="yt-player" className="hidden-player" />

      <main className="deck-grid">
        <section className="deck-side" aria-label="Turntable">
          <TurntableDeck
            playing={player.playing}
            artUrl={track?.thumbnail_url ?? null}
          />
          <div className="mixer">
            <div className="dj">
              <small>On the decks</small>
              <strong>{genreName ?? "Nakout Radio"}</strong>
            </div>
            <VUMeter playing={player.playing} seed={0} />
            <div className="knob-row">
              <VolumeKnob
                label="Volume"
                value={player.volume}
                onChange={player.setVolume}
              />
              <span className="deck-knob" aria-hidden="true" />
              <span
                className="deck-knob"
                aria-hidden="true"
                style={{ "--r": "20deg" } as CSSProperties}
              />
              <span
                className="deck-knob"
                aria-hidden="true"
                style={{ "--r": "70deg" } as CSSProperties}
              />
            </div>
          </div>
        </section>

        <section className="np-col">
          {offline ? (
            <>
              <OfflineNotice />
              <p className="np-artist">
                The deck is at rest. Come back for the next show.
              </p>
            </>
          ) : (
            <>
              <div className="sleeve">
                {track?.thumbnail_url && (
                  <img className="np-cover" src={track.thumbnail_url} alt="" />
                )}
                <div>
                  <div className="kicker">
                    {genreName ? `${genreName} · live now` : "Live now"}
                  </div>
                  <h1 className="np-title">{track?.title ?? "Tune in"}</h1>
                  <div className="np-artist">
                    {track?.artist || "Nakout Radio"}
                  </div>
                </div>
              </div>
              <div>
                <div className="np-bar">
                  <div
                    className="np-bar-fill"
                    role="progressbar"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={Math.round(pct)}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <div className="np-times">
                  <span>{formatClock(player.progress)}</span>
                  <span>{formatClock(duration)}</span>
                </div>
              </div>
            </>
          )}

          <div className="np-controls">
            {player.error && !offline ? (
              <button type="button" className="tune-btn" onClick={refresh}>
                Retry
              </button>
            ) : (
              <button
                type="button"
                className="tune-btn"
                onClick={player.toggleMute}
                disabled={offline}
              >
                {player.muted ? "Tune in" : "Tune out"}
              </button>
            )}
          </div>

          <section className="sched" aria-label="Today's schedule">
            <h2>Today's schedule</h2>
            {rows.length > 0 ? (
              <ul>
                {rows.map((row) => (
                  <li key={row.id} className={row.isNow ? "now" : undefined}>
                    <span>{row.name}</span>
                    <span>{row.range}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="np-artist">No schedule slots yet.</p>
            )}
          </section>
        </section>
      </main>
    </div>
  );
}
