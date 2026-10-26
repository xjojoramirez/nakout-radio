import { useId, useRef, useState, type KeyboardEvent } from "react";
import type { TrackDetail, TrackDetailStatus } from "../../types";

type TabId = "story" | "details" | "charts";

const TABS: { id: TabId; label: string }[] = [
  { id: "story", label: "Story" },
  { id: "details", label: "Details" },
  { id: "charts", label: "Charts" },
];

interface Props {
  detail: TrackDetail | null;
  status: TrackDetailStatus;
  onRetry?: () => void;
}

function paragraphs(text: string): string[] {
  return text
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function wikipediaLink(detail: TrackDetail) {
  return detail.links.find(
    (link) =>
      /wikipedia/i.test(link.label) || /wikipedia\.org/i.test(link.url),
  );
}

function StoryPanel({ detail }: { detail: TrackDetail }) {
  const source = wikipediaLink(detail);
  const hasStory = Boolean(
    detail.summary || detail.story || detail.dj_note || detail.lyric_snippet,
  );

  if (!hasStory) {
    return <p className="liner-empty">No story for this track yet.</p>;
  }

  return (
    <div className="liner-story">
      {detail.dj_note && (
        <div className="liner-dj">
          <span className="liner-label">From the DJ</span>
          <p>{detail.dj_note}</p>
        </div>
      )}
      {detail.summary && <p className="liner-summary">{detail.summary}</p>}
      {detail.story &&
        paragraphs(detail.story).map((part, index) => (
          <p key={index}>{part}</p>
        ))}
      {detail.lyric_snippet && (
        <blockquote className="liner-lyric">
          <span className="liner-label">Key lyric</span>
          <p>&ldquo;{detail.lyric_snippet}&rdquo;</p>
        </blockquote>
      )}
      {source && (
        <a
          className="liner-attribution"
          href={source.url}
          target="_blank"
          rel="noreferrer"
        >
          Story source: {source.label}
        </a>
      )}
    </div>
  );
}

function FactsPanel({ detail }: { detail: TrackDetail }) {
  const facts: [string, string][] = [];
  const add = (label: string, value: string | number | null | undefined) => {
    if (value !== null && value !== undefined && value !== "") {
      facts.push([label, String(value)]);
    }
  };

  add("Album", detail.album);
  add("Album artist", detail.album_artist);
  add("Released", detail.release_date || detail.release_year);
  add("Label", detail.label);
  add("Catalog", detail.catalog_number);
  add("ISRC", detail.isrc);
  add("Track", detail.track_number);
  add("Disc", detail.disc_number);
  add("Genre", detail.genres.join(", "));
  add("BPM", detail.bpm);
  add("Key", detail.musical_key);
  add("Country", detail.country);
  add("Language", detail.language);

  const hasCredits = detail.credits.length > 0;
  const hasMoods = detail.moods.length > 0;
  const hasLinks = detail.links.length > 0;
  const similar = detail.similar.filter((item) => item.title);
  const isEmpty =
    facts.length === 0 &&
    !hasCredits &&
    !hasMoods &&
    !hasLinks &&
    similar.length === 0;

  if (isEmpty) {
    return <p className="liner-empty">No extra details yet.</p>;
  }

  return (
    <div className="liner-details">
      {facts.length > 0 && (
        <dl className="liner-facts">
          {facts.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      )}

      {hasCredits && (
        <section className="liner-block">
          <h3>Credits</h3>
          <dl className="liner-credits">
            {detail.credits.map((credit, index) => (
              <div key={`${credit.role}-${credit.name}-${index}`}>
                <dt>{credit.role}</dt>
                <dd>{credit.name}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {hasMoods && (
        <section className="liner-block">
          <h3>Moods</h3>
          <ul className="liner-chips">
            {detail.moods.map((mood) => (
              <li key={mood}>{mood}</li>
            ))}
          </ul>
        </section>
      )}

      {similar.length > 0 && (
        <section className="liner-block">
          <h3>Also on the station</h3>
          <ul className="liner-similar">
            {similar.map((item) => (
              <li key={item.youtube_video_id}>
                <span>{item.title}</span>
                {item.artist && <small>{item.artist}</small>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {hasLinks && (
        <section className="liner-block">
          <h3>Links</h3>
          <ul className="liner-links">
            {detail.links.map((link) => (
              <li key={`${link.label}-${link.url}`}>
                <a href={link.url} target="_blank" rel="noreferrer">
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function ChartsPanel({ detail }: { detail: TrackDetail }) {
  if (detail.charts.length === 0) {
    return <p className="liner-empty">No chart history yet.</p>;
  }

  return (
    <div className="liner-charts-wrap">
      <table className="liner-charts">
        <thead>
          <tr>
            <th scope="col">Chart</th>
            <th scope="col">Peak</th>
            <th scope="col">Weeks</th>
            <th scope="col">Year</th>
            <th scope="col">Country</th>
            <th scope="col">
              <span className="sr-only">Source</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {detail.charts.map((chart, index) => (
            <tr key={`${chart.chart_name}-${chart.year}-${index}`}>
              <th scope="row">{chart.chart_name}</th>
              <td>#{chart.peak}</td>
              <td>{chart.weeks_on_chart ?? "—"}</td>
              <td>{chart.year ?? "—"}</td>
              <td>{chart.country || "—"}</td>
              <td>
                {chart.source_url ? (
                  <a
                    href={chart.source_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Source
                  </a>
                ) : (
                  "—"
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Inline "liner notes" card for the track on air.
 *
 * The card is always present while a track plays, with explicit states for
 * fetching, "no details yet", and "temporarily unavailable". Story / Details /
 * Charts are real tabs; empty tabs explain themselves instead of disappearing.
 */
export function LinerNotes({ detail, status, onRetry }: Props) {
  const baseId = useId();
  const [tab, setTab] = useState<TabId>("story");
  const tabRefs = useRef<Partial<Record<TabId, HTMLButtonElement | null>>>({});

  if (status === "idle") return null;

  const active = detail ? tab : "story";

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next = index;
    if (event.key === "ArrowRight") next = (index + 1) % TABS.length;
    else if (event.key === "ArrowLeft")
      next = (index - 1 + TABS.length) % TABS.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = TABS.length - 1;
    else return;

    event.preventDefault();
    const id = TABS[next].id;
    setTab(id);
    tabRefs.current[id]?.focus();
  };

  return (
    <section className="liner" aria-labelledby={`${baseId}-title`}>
      <header className="liner-head">
        <h2 id={`${baseId}-title`}>Liner notes</h2>
        <span className="liner-kicker">On the record</span>
      </header>

      {status === "loading" && (
        <div className="liner-state" aria-busy="true">
          <span className="liner-skeleton" aria-hidden="true" />
          <span className="liner-skeleton short" aria-hidden="true" />
          <p>Fetching details…</p>
        </div>
      )}

      {status === "missing" && (
        <div className="liner-state">
          <p>Details not available for this track yet.</p>
          <p className="liner-hint">
            The station is still digging through the crates.
          </p>
        </div>
      )}

      {status === "error" && (
        <div className="liner-state">
          <p>Details are not available at the moment.</p>
          {onRetry && (
            <button type="button" className="liner-retry" onClick={onRetry}>
              Retry
            </button>
          )}
        </div>
      )}

      {status === "ready" && detail && (
        <>
          <div className="liner-tabs" role="tablist" aria-label="Track details">
            {TABS.map((entry, index) => (
              <button
                key={entry.id}
                type="button"
                role="tab"
                id={`${baseId}-tab-${entry.id}`}
                aria-selected={active === entry.id}
                aria-controls={`${baseId}-panel`}
                tabIndex={active === entry.id ? 0 : -1}
                ref={(element) => {
                  tabRefs.current[entry.id] = element;
                }}
                onClick={() => setTab(entry.id)}
                onKeyDown={(event) => onKeyDown(event, index)}
              >
                {entry.label}
              </button>
            ))}
          </div>

          <div
            className="liner-panel"
            role="tabpanel"
            id={`${baseId}-panel`}
            aria-labelledby={`${baseId}-tab-${active}`}
            tabIndex={0}
          >
            {active === "story" && <StoryPanel detail={detail} />}
            {active === "details" && <FactsPanel detail={detail} />}
            {active === "charts" && <ChartsPanel detail={detail} />}
          </div>
        </>
      )}
    </section>
  );
}
