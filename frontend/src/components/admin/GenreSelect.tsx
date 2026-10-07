import type { Genre } from "../../types";

interface Props {
  label: string;
  genres: Genre[];
  value: string;
  onChange: (value: string) => void;
}

export function GenreSelect({ label, genres, value, onChange }: Props) {
  return (
    <label className="field">
      {label}
      <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Select a genre…</option>
        {genres.map((s) => (
          <option key={s.slug} value={s.id}>
            {s.name}
          </option>
        ))}
      </select>
    </label>
  );
}
