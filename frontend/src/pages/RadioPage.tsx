import { NowPlaying } from "../components/NowPlaying";
import { VUMeter } from "../components/VUMeter";
import { useBroadcast } from "../hooks/useBroadcast";
import { useListenerCount } from "../hooks/useListenerCount";
import { useYouTubePlayer } from "../hooks/useYouTubePlayer";

export function RadioPage() {
  const listeners = useListenerCount();
  const { state, refresh } = useBroadcast();
  const player = useYouTubePlayer("yt-player", state, refresh);

  return (
    <div className="radio-cabinet">
      <header className="radio-header">
        <h1>Nakout Radio</h1>
        <span className="listeners">{listeners} listening</span>
      </header>

      <div id="yt-player" className="hidden-player" />

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
          <button type="button" className="tune-in" onClick={player.toggleMute}>
            {player.muted ? "UNMUTE" : "MUTE"}
          </button>
        )}
        <label className="volume">
          Volume
          <input
            type="range"
            min={0}
            max={100}
            value={player.volume}
            onChange={(event) => player.setVolume(Number(event.target.value))}
            aria-label="Volume"
          />
        </label>
      </div>
    </div>
  );
}
