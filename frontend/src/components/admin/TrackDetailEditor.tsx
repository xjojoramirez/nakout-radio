import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../../api/client";
import type { StudioTrackDetail, TrackDetailInput } from "../../types";
import { messageFor } from "../../utils/errors";
import { ConfirmDialog } from "../ConfirmDialog";

const LOCKABLE_FIELDS = [
  "album",
  "album_artist",
  "release_date",
  "release_year",
  "label",
  "catalog_number",
  "isrc",
  "track_number",
  "disc_number",
  "genres",
  "country",
  "language",
  "bpm",
  "musical_key",
  "cover_url",
  "summary",
  "story",
  "dj_note",
  "lyric_snippet",
  "moods",
  "credits",
  "links",
  "charts",
] as const;

const CHART_SUGGESTIONS = [
  "Billboard Hot 100",
  "Billboard Global 200",
  "Billboard Hot R&B/Hip-Hop Songs",
  "Billboard Hot Country Songs",
  "Billboard Hot Rock & Alternative Songs",
  "Billboard Pop Airplay",
  "Billboard Philippines Hot 100",
  "UK Singles Chart",
  "ARIA Singles Chart",
  "Oricon Combined Singles",
];

interface ChartDraft {
  chart_name: string;
  country: string;
  peak: string;
  weeks_on_chart: string;
  year: string;
  source_url: string;
}

interface CreditDraft {
  role: string;
  name: string;
}

interface LinkDraft {
  label: string;
  url: string;
}

interface SimilarDraft {
  youtube_video_id: string;
  title: string;
  artist: string;
}

interface Draft {
  album: string;
  album_artist: string;
  release_date: string;
  release_year: string;
  label: string;
  catalog_number: string;
  isrc: string;
  track_number: string;
  disc_number: string;
  genres: string;
  country: string;
  language: string;
  bpm: string;
  musical_key: string;
  cover_url: string;
  summary: string;
  story: string;
  dj_note: string;
  dj_note_public: boolean;
  lyric_snippet: string;
  moods: string;
  credits: CreditDraft[];
  links: LinkDraft[];
  charts: ChartDraft[];
  similar: SimilarDraft[];
}

const text = (value: string | null) => value ?? "";
const numeric = (value: number | null) =>
  value === null || value === undefined ? "" : String(value);

function draftFrom(detail: StudioTrackDetail): Draft {
  return {
    album: text(detail.album),
    album_artist: text(detail.album_artist),
    release_date: text(detail.release_date),
    release_year: numeric(detail.release_year),
    label: text(detail.label),
    catalog_number: text(detail.catalog_number),
    isrc: text(detail.isrc),
    track_number: numeric(detail.track_number),
    disc_number: numeric(detail.disc_number),
    genres: detail.genres.join(", "),
    country: text(detail.country),
    language: text(detail.language),
    bpm: numeric(detail.bpm),
    musical_key: text(detail.musical_key),
    cover_url: text(detail.cover_url),
    summary: text(detail.summary),
    story: text(detail.story),
    dj_note: text(detail.dj_note),
    dj_note_public: detail.dj_note_public,
    lyric_snippet: text(detail.lyric_snippet),
    moods: detail.moods.join(", "),
    credits: detail.credits.map((credit) => ({
      role: credit.role,
      name: credit.name,
    })),
    links: detail.links.map((link) => ({ label: link.label, url: link.url })),
    charts: detail.charts.map((chart) => ({
      chart_name: chart.chart_name,
      country: chart.country,
      peak: String(chart.peak),
      weeks_on_chart: numeric(chart.weeks_on_chart),
      year: numeric(chart.year),
      source_url: chart.source_url,
    })),
    similar: detail.similar.map((track) => ({ ...track })),
  };
}

const splitList = (value: string) =>
  value
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);

const PROVIDER_LABELS: Record<string, string> = {
  deezer: "Deezer",
  musicbrainz: "MusicBrainz",
};

const providerLabel = (provider: string) =>
  PROVIDER_LABELS[provider] ?? provider;

const nullable = (value: string) => value.trim() || null;

const toInt = (value: string) => {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? Math.trunc(parsed) : null;
};

