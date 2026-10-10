import type { CSSProperties } from "react";
import type { Genre } from "../../types";

interface Props {
  label: string;
  genres: Genre[];
  value: number | null;
  onChange: (genreId: number) => void;
}

export function GenreChipRadio({ label, genres, value, onChange }: Props) {
  if (!genres.length) {
    return <p className="hint">Create a genre first, then come back.</p>;
  }
  return (
    <div className="chips" role="radiogroup" aria-label={label}>
      {genres.map((g) => (
        <button
          key={g.id}
          type="button"
          role="radio"
          className="gchip"
          aria-checked={g.id === value}
          style={{ "--gc": g.color || "var(--amber)" } as CSSProperties}
          onClick={() => onChange(g.id)}
        >
          <i className="dot" aria-hidden="true" />
          {g.name}
        </button>
      ))}
    </div>
  );
}
