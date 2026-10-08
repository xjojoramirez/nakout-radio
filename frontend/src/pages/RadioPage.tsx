import { NowPlaying } from "../components/NowPlaying";
import { OfflineNotice } from "../components/OfflineNotice";
import { VUMeter } from "../components/VUMeter";
import { useBroadcast } from "../hooks/useBroadcast";
import { useListenerCount } from "../hooks/useListenerCount";
import { useYouTubePlayer } from "../hooks/useYouTubePlayer";

function SoundOnIcon() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false">
      <path d="M3 9v6h4l5 4V5L7 9H3Z" fill="currentColor" />
      <path
        d="M15.5 8.7a4.7 4.7 0 0 1 0 6.6M18.3 6a8.5 8.5 0 0 1 0 12"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function SoundOffIcon() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false">
      <path d="M3 9v6h4l5 4V5L7 9H3Z" fill="currentColor" />
      <path
        d="M4.3 3 21 19.7"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function RadioPage() {
  const listeners = useListenerCount();
  const { state, refresh } = useBroadcast();
  const player = useYouTubePlayer("yt-player", state, refresh);

  const offline = state != null && (state.source === "none" || !state.track);

  return (
    <div className={offline ? "radio-cabinet offline" : "radio-cabinet"}>
      <header className="radio-header">
        <h1>Nakout Radio</h1>
        <span className="listeners">{listeners} listening</span>
      </header>

      <div id="yt-player" className="hidden-player" />

      {offline ? (
        <OfflineNotice />
      ) : (
        <>
          <NowPlaying
            track={player.error ? null : player.track}
            progress={player.progress}
          />
          <VUMeter playing={player.playing} seed={0} />

          <div className="genre-row">
            <span className="tuned-label">
              {state?.genre ? `Tuned: ${state.genre.name}` : "Off air"}
            </span>
          </div>

          <div className="controls">
            {player.error ? (
              <button type="button" className="tune-in" onClick={refresh}>
                RETRY
              </button>
            ) : (
              <button
                type="button"
                className="mute-btn"
                onClick={player.toggleMute}
                aria-label={player.muted ? "Unmute" : "Mute"}
                title={player.muted ? "Unmute" : "Mute"}
              >
                {player.muted ? <SoundOffIcon /> : <SoundOnIcon />}
              </button>
            )}
            <label className="volume">
              Volume
              <input
                type="range"
                min={0}
                max={100}
                value={player.volume}
                onChange={(event) =>
                  player.setVolume(Number(event.target.value))
                }
                aria-label="Volume"
              />
            </label>
          </div>
        </>
      )}
    </div>
  );
}