function payloadFrom(draft: Draft, protect: boolean): TrackDetailInput {
  const payload: TrackDetailInput = {
    album: nullable(draft.album),
    album_artist: nullable(draft.album_artist),
    release_date: nullable(draft.release_date),
    release_year: toInt(draft.release_year),
    label: nullable(draft.label),
    catalog_number: nullable(draft.catalog_number),
    isrc: nullable(draft.isrc),
    track_number: toInt(draft.track_number),
    disc_number: toInt(draft.disc_number),
    genres: splitList(draft.genres),
    country: nullable(draft.country),
    language: nullable(draft.language),
    bpm: toInt(draft.bpm),
    musical_key: nullable(draft.musical_key),
    cover_url: nullable(draft.cover_url),
    summary: nullable(draft.summary),
    story: nullable(draft.story),
    dj_note: nullable(draft.dj_note),
    dj_note_public: draft.dj_note_public,
    lyric_snippet: nullable(draft.lyric_snippet),
    moods: splitList(draft.moods),
    credits: draft.credits
      .filter((credit) => credit.role.trim() || credit.name.trim())
      .map((credit) => ({
        role: credit.role.trim(),
        name: credit.name.trim(),
      })),
    links: draft.links
      .filter((link) => link.label.trim() || link.url.trim())
      .map((link) => ({ label: link.label.trim(), url: link.url.trim() })),
    charts: draft.charts
      .filter((chart) => Object.values(chart).some((value) => value.trim()))
      .map((chart) => ({
        chart_name: chart.chart_name.trim(),
        country: chart.country.trim(),
        peak: Number(chart.peak) || 0,
        weeks_on_chart: toInt(chart.weeks_on_chart),
        year: toInt(chart.year),
        source_url: chart.source_url.trim(),
      })),
    similar_video_ids: draft.similar.map((track) => track.youtube_video_id),
    locked_fields: [],
  };

  if (protect) {
    payload.locked_fields = LOCKABLE_FIELDS.filter((field) => {
      const value = payload[field as keyof TrackDetailInput];
      if (Array.isArray(value)) return value.length > 0;
      return value !== null && value !== undefined && value !== "";
    });
  }

  return payload;
}

interface Props {
  videoId: string;
  onClose: () => void;
  onSaved: (message: string) => void;
  onError: (message: string) => void;
}

