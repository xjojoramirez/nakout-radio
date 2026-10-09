import { useEffect, useRef } from "react";

interface Props {
  playing: boolean;
  artUrl: string | null;
}

/** 33 and a third RPM = 200 deg/sec, with spin-up / spin-down inertia. */
const DEG_PER_SECOND = 200;

export function TurntableDeck({ playing, artUrl }: Props) {
  const recordRef = useRef<HTMLDivElement | null>(null);
  const angleRef = useRef(0);
  const playingRef = useRef(playing);
  playingRef.current = playing;

  useEffect(() => {
    const reduce =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) return;
    let raf = 0;
    let last = performance.now();
    let omega = 0;
    const frame = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const target = playingRef.current ? DEG_PER_SECOND : 0;
      omega +=
        (target - omega) * Math.min(1, dt * (playingRef.current ? 1.6 : 1.1));
      if (Math.abs(omega) < 0.2 && target === 0) omega = 0;
      angleRef.current = (angleRef.current + omega * dt) % 360;
      const el = recordRef.current;
      if (el) {
        el.style.transform = `rotate(${angleRef.current.toFixed(2)}deg)`;
      }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div className={playing ? "deck playing" : "deck"}>
      <div className="platter">
        <div className="record" ref={recordRef}>
          <div
            className="label"
            style={artUrl ? { backgroundImage: `url(${artUrl})` } : undefined}
          />
        </div>
        <div className="sheen" />
      </div>
      <div className="pivot" />
      <div className="arm" />
      <div className="deck-rpm" aria-hidden="true">
        <b className="on">33</b>
        <b>45</b>
      </div>
    </div>
  );
}
