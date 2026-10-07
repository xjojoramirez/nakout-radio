import type { Genre } from "../types";

interface Props {
  genres: Genre[];
  activeSlug: string | null;
  onSelect: (slug: string) => void;
}

export function GenreDial({ genres, activeSlug, onSelect }: Props) {
  const activeIndex = genres.findIndex((s) => s.slug === activeSlug);
  const angle =
    genres.length && activeIndex >= 0
      ? -120 + (240 / Math.max(1, genres.length - 1)) * activeIndex
      : -120;

  return (
    <div className="genre-dial">
      <div
        className="knob"
        aria-hidden="true"
        style={{ transform: `rotate(${angle}deg)` }}
      >
        <div className="knob-indicator" />
      </div>
      <ul className="genre-list">
        {genres.map((s) => (
          <li key={s.slug}>
            <button
              type="button"
              className={s.slug === activeSlug ? "active" : ""}
              aria-current={s.slug === activeSlug ? "true" : undefined}
              onClick={() => onSelect(s.slug)}
            >
              {s.name}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
