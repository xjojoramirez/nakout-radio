import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  StudioTrackDetail,
  TrackLibraryItem,
  TrackLibraryPage,
} from "../../types";
import { api } from "../../api/client";
import { TrackLibraryPanel } from "./TrackLibraryPanel";

vi.mock("../../api/client", () => ({
  api: {
    listTracks: vi.fn(),
    studioTrack: vi.fn(),
    saveStudioTrack: vi.fn(),
    deleteStudioTrack: vi.fn(),
  },
}));

const mocked = api as unknown as {
  listTracks: ReturnType<typeof vi.fn>;
  studioTrack: ReturnType<typeof vi.fn>;
  saveStudioTrack: ReturnType<typeof vi.fn>;
  deleteStudioTrack: ReturnType<typeof vi.fn>;
};

function item(overrides: Partial<TrackLibraryItem> = {}): TrackLibraryItem {
  return {
    youtube_video_id: "vid1",
    title: "Blue in Green",
    artist: "Miles Davis",
    thumbnail_url: "",
    duration_seconds: 337,
    album: "Kind of Blue",
    release_year: 1959,
    status: "curated",
    completeness: 3,
    genres: ["Jazz"],
    ...overrides,
  };
}

function page(items: TrackLibraryItem[]): TrackLibraryPage {
  return { items, total: items.length, limit: 50, offset: 0 };
}

function detail(
  overrides: Partial<StudioTrackDetail> = {},
): StudioTrackDetail {
  return {
    youtube_video_id: "vid1",
    title: "Blue in Green",
    artist: "Miles Davis",
    album: "Kind of Blue",
    album_artist: "Miles Davis",
    release_date: "1959-08-17",
    release_year: 1959,
    label: "Columbia",
    catalog_number: null,
    isrc: null,
    track_number: 3,
    disc_number: 1,
    genres: ["jazz"],
    country: "US",
    language: null,
    bpm: null,
    musical_key: null,
    cover_url: null,
    summary: "A modal jazz ballad.",
    story: "Recorded in two sessions in 1959.",
    dj_note: null,
    dj_note_public: true,
    lyric_snippet: null,
    moods: [],
    credits: [{ role: "Trumpet", name: "Miles Davis" }],
    links: [],
    charts: [
      {
        chart_name: "Billboard Hot 100",
        country: "US",
        peak: 1,
        weeks_on_chart: 12,
        year: 1959,
        source_url: "",
      },
    ],
    similar: [],
    sources: {},
    locked_fields: ["album"],
    needs_review: false,
    enriched_at: null,
    enrich_error: null,
    created_at: null,
    updated_at: null,
    status: "curated",
    completeness: 4,
    ...overrides,
  };
}

function renderPanel() {
  const onNotice = vi.fn();
  const onError = vi.fn();
  const onCountChange = vi.fn();
  render(
    <TrackLibraryPanel
      onNotice={onNotice}
      onError={onError}
      onCountChange={onCountChange}
    />,
  );
  return { onNotice, onError, onCountChange };
}

beforeEach(() => {
  vi.clearAllMocks();
  mocked.listTracks.mockResolvedValue(page([item()]));
});

describe("TrackLibraryPanel", () => {
  it("lists tracks with their detail status and completeness", async () => {
    const { onCountChange } = renderPanel();

    expect(await screen.findByText("Blue in Green")).toBeInTheDocument();
    expect(screen.getByText("Miles Davis")).toBeInTheDocument();
    expect(screen.getByText("Kind of Blue · 1959")).toBeInTheDocument();
    expect(screen.getByText("3/6")).toBeInTheDocument();
    expect(
      screen.getByLabelText("Details status: Curated"),
    ).toBeInTheDocument();
    expect(onCountChange).toHaveBeenCalledWith(1);
  });

  it("searches by title or artist", async () => {
    renderPanel();
    await screen.findByText("Blue in Green");

    fireEvent.change(screen.getByLabelText("Search library"), {
      target: { value: "miles" },
    });

    await waitFor(() =>
      expect(mocked.listTracks).toHaveBeenLastCalledWith(
        expect.objectContaining({ q: "miles" }),
      ),
    );
  });

  it("filters by detail status", async () => {
    renderPanel();
    await screen.findByText("Blue in Green");

    fireEvent.change(screen.getByLabelText("Filter by status"), {
      target: { value: "empty" },
    });

    await waitFor(() =>
      expect(mocked.listTracks).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: "empty" }),
      ),
    );
  });

  it("shows an empty state when nothing matches", async () => {
    mocked.listTracks.mockResolvedValue(page([]));

    renderPanel();

    expect(await screen.findByText("No tracks match.")).toBeInTheDocument();
  });

  it("opens the editor and saves manual edits with protection", async () => {
    mocked.studioTrack.mockResolvedValue(detail());
    mocked.saveStudioTrack.mockResolvedValue(
      detail({ album: "Kind of Blue (Legacy)" }),
    );
    const { onNotice } = renderPanel();

    fireEvent.click(
      await screen.findByRole("button", { name: /Blue in Green/ }),
    );
    const album = await screen.findByLabelText("Album");
    expect(album).toHaveValue("Kind of Blue");

    fireEvent.change(album, { target: { value: "Kind of Blue (Legacy)" } });
    fireEvent.change(screen.getByLabelText("DJ note"), {
      target: { value: "One for the rainy window." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(mocked.saveStudioTrack).toHaveBeenCalled());
    const [videoId, payload] = mocked.saveStudioTrack.mock.calls[0];
    expect(videoId).toBe("vid1");
    expect(payload.album).toBe("Kind of Blue (Legacy)");
    expect(payload.dj_note).toBe("One for the rainy window.");
    expect(payload.locked_fields).toContain("album");
    expect(payload.locked_fields).toContain("dj_note");
    expect(onNotice).toHaveBeenCalledWith("Track details saved");
  });

  it("refuses to save a chart without a peak", async () => {
    mocked.studioTrack.mockResolvedValue(detail({ charts: [] }));
    renderPanel();

    fireEvent.click(
      await screen.findByRole("button", { name: /Blue in Green/ }),
    );
    fireEvent.click(await screen.findByRole("button", { name: "Add chart" }));
    fireEvent.change(screen.getByLabelText("Chart 1 name"), {
      target: { value: "Billboard Hot 100" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(
      await screen.findByText("Each chart needs a name and a peak position."),
    ).toBeInTheDocument();
    expect(mocked.saveStudioTrack).not.toHaveBeenCalled();
  });

  it("clears details after confirmation", async () => {
    mocked.studioTrack.mockResolvedValue(detail());
    mocked.deleteStudioTrack.mockResolvedValue({ status: "deleted" });
    const { onNotice } = renderPanel();

    fireEvent.click(
      await screen.findByRole("button", { name: /Blue in Green/ }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Clear details" }),
    );

    const dialog = await screen.findByRole("dialog", {
      name: "Clear track details?",
    });
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Clear details" }),
    );

    await waitFor(() =>
      expect(mocked.deleteStudioTrack).toHaveBeenCalledWith("vid1"),
    );
    expect(onNotice).toHaveBeenCalledWith("Track details cleared");
  });
});
