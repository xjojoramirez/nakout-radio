import {
  useRef,
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent,
} from "react";

interface Props {
  value: number;
  onChange: (value: number) => void;
  label: string;
  disabled?: boolean;
}

function clamp(value: number): number {
  return Math.min(100, Math.max(0, Math.round(value)));
}

export function VolumeKnob({ value, onChange, label, disabled }: Props) {
  const dragRef = useRef<{ startY: number; startValue: number } | null>(null);

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (disabled) return;
    dragRef.current = { startY: event.clientY, startValue: value };
    if (typeof event.currentTarget.setPointerCapture === "function") {
      event.currentTarget.setPointerCapture(event.pointerId);
    }
  };

  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (disabled) return;
    const drag = dragRef.current;
    if (!drag) return;
    onChange(clamp(drag.startValue + (drag.startY - event.clientY) / 2));
  };

  const onPointerUp = (event: PointerEvent<HTMLDivElement>) => {
    dragRef.current = null;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };

  const onPointerCancel = () => {
    dragRef.current = null;
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (disabled) return;
    const step = event.shiftKey ? 10 : 2;
    let next: number | null = null;
    if (event.key === "ArrowUp" || event.key === "ArrowRight") {
      next = value + step;
    } else if (event.key === "ArrowDown" || event.key === "ArrowLeft") {
      next = value - step;
    } else if (event.key === "PageUp") {
      next = value + 10;
    } else if (event.key === "PageDown") {
      next = value - 10;
    } else if (event.key === "Home") {
      next = 0;
    } else if (event.key === "End") {
      next = 100;
    }
    if (next === null) return;
    event.preventDefault();
    onChange(clamp(next));
  };

  const angle = -135 + (value / 100) * 270;

  return (
    <div
      className={
        disabled ? "deck-knob interactive disabled" : "deck-knob interactive"
      }
      role="slider"
      tabIndex={disabled ? -1 : 0}
      aria-label={label}
      aria-disabled={disabled || undefined}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={value}
      aria-valuetext={`${value}%`}
      style={{ "--r": `${angle.toFixed(1)}deg` } as CSSProperties}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerCancel}
      onKeyDown={onKeyDown}
    />
  );
}
