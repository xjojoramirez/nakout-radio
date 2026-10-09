import type { CSSProperties } from "react";
import { GENRE_PALETTE } from "../../palette";

interface Props {
  label: string;
  value: string;
  onChange: (color: string) => void;
}

export function PaletteSwatches({ label, value, onChange }: Props) {
  return (
    <div className="swatches" role="radiogroup" aria-label={label}>
      {GENRE_PALETTE.map((c, i) => (
        <button
          key={c}
          type="button"
          role="radio"
          className="sw"
          aria-checked={value === c}
          aria-label={`Colour ${i + 1}`}
          style={{ "--gc": c } as CSSProperties}
          onClick={() => onChange(c)}
        />
      ))}
    </div>
  );
}
