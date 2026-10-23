const LEVELS = [41, 48, 55, 62, 69, 76, 83, 90, 97, 44, 51, 58];

interface Props {
  playing: boolean;
}

export function VUMeter({ playing }: Props) {
  return (
    <div className={playing ? "vu-meter playing" : "vu-meter"} aria-hidden="true">
      {LEVELS.map((level, i) => (
        <div
          key={i}
          className="vu-bar"
          style={{ height: `${playing ? level : 6}%` }}
        />
      ))}
    </div>
  );
}
