interface Props {
  playing: boolean;
  seed: number;
}

export function VUMeter({ playing, seed }: Props) {
  const bars = Array.from({ length: 12 }, (_, i) => {
    const base = playing ? 40 + ((seed + i * 7) % 60) : 6;
    return Math.min(100, base);
  });
  return (
    <div className={playing ? "vu-meter playing" : "vu-meter"} aria-hidden="true">
      {bars.map((height, i) => (
        <div key={i} className="vu-bar" style={{ height: `${height}%` }} />
      ))}
    </div>
  );
}
