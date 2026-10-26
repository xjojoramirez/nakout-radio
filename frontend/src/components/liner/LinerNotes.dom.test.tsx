import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { TrackDetail } from "../../types";
import { LinerNotes } from "./LinerNotes";
import { TrackFacts } from "./TrackFacts";

function detail(overrides: Partial<TrackDetail> = {}): TrackDetail {
  return {
    youtube_video_id: "vid1",
    title: "Blue in Green",
    artist: "Miles Davis",
    album: "Kind of Blue",
    album_artist: "Miles Davis",
    release_date: "1959-08-17",
    release_year: 1959,
    label: "Columbia",
    catalog_number: "CL 1355",
    isrc: "USSM15900001",
    track_number: 3,
    disc_number: 1,
    genres: ["jazz"],
    country: "US",
    language: "instrumental",
    bpm: 58,
    musical_key: "D minor",
    cover_url: null,
    summary: "A modal jazz ballad from Kind of Blue.",
    story: "Recorded in two sessions in 1959.",
    dj_note: "One for the rainy window.",
    lyric_snippet: null,
    moods: ["late night", "rainy day"],
    credits: [
      { role: "Trumpet", name: "Miles Davis" },
      { role: "Piano", name: "Bill Evans" },
    ],
    links: [
      {
        label: "Wikipedia",
        url: "https://en.wikipedia.org/wiki/Blue_in_Green",
      },
    ],
    charts: [
      {
        chart_name: "Billboard Hot 100",
        country: "US",
        peak: 1,
        weeks_on_chart: 12,
        year: 1959,
        source_url: "https://example.com/chart",
      },
    ],
    similar: [
      { youtube_video_id: "vid2", title: "So What", artist: "Miles Davis" },
    ],
    metadata_sources: [],
    ...overrides,
  };
}

describe("LinerNotes", () => {
  it("shows a loading state while the details are fetched", () => {
    render(<LinerNotes status="loading" detail={null} />);

    expect(screen.getByText("Fetching details…")).toBeInTheDocument();
  });

  it("says when a track has no details yet", () => {
    render(<LinerNotes status="missing" detail={null} />);

    expect(
      screen.getByText("Details not available for this track yet."),
    ).toBeInTheDocument();
  });

  it("offers a retry when the details are temporarily unavailable", () => {
    const onRetry = vi.fn();
    render(<LinerNotes status="error" detail={null} onRetry={onRetry} />);

    expect(
      screen.getByText("Details are not available at the moment."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalled();
  });

  it("renders nothing when no track is on air", () => {
    const { container } = render(<LinerNotes status="idle" detail={null} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("shows the story, DJ note and key lyric first", () => {
    render(<LinerNotes status="ready" detail={detail()} />);

    expect(
      screen.getByRole("tab", { name: "Story" }),
    ).toHaveAttribute("aria-selected", "true");
    expect(
      screen.getByText("A modal jazz ballad from Kind of Blue."),
    ).toBeInTheDocument();
    expect(screen.getByText("From the DJ")).toBeInTheDocument();
    expect(
      screen.getByText("One for the rainy window."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Recorded in two sessions in 1959."),
    ).toBeInTheDocument();
    expect(screen.getByText("Story source: Wikipedia")).toBeInTheDocument();
  });

  it("switches to the facts and credits tab", () => {
    render(<LinerNotes status="ready" detail={detail()} />);

    fireEvent.click(screen.getByRole("tab", { name: "Details" }));

    expect(screen.getByText("Kind of Blue")).toBeInTheDocument();
    expect(screen.getByText("Columbia")).toBeInTheDocument();
    expect(screen.getByText("USSM15900001")).toBeInTheDocument();
    expect(screen.getByText("Trumpet")).toBeInTheDocument();
    expect(screen.getByText("late night")).toBeInTheDocument();
    expect(screen.getByText("So What")).toBeInTheDocument();
  });

  it("switches to the chart history tab", () => {
    render(<LinerNotes status="ready" detail={detail()} />);

    fireEvent.click(screen.getByRole("tab", { name: "Charts" }));

    expect(screen.getByText("Billboard Hot 100")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Peak" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Source" })).toHaveAttribute(
      "href",
      "https://example.com/chart",
    );
  });

  it("credits the metadata providers on the details tab", () => {
    render(
      <LinerNotes
        status="ready"
        detail={detail({ metadata_sources: ["Deezer", "MusicBrainz"] })}
      />,
    );

    fireEvent.click(screen.getByRole("tab", { name: "Details" }));

    expect(
      screen.getByText("Metadata: Deezer · MusicBrainz"),
    ).toBeInTheDocument();
  });

  it("moves between tabs with the arrow keys", () => {
    render(<LinerNotes status="ready" detail={detail()} />);

    const story = screen.getByRole("tab", { name: "Story" });
    story.focus();
    fireEvent.keyDown(story, { key: "ArrowRight" });

    expect(screen.getByRole("tab", { name: "Details" })).toHaveFocus();
    expect(screen.getByRole("tab", { name: "Details" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("defaults to details when a track has facts but no story", () => {
    render(
      <LinerNotes
        status="ready"
        detail={detail({ summary: null, story: null, dj_note: null })}
      />,
    );

    expect(screen.getByRole("tab", { name: "Details" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByText("Kind of Blue")).toBeInTheDocument();
  });

  it("shows friendly empty states for sparse details", () => {
    render(
      <LinerNotes
        status="ready"
        detail={detail({
          summary: null,
          story: null,
          dj_note: null,
          charts: [],
        })}
      />,
    );

    fireEvent.click(screen.getByRole("tab", { name: "Story" }));
    expect(screen.getByText("No story for this track yet.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Charts" }));
    expect(screen.getByText("No chart history yet.")).toBeInTheDocument();
  });
});

describe("TrackFacts", () => {
  it("shows album, year and label under the artist", () => {
    render(<TrackFacts detail={detail()} />);

    expect(
      screen.getByText("Kind of Blue · 1959 · Columbia"),
    ).toBeInTheDocument();
  });

  it("renders nothing without facts", () => {
    const { container } = render(
      <TrackFacts detail={detail({ album: null, release_year: null, label: null })} />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing while the details are unavailable", () => {
    const { container } = render(<TrackFacts detail={null} />);

    expect(container).toBeEmptyDOMElement();
  });
});