export function TrackDetailEditor({
  videoId,
  onClose,
  onSaved,
  onError,
}: Props) {
  const [detail, setDetail] = useState<StudioTrackDetail | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [error, setError] = useState("");
  const [protect, setProtect] = useState(true);
  const [confirmClear, setConfirmClear] = useState(false);
  const [similarQuery, setSimilarQuery] = useState("");
  const [similarResults, setSimilarResults] = useState<
    { youtube_video_id: string; title: string; artist: string }[]
  >([]);
  const cardRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    api.studioTrack(videoId).then(
      (loaded) => {
        if (!active) return;
        setDetail(loaded);
        setDraft(draftFrom(loaded));
        setLoading(false);
      },
      (failure: unknown) => {
        if (!active) return;
        setError(messageFor(failure));
        setLoading(false);
      },
    );
    return () => {
      active = false;
    };
  }, [videoId]);

  useEffect(() => {
    cardRef.current?.focus();
  }, [loading]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !confirmClear) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [confirmClear, onClose]);

  useEffect(() => {
    const query = similarQuery.trim();
    if (query.length < 2) {
      setSimilarResults([]);
      return;
    }
    let active = true;
    const timer = window.setTimeout(() => {
      api
        .listTracks({ q: query, limit: 6 })
        .then((page) => {
          if (active) setSimilarResults(page.items);
        })
        .catch(() => {
          if (active) setSimilarResults([]);
        });
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [similarQuery]);

  const update = <K extends keyof Draft>(key: K, value: Draft[K]) => {
    setDraft((current) => (current ? { ...current, [key]: value } : current));
  };

  const updateCredit = (
    index: number,
    field: "role" | "name",
    value: string,
  ) => {
    setDraft((current) => {
      if (!current) return current;
      const credits = current.credits.map((credit, i) =>
        i === index ? { ...credit, [field]: value } : credit,
      );
      return { ...current, credits };
    });
  };

  const updateLink = (
    index: number,
    field: "label" | "url",
    value: string,
  ) => {
    setDraft((current) => {
      if (!current) return current;
      const links = current.links.map((link, i) =>
        i === index ? { ...link, [field]: value } : link,
      );
      return { ...current, links };
    });
  };

  const updateChart = (
    index: number,
    field: keyof ChartDraft,
    value: string,
  ) => {
    setDraft((current) => {
      if (!current) return current;
      const charts = current.charts.map((chart, i) =>
        i === index ? { ...chart, [field]: value } : chart,
      );
      return { ...current, charts };
    });
  };

  const removeCredit = (index: number) =>
    setDraft((current) =>
      current
        ? { ...current, credits: current.credits.filter((_, i) => i !== index) }
        : current,
    );

  const removeLink = (index: number) =>
    setDraft((current) =>
      current
        ? { ...current, links: current.links.filter((_, i) => i !== index) }
        : current,
    );

  const removeChart = (index: number) =>
    setDraft((current) =>
      current
        ? { ...current, charts: current.charts.filter((_, i) => i !== index) }
        : current,
    );

  const removeSimilar = (index: number) =>
    setDraft((current) =>
      current
        ? { ...current, similar: current.similar.filter((_, i) => i !== index) }
        : current,
    );

  const submit = async () => {
    if (!draft) return;
    setError("");

    const incompleteChart = draft.charts.find((chart) => {
      const touched = Object.values(chart).some((value) => value.trim());
      return touched && (!chart.chart_name.trim() || !chart.peak.trim());
    });
    if (incompleteChart) {
      setError("Each chart needs a name and a peak position.");
      return;
    }
    const incompleteCredit = draft.credits.find(
      (credit) =>
        (credit.role.trim() || credit.name.trim()) &&
        (!credit.role.trim() || !credit.name.trim()),
    );
    if (incompleteCredit) {
      setError("Each credit needs both a role and a name.");
      return;
    }
    const incompleteLink = draft.links.find(
      (link) =>
        (link.label.trim() || link.url.trim()) &&
        (!link.label.trim() || !link.url.trim()),
    );
    if (incompleteLink) {
      setError("Each link needs both a label and a URL.");
      return;
    }

    setSaving(true);
    try {
      const saved = await api.saveStudioTrack(
        videoId,
        payloadFrom(draft, protect),
      );
      setDetail(saved);
      onSaved("Track details saved");
      onClose();
    } catch (failure) {
      setError(messageFor(failure));
    } finally {
      setSaving(false);
    }
  };

  const clear = async () => {
    setConfirmClear(false);
    try {
      await api.deleteStudioTrack(videoId);
      onSaved("Track details cleared");
      onClose();
    } catch (failure) {
      onError(messageFor(failure));
    }
  };

  const fetchDetails = async () => {
    setFetching(true);
    setError("");
    try {
      const saved = await api.enrichTrack(videoId);
      setDetail(saved);
      setDraft(draftFrom(saved));
      onSaved(
        saved.metadata_sources.length > 0
          ? "Details fetched"
          : "No details found for this track",
      );
    } catch (failure) {
      setError(messageFor(failure));
    } finally {
      setFetching(false);
    }
  };

  const addChart = () => {
    update("charts", [
      ...(draft?.charts ?? []),
      {
        chart_name: "",
        country: "",
        peak: "",
        weeks_on_chart: "",
        year: "",
        source_url: "",
      },
    ]);
  };

  const similarOptions = similarResults.filter(
    (candidate) =>
      candidate.youtube_video_id !== videoId &&
      !draft?.similar.some(
        (track) => track.youtube_video_id === candidate.youtube_video_id,
      ),
  );

  return createPortal(
    <div
      className="modal-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className="modal-card track-editor"
        role="dialog"
        aria-modal="true"
        aria-labelledby="track-editor-title"
        tabIndex={-1}
        ref={cardRef}
      >
        <header className="track-editor-head">
          <div>
            <span className="kicker">Track details</span>
            <h2 id="track-editor-title">{detail?.title ?? "Track"}</h2>
            <p className="np-artist">{detail?.artist ?? ""}</p>
          </div>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={fetchDetails}
            disabled={loading || fetching || saving}
          >
            {fetching ? "Fetching…" : "Fetch details"}
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={onClose}
          >
            Close
          </button>
        </header>

        {error && (
          <p className="error banner" role="alert">
            {error}
          </p>
        )}

        {loading && <p className="hint">Loading details…</p>}

        {!loading && draft && (
          <form
            className="track-editor-form"
            onSubmit={(event) => {
              event.preventDefault();
              submit();
            }}
          >
            <fieldset className="track-editor-section">
              <legend>Facts</legend>
              <div className="te-grid">
                <label className="field">
                  Album
                  <input
                    value={draft.album}
                    onChange={(event) => update("album", event.target.value)}
                  />
                </label>
                <label className="field">
                  Album artist
                  <input
                    value={draft.album_artist}
                    onChange={(event) =>
                      update("album_artist", event.target.value)
                    }
                  />
                </label>
                <label className="field">
                  Release date
                  <input
                    placeholder="1959-08-17"
                    value={draft.release_date}
                    onChange={(event) =>
                      update("release_date", event.target.value)
                    }
                  />
                </label>
                <label className="field">
                  Release year
                  <input
                    inputMode="numeric"
                    value={draft.release_year}
                    onChange={(event) =>
                      update("release_year", event.target.value)
                    }
                  />
                </label>
                <label className="field">
                  Label
                  <input
                    value={draft.label}
                    onChange={(event) => update("label", event.target.value)}
                  />
                </label>
                <label className="field">
                  Catalog no.
                  <input
                    value={draft.catalog_number}
                    onChange={(event) =>
                      update("catalog_number", event.target.value)
                    }
                  />
                </label>
                <label className="field">
                  ISRC
                  <input
                    value={draft.isrc}
                    onChange={(event) => update("isrc", event.target.value)}
                  />
                </label>
                <label className="field">
                  Track no.
                  <input
                    inputMode="numeric"
                    value={draft.track_number}
                    onChange={(event) =>
                      update("track_number", event.target.value)
                    }
                  />
                </label>
                <label className="field">
                  Disc no.
                  <input
                    inputMode="numeric"
                    value={draft.disc_number}
                    onChange={(event) =>
                      update("disc_number", event.target.value)
                    }
                  />
                </label>
                <label className="field">
                  Genres
                  <input
                    placeholder="jazz, modal jazz"
                    value={draft.genres}
                    onChange={(event) => update("genres", event.target.value)}
                  />
                </label>
                <label className="field">
                  Country
                  <input
                    value={draft.country}
                    onChange={(event) => update("country", event.target.value)}
                  />
                </label>
                <label className="field">
                  Language
                  <input
                    value={draft.language}
                    onChange={(event) => update("language", event.target.value)}
                  />
                </label>
                <label className="field">
                  BPM
                  <input
                    inputMode="numeric"
                    value={draft.bpm}
                    onChange={(event) => update("bpm", event.target.value)}
                  />
                </label>
                <label className="field">
                  Musical key
                  <input
                    value={draft.musical_key}
                    onChange={(event) =>
                      update("musical_key", event.target.value)
                    }
                  />
                </label>
                <label className="field">
                  Cover URL
                  <input
                    value={draft.cover_url}
                    onChange={(event) =>
                      update("cover_url", event.target.value)
                    }
                  />
                </label>
              </div>
            </fieldset>

            <fieldset className="track-editor-section">
              <legend>Story &amp; notes</legend>
              <label className="field">
                Summary
                <textarea
                  rows={2}
                  maxLength={1000}
                  value={draft.summary}
                  onChange={(event) => update("summary", event.target.value)}
                />
              </label>
              <label className="field">
                Story
                <textarea
                  rows={5}
                  maxLength={20000}
                  value={draft.story}
                  onChange={(event) => update("story", event.target.value)}
                />
              </label>
              <label className="field">
                DJ note
                <textarea
                  rows={2}
                  maxLength={4000}
                  value={draft.dj_note}
                  onChange={(event) => update("dj_note", event.target.value)}
                />
              </label>
              <label className="te-check">
                <input
                  type="checkbox"
                  checked={draft.dj_note_public}
                  onChange={(event) =>
                    update("dj_note_public", event.target.checked)
                  }
                />
                Show the DJ note on the radio page
              </label>
              <label className="field">
                Key lyric
                <input
                  maxLength={200}
                  placeholder="Short excerpt only (200 characters)"
                  value={draft.lyric_snippet}
                  onChange={(event) =>
                    update("lyric_snippet", event.target.value)
                  }
                />
              </label>
              <label className="field">
                Moods
                <input
                  placeholder="late night, rainy day"
                  value={draft.moods}
                  onChange={(event) => update("moods", event.target.value)}
                />
              </label>
            </fieldset>

            <fieldset className="track-editor-section">
              <legend>Credits</legend>
              {draft.credits.map((credit, index) => (
                <div className="te-row" key={index}>
                  <input
                    aria-label={`Credit ${index + 1} role`}
                    placeholder="Role"
                    value={credit.role}
                    onChange={(event) =>
                      updateCredit(index, "role",
                        event.target.value,
                      )
                    }
                  />
                  <input
                    aria-label={`Credit ${index + 1} name`}
                    placeholder="Name"
                    value={credit.name}
                    onChange={(event) =>
                      updateCredit(index, "name",
                        event.target.value,
                      )
                    }
                  />
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    aria-label={`Remove credit ${index + 1}`}
                    onClick={() => removeCredit(index)}
                  >
                    Remove
                  </button>
                </div>
              ))}
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() =>
                  update("credits", [...draft.credits, { role: "", name: "" }])
                }
              >
                Add credit
              </button>
            </fieldset>

            <fieldset className="track-editor-section">
              <legend>Links</legend>
              {draft.links.map((link, index) => (
                <div className="te-row" key={index}>
                  <input
                    aria-label={`Link ${index + 1} label`}
                    placeholder="Label"
                    value={link.label}
                    onChange={(event) =>
                      updateLink(index, "label",
                        event.target.value,
                      )
                    }
                  />
                  <input
                    aria-label={`Link ${index + 1} URL`}
                    placeholder="https://…"
                    value={link.url}
                    onChange={(event) =>
                      updateLink(index, "url",
                        event.target.value,
                      )
                    }
                  />
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    aria-label={`Remove link ${index + 1}`}
                    onClick={() => removeLink(index)}
                  >
                    Remove
                  </button>
                </div>
              ))}
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() =>
                  update("links", [...draft.links, { label: "", url: "" }])
                }
              >
                Add link
              </button>
            </fieldset>

            <fieldset className="track-editor-section">
              <legend>Also on the station</legend>
              <label className="field">
                Find similar tracks
                <input
                  placeholder="Search the library…"
                  value={similarQuery}
                  onChange={(event) => setSimilarQuery(event.target.value)}
                />
              </label>
              {similarOptions.length > 0 && (
                <ul className="te-similar-results">
                  {similarOptions.map((candidate) => (
                    <li key={candidate.youtube_video_id}>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() => {
                          update("similar", [
                            ...draft.similar,
                            {
                              youtube_video_id: candidate.youtube_video_id,
                              title: candidate.title,
                              artist: candidate.artist,
                            },
                          ]);
                          setSimilarQuery("");
                          setSimilarResults([]);
                        }}
                      >
                        {candidate.title} — {candidate.artist}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {draft.similar.length > 0 && (
                <ul className="te-chips">
                  {draft.similar.map((track, index) => (
                    <li key={track.youtube_video_id}>
                      <span>
                        {track.title}
                        {track.artist ? ` — ${track.artist}` : ""}
                      </span>
                      <button
                        type="button"
                        aria-label={`Remove similar track ${track.title}`}
                        onClick={() => removeSimilar(index)}
                      >
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </fieldset>

            <fieldset className="track-editor-section">
              <legend>Chart history</legend>
              <datalist id="chart-suggestions">
                {CHART_SUGGESTIONS.map((name) => (
                  <option key={name} value={name} />
                ))}
              </datalist>
              {draft.charts.map((chart, index) => (
                <div className="te-chart-row" key={index}>
                  <input
                    aria-label={`Chart ${index + 1} name`}
                    list="chart-suggestions"
                    placeholder="Chart"
                    value={chart.chart_name}
                    onChange={(event) =>
                      updateChart(index, "chart_name",
                        event.target.value,
                      )
                    }
                  />
                  <input
                    aria-label={`Chart ${index + 1} country`}
                    placeholder="US"
                    value={chart.country}
                    onChange={(event) =>
                      updateChart(index, "country",
                        event.target.value,
                      )
                    }
                  />
                  <input
                    aria-label={`Chart ${index + 1} peak`}
                    inputMode="numeric"
                    placeholder="Peak"
                    value={chart.peak}
                    onChange={(event) =>
                      updateChart(index, "peak",
                        event.target.value,
                      )
                    }
                  />
                  <input
                    aria-label={`Chart ${index + 1} weeks`}
                    inputMode="numeric"
                    placeholder="Weeks"
                    value={chart.weeks_on_chart}
                    onChange={(event) =>
                      updateChart(index, "weeks_on_chart",
                        event.target.value,
                      )
                    }
                  />
                  <input
                    aria-label={`Chart ${index + 1} year`}
                    inputMode="numeric"
                    placeholder="Year"
                    value={chart.year}
                    onChange={(event) =>
                      updateChart(index, "year",
                        event.target.value,
                      )
                    }
                  />
                  <input
                    aria-label={`Chart ${index + 1} source`}
                    placeholder="Source URL"
                    value={chart.source_url}
                    onChange={(event) =>
                      updateChart(index, "source_url",
                        event.target.value,
                      )
                    }
                  />
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    aria-label={`Remove chart ${index + 1}`}
                    onClick={() => removeChart(index)}
                  >
                    Remove
                  </button>
                </div>
              ))}
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={addChart}
              >
                Add chart
              </button>
            </fieldset>

            {detail &&
              (detail.enriched_at ||
                detail.story_at ||
                detail.needs_review ||
                detail.enrich_error ||
                detail.story_error ||
                Object.keys(detail.sources).length > 0) && (
                <fieldset className="track-editor-section">
                  <legend>Metadata</legend>
                  {detail.needs_review && (
                    <p className="te-warning">
                      This match is fuzzy — check the album, label and year
                      before trusting it.
                    </p>
                  )}
                  <p className="hint">
                    {detail.enriched_at
                      ? `Fetched ${new Date(
                          detail.enriched_at,
                        ).toLocaleDateString()}`
                      : "Not fetched yet"}
                    {detail.story_at &&
                      ` · Story checked ${new Date(
                        detail.story_at,
                      ).toLocaleDateString()}`}
                    {detail.metadata_sources.length > 0 &&
                      ` · ${detail.metadata_sources.join(" · ")}`}
                  </p>
                  {detail.enrich_error && (
                    <p className="te-warning">{detail.enrich_error}</p>
                  )}
                  {detail.story_error && (
                    <p className="te-warning">{detail.story_error}</p>
                  )}
                  {Object.keys(detail.sources).length > 0 && (
                    <ul className="te-sources">
                      {Object.entries(detail.sources).map(
                        ([field, source]) => (
                          <li key={field}>
                            <span>{field.replace(/_/g, " ")}</span>
                            {source.url ? (
                              <a
                                href={source.url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                {providerLabel(source.provider)}
                              </a>
                            ) : (
                              <span>{providerLabel(source.provider)}</span>
                            )}
                          </li>
                        ),
                      )}
                    </ul>
                  )}
                </fieldset>
              )}

            <label className="te-check">
              <input
                type="checkbox"
                checked={protect}
                onChange={(event) => setProtect(event.target.checked)}
              />
              Protect these details from auto-refresh
            </label>

            <footer className="te-actions">
              <button
                type="button"
                className="btn btn-danger"
                onClick={() => setConfirmClear(true)}
              >
                Clear details
              </button>
              <span className="te-spacer" />
              <button
                type="button"
                className="btn btn-secondary"
                onClick={onClose}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={saving}
              >
                {saving ? "Saving…" : "Save"}
              </button>
            </footer>
          </form>
        )}

        {!loading && !draft && (
          <footer className="te-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              Close
            </button>
          </footer>
        )}
      </div>

      {confirmClear && (
        <ConfirmDialog
          title="Clear track details?"
          message="This removes every fact, story and chart entry for this track. The track itself stays in the library."
          confirmLabel="Clear details"
          danger
          onConfirm={clear}
          onCancel={() => setConfirmClear(false)}
        />
      )}
    </div>,
    document.body,
  );
}
