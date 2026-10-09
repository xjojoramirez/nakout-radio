import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../../api/client";
import type { Genre, Track } from "../../types";
import { NowPlayingPanel } from "./NowPlayingPanel";

vi.mock("../../api/client", async () => {
  const actual =
    await vi.importActual<typeof import("../../api/client")>(
      "../../api/client",
    );
  return {
    ...actual,
    api: {
      now: vi.fn(),
      syncAll: vi.fn(),
      genreTracks: vi.fn(),
      play: vi.fn(),
      playbackNext: vi.fn(),
      playbackPrev: vi.fn(),
      playbackAuto: vi.fn(),
      playbackStop: vi.fn(),
      setGenreOrder: vi.fn(),
    },
  };
});

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

const GENRE: Genre = {
  id: 1,
  name: "Chill",
  slug: "chill",
  is_default: true,
  track_count: 2,
  color: "#f2a33a",
};

const track = (id: string, title: string, position: number): Track => ({
  youtube_video_id: id,
  title,
  artist: "Artist",
  thumbnail_url: "",
  duration_seconds: 200,
  position,
});

const TRACK_A = track("a", "Alpha", 0);
const TRACK_B = track("b", "Beta", 1);

beforeEach(() => {
  mocked.genreTracks.mockResolvedValue([TRACK_A, TRACK_B]);
});

afterEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

function renderPanel(genres: Genre[] = [GENRE]) {
  return render(
    <NowPlayingPanel
      genres={genres}
      onNotice={vi.fn()}
      onError={vi.fn()}
    />,
  );
}

describe("NowPlayingPanel", () => {
  it("shows the on-air track and the queue", async () => {
    mocked.now.mockResolvedValue({
      genre: GENRE,
      track: TRACK_A,
      offset_seconds: 5,
      server_time: "2026-01-01T00:00:00+00:00",
      source: "schedule",
    });
    renderPanel();
    expect((await screen.findAllByText("Alpha")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("Beta")).length).toBeGreaterThan(0);
    expect(screen.getByText("On air")).toBeInTheDocument();
    expect(screen.getAllByText("3:20").length).toBeGreaterThan(0);
    expect(screen.getByText("Schedule")).toBeInTheDocument();
  });

  it("scrolls the current row into view on mobile after load", async () => {
    mocked.now.mockResolvedValue({
      genre: GENRE,
      track: TRACK_A,
      offset_seconds: 5,
      server_time: "2026-01-01T00:00:00+00:00",
      source: "schedule",
    });
    const spy = vi.spyOn(Element.prototype, "scrollIntoView");
    const original = window.matchMedia;
    window.matchMedia = (query: string) =>
      ({
        matches: query === "(max-width: 600px)",
        media: query,
        addEventListener: () => {},
        removeEventListener: () => {},
      }) as unknown as MediaQueryList;
    try {
      renderPanel();
      await screen.findAllByText("Schedule");
      const row = within(screen.getByRole("list"))
        .getByText("Alpha")
        .closest("li");
      expect(row).not.toBeNull();
      const instances = spy.mock.instances as unknown[];
      expect(instances).toContain(row);
      expect(instances.filter((el) => el === row)).toHaveLength(1);
    } finally {
      window.matchMedia = original;
    }
  });

  it("does not scroll the page on desktop after load", async () => {
    mocked.now.mockResolvedValue({
      genre: GENRE,
      track: TRACK_A,
      offset_seconds: 5,
      server_time: "2026-01-01T00:00:00+00:00",
      source: "schedule",
    });
    const spy = vi.spyOn(Element.prototype, "scrollIntoView");
    renderPanel();
    await screen.findByText("On air");
    expect(spy).not.toHaveBeenCalled();
  });

  it("shows an empty state when nothing is scheduled", async () => {
    mocked.now.mockResolvedValue({
      genre: null,
      track: null,
      offset_seconds: 0,
      server_time: "2026-01-01T00:00:00+00:00",
      source: "none",
    });
    renderPanel([]);
    expect(await screen.findByText("Nothing scheduled.")).toBeInTheDocument();
  });

  it("shows an error state when playback status cannot be loaded", async () => {
    mocked.now.mockRejectedValue(new Error("boom"));
    renderPanel([]);
    expect(
      await screen.findByText("Could not load playback status."),
    ).toBeInTheDocument();
  });

  it("asks for confirmation before cutting over, then plays", async () => {
    mocked.now.mockResolvedValue({
      genre: GENRE,
      track: TRACK_A,
      offset_seconds: 5,
      server_time: "2026-01-01T00:00:00+00:00",
      source: "schedule",
    });
    mocked.play.mockResolvedValue({ status: "ok" });
    renderPanel();
    const playButtons = await screen.findAllByText("Play");
    fireEvent.click(playButtons[1]);
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("A song is playing");
    fireEvent.click(within(dialog).getByText("Play now"));
    await waitFor(() => expect(mocked.play).toHaveBeenCalledWith(1, "b"));
  });

  it("calls next and prev for the selected genre", async () => {
    mocked.now.mockResolvedValue({
      genre: GENRE,
      track: TRACK_A,
      offset_seconds: 0,
      server_time: "x",
      source: "schedule",
    });
    mocked.playbackNext.mockResolvedValue({ status: "ok" });
    mocked.playbackPrev.mockResolvedValue({ status: "ok" });
    renderPanel();
    fireEvent.click(await screen.findByText("Next"));
    await waitFor(() => expect(mocked.playbackNext).toHaveBeenCalledWith(1));
    fireEvent.click(screen.getByText("Prev"));
    await waitFor(() => expect(mocked.playbackPrev).toHaveBeenCalledWith(1));
  });

  it("stops playback and takes the station off air", async () => {
    mocked.now.mockResolvedValue({
      genre: GENRE,
      track: TRACK_A,
      offset_seconds: 0,
      server_time: "x",
      source: "schedule",
    });
    mocked.playbackStop.mockResolvedValue({ status: "ok" });
    const onNotice = vi.fn();
    render(
      <NowPlayingPanel genres={[GENRE]} onNotice={onNotice} onError={vi.fn()} />,
    );
    fireEvent.click(await screen.findByText("Stop"));
    await waitFor(() => expect(mocked.playbackStop).toHaveBeenCalled());
    expect(onNotice).toHaveBeenCalledWith("Stopped playback.");
  });

  it("disables Stop when nothing is on air", async () => {
    mocked.now.mockResolvedValue({
      genre: null,
      track: null,
      offset_seconds: 0,
      server_time: "x",
      source: "none",
    });
    renderPanel([GENRE]);
    expect(await screen.findByText("Stop")).toBeDisabled();
  });

  it("enables Auto after the station is stopped", async () => {
    mocked.now.mockResolvedValue({
      genre: null,
      track: null,
      offset_seconds: 0,
      server_time: "x",
      source: "none",
    });
    renderPanel([GENRE]);
    expect(await screen.findByText("Auto")).not.toBeDisabled();
  });

  it("enables Auto in manual mode and returns to schedule", async () => {
    mocked.now.mockResolvedValue({
      genre: GENRE,
      track: TRACK_A,
      offset_seconds: 0,
      server_time: "x",
      source: "manual",
    });
    mocked.playbackAuto.mockResolvedValue({ status: "ok" });
    renderPanel();
    const auto = await screen.findByText("Auto");
    expect(auto).not.toBeDisabled();
    fireEvent.click(auto);
    await waitFor(() => expect(mocked.playbackAuto).toHaveBeenCalled());
  });

  it("disables Auto in automatic mode", async () => {
    mocked.now.mockResolvedValue({
      genre: GENRE,
      track: TRACK_A,
      offset_seconds: 0,
      server_time: "x",
      source: "schedule",
    });
    renderPanel();
    expect(await screen.findByText("Auto")).toBeDisabled();
  });

  it("shuffles and saves the new order", async () => {
    mocked.now.mockResolvedValue({
      genre: GENRE,
      track: TRACK_A,
      offset_seconds: 0,
      server_time: "x",
      source: "schedule",
    });
    mocked.setGenreOrder.mockResolvedValue({ status: "ok" });
    vi.spyOn(Math, "random").mockReturnValue(0);
    renderPanel();
    fireEvent.click(await screen.findByText("Shuffle"));
    await waitFor(() =>
      expect(mocked.setGenreOrder).toHaveBeenCalledWith(1, ["b", "a"]),
    );
  });

  it("syncs all playlists and reports the summary", async () => {
    mocked.now.mockResolvedValue({
      genre: null,
      track: null,
      offset_seconds: 0,
      server_time: "x",
      source: "none",
    });
    mocked.syncAll.mockResolvedValue({
      results: [
        { id: 1, synced: 2, error: null },
        { id: 2, synced: 0, error: "nope" },
      ],
    });
    const onNotice = vi.fn();
    render(
      <NowPlayingPanel
        genres={[]}
        onNotice={onNotice}
        onError={vi.fn()}
      />,
    );
    fireEvent.click(await screen.findByText("Sync all playlists"));
    await waitFor(() =>
      expect(onNotice).toHaveBeenCalledWith(
        "Synced 1 of 2 playlist(s); 1 failed.",
      ),
    );
  });

  it("refetches the queue after syncing playlists", async () => {
    mocked.now.mockResolvedValue({
      genre: GENRE,
      track: TRACK_A,
      offset_seconds: 0,
      server_time: "x",
      source: "schedule",
    });
    mocked.syncAll.mockResolvedValue({ results: [] });
    renderPanel();
    await screen.findAllByText("Play");
    expect(mocked.genreTracks).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByText("Sync all playlists"));
    await waitFor(() =>
      expect(mocked.genreTracks).toHaveBeenCalledTimes(2),
    );
  });

  it("refetches tracks when the genre changes", async () => {
    const GENRE_2: Genre = {
      id: 2,
      name: "Jazz",
      slug: "jazz",
      is_default: false,
      track_count: 0,
      color: "#e0654a",
    };
    mocked.now.mockResolvedValue({
      genre: GENRE,
      track: TRACK_A,
      offset_seconds: 0,
      server_time: "x",
      source: "schedule",
    });
    renderPanel([GENRE, GENRE_2]);
    await screen.findAllByText("Play");
    expect(mocked.genreTracks).toHaveBeenCalledWith(1);
    fireEvent.change(screen.getByLabelText("Genre to control"), {
      target: { value: "2" },
    });
    await waitFor(() => expect(mocked.genreTracks).toHaveBeenCalledWith(2));
  });

  it("selects the currently playing genre on load", async () => {
    const GENRE_2: Genre = {
      id: 2,
      name: "Jazz",
      slug: "jazz",
      is_default: false,
      track_count: 0,
      color: "#e0654a",
    };
    mocked.now.mockResolvedValue({
      genre: GENRE_2,
      track: TRACK_A,
      offset_seconds: 0,
      server_time: "x",
      source: "schedule",
    });
    renderPanel([GENRE, GENRE_2]);
    await waitFor(() =>
      expect(mocked.genreTracks).toHaveBeenLastCalledWith(2),
    );
    expect(screen.getByLabelText("Genre to control")).toHaveValue("2");
  });

  it("reorders on drag and drop", async () => {
    mocked.now.mockResolvedValue({
      genre: GENRE,
      track: TRACK_A,
      offset_seconds: 0,
      server_time: "x",
      source: "schedule",
    });
    mocked.setGenreOrder.mockResolvedValue({ status: "ok" });
    const { container } = renderPanel();
    await screen.findAllByText("Play");
    const rows = container.querySelectorAll(".queue-row");
    fireEvent.dragStart(rows[0]);
    fireEvent.dragOver(rows[1]);
    fireEvent.drop(rows[1]);
    await waitFor(() =>
      expect(mocked.setGenreOrder).toHaveBeenCalledWith(1, ["b", "a"]),
    );
  });

  it("restores the order when saving fails", async () => {
    mocked.now.mockResolvedValue({
      genre: GENRE,
      track: TRACK_A,
      offset_seconds: 0,
      server_time: "x",
      source: "schedule",
    });
    mocked.setGenreOrder.mockRejectedValue(new ApiError(500, "nope"));
    const onError = vi.fn();
    const { container } = render(
      <NowPlayingPanel genres={[GENRE]} onNotice={vi.fn()} onError={onError} />,
    );
    await screen.findAllByText("Play");
    const rows = container.querySelectorAll(".queue-row");
    fireEvent.dragStart(rows[0]);
    fireEvent.drop(rows[1]);
    await waitFor(() => expect(onError).toHaveBeenCalledWith("nope"));
    const titles = Array.from(
      container.querySelectorAll(".queue-title"),
    ).map((el) => el.textContent);
    expect(titles).toEqual(["Alpha", "Beta"]);
  });

  it("does not play when the confirmation is cancelled", async () => {
    mocked.now.mockResolvedValue({
      genre: GENRE,
      track: TRACK_A,
      offset_seconds: 0,
      server_time: "x",
      source: "schedule",
    });
    renderPanel();
    const playButtons = await screen.findAllByText("Play");
    fireEvent.click(playButtons[1]);
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByText("Cancel"));
    expect(mocked.play).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
  });

  it("reports an error when play fails", async () => {
    mocked.now.mockResolvedValue({
      genre: GENRE,
      track: TRACK_A,
      offset_seconds: 0,
      server_time: "x",
      source: "schedule",
    });
    mocked.play.mockRejectedValue(new ApiError(500, "boom"));
    const onError = vi.fn();
    render(
      <NowPlayingPanel genres={[GENRE]} onNotice={vi.fn()} onError={onError} />,
    );
    const playButtons = await screen.findAllByText("Play");
    fireEvent.click(playButtons[1]);
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByText("Play now"));
    await waitFor(() => expect(onError).toHaveBeenCalledWith("boom"));
  });
});
