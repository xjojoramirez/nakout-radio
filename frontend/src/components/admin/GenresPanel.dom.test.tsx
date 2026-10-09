import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import type { Genre, Track } from "../../types";
import { GenresPanel } from "./GenresPanel";

vi.mock("../../api/client", async () => {
  const actual =
    await vi.importActual<typeof import("../../api/client")>(
      "../../api/client",
    );
  return {
    ...actual,
    api: {
      ...actual.api,
      createGenre: vi.fn(),
      updateGenre: vi.fn(),
      deleteGenre: vi.fn(),
      genreTracks: vi.fn(),
      play: vi.fn(),
    },
  };
});

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

const genres: Genre[] = [
  {
    id: 1,
    name: "Emo Night",
    slug: "EN",
    is_default: false,
    color: "#f2a33a",
    track_count: 12,
  },
  {
    id: 2,
    name: "NU Metal",
    slug: "numetal",
    is_default: false,
    color: "#e0654a",
    track_count: 0,
  },
  {
    id: 3,
    name: "Late Night",
    slug: "late",
    is_default: true,
    color: "#5fb3b3",
    track_count: 4,
  },
];

const trackFixture: Track[] = [
  {
    youtube_video_id: "v1",
    title: "First",
    artist: "A",
    thumbnail_url: "",
    duration_seconds: 180,
    position: 0,
  },
  {
    youtube_video_id: "v2",
    title: "Second",
    artist: "A",
    thumbnail_url: "",
    duration_seconds: 200,
    position: 1,
  },
];

afterEach(() => {
  vi.clearAllMocks();
});

function renderPanel(
  overrides: Partial<Parameters<typeof GenresPanel>[0]> = {},
) {
  const onNotice = overrides.onNotice ?? vi.fn();
  const onError = overrides.onError ?? vi.fn();
  const onJump = overrides.onJump ?? vi.fn();
  render(
    <GenresPanel
      genres={overrides.genres ?? genres}
      onGenresChanged={overrides.onGenresChanged ?? (async () => {})}
      onNotice={onNotice}
      onError={onError}
      onJump={onJump}
    />,
  );
  return { onNotice, onError, onJump };
}

describe("GenresPanel", () => {
  it("renders genre cards with colour, slug, track chips and a default pill", () => {
    renderPanel();
    const card = screen.getByText("Emo Night").closest(".gcard");
    expect(card).not.toBeNull();
    expect(
      (card as HTMLElement).style.getPropertyValue("--gc"),
    ).toBe("#f2a33a");
    expect(within(card as HTMLElement).getByText("/EN")).toBeInTheDocument();
    expect(
      within(card as HTMLElement).getByText("12 tracks"),
    ).toBeInTheDocument();
    const defaultCard = screen.getByText("Late Night").closest(".gcard");
    expect(defaultCard).not.toBeNull();
    expect(
      within(defaultCard as HTMLElement).getByText("default"),
    ).toBeInTheDocument();
    expect(
      within(card as HTMLElement).queryByText("default"),
    ).toBeNull();
  });

  it("warns and quick-links an empty genre to playlists and schedule", () => {
    const onJump = vi.fn();
    renderPanel({ onJump });
    const card = screen.getByText("NU Metal").closest(".gcard");
    expect(card).not.toBeNull();
    expect(
      within(card as HTMLElement).getByText("No playlists"),
    ).toBeInTheDocument();
    fireEvent.click(
      within(card as HTMLElement).getByRole("button", { name: "Add one" }),
    );
    expect(onJump).toHaveBeenCalledWith("playlists", { playlistsGenre: 2 });
    fireEvent.click(
      within(card as HTMLElement).getByRole("button", {
        name: "Schedule it",
      }),
    );
    expect(onJump).toHaveBeenCalledWith("schedule", { scheduleGenre: 2 });
    const fedCard = screen.getByText("Emo Night").closest(".gcard");
    expect(
      within(fedCard as HTMLElement).queryByText("Add one"),
    ).toBeNull();
  });

  it("slug auto-fills from the name until manually edited", () => {
    renderPanel();
    const name = screen.getByLabelText("Genre name") as HTMLInputElement;
    const slug = screen.getByLabelText("Genre slug") as HTMLInputElement;
    fireEvent.change(name, { target: { value: "Sunday Acoustic" } });
    expect(slug.value).toBe("sundayacoustic");
    fireEvent.change(slug, { target: { value: "custom" } });
    fireEvent.change(name, { target: { value: "Something Else" } });
    expect(slug.value).toBe("custom");
  });

  it("add button stays disabled until name and slug are filled", () => {
    renderPanel();
    const add = screen.getByRole("button", { name: "Add genre" });
    expect(add).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Genre name"), {
      target: { value: "Jazz" },
    });
    expect(add).toBeEnabled();
    fireEvent.change(screen.getByLabelText("Genre slug"), {
      target: { value: "" },
    });
    expect(add).toBeDisabled();
  });

  it("add form sends the chosen colour and reports the notice", async () => {
    const { onNotice } = renderPanel();
    mocked.createGenre.mockResolvedValue({
      id: 9,
      name: "Jazz",
      slug: "jazz",
      is_default: false,
      color: "#5fb3b3",
      track_count: 0,
    });
    fireEvent.change(screen.getByLabelText("Genre name"), {
      target: { value: "Jazz" },
    });
    expect(
      (screen.getByLabelText("Genre slug") as HTMLInputElement).value,
    ).toBe("jazz");
    const swatches = screen.getByRole("radiogroup", { name: "Genre colour" });
    fireEvent.click(within(swatches).getAllByRole("radio")[3]);
    fireEvent.click(screen.getByRole("button", { name: "Add genre" }));
    await waitFor(() =>
      expect(mocked.createGenre).toHaveBeenCalledWith(
        "Jazz",
        "jazz",
        "#5fb3b3",
      ),
    );
    expect(onNotice).toHaveBeenCalledWith(
      "Jazz added. Add a playlist and a schedule slot to put it on air.",
    );
  });

  it("Play now posts the genre's first track, notices and jumps to now", async () => {
    const { onNotice, onJump } = renderPanel();
    mocked.genreTracks.mockResolvedValue(trackFixture);
    mocked.play.mockResolvedValue({ status: "ok" });
    fireEvent.click(
      screen.getByRole("button", { name: "Play now Emo Night" }),
    );
    await waitFor(() => expect(mocked.genreTracks).toHaveBeenCalledWith(1));
    await waitFor(() =>
      expect(mocked.play).toHaveBeenCalledWith(1, "v1"),
    );
    expect(onNotice).toHaveBeenCalledWith("Now playing Emo Night.");
    expect(onJump).toHaveBeenCalledWith("now");
  });

  it("Play now on an empty genre errors and never calls play", async () => {
    const { onError, onJump } = renderPanel();
    mocked.genreTracks.mockResolvedValue([]);
    fireEvent.click(
      screen.getByRole("button", { name: "Play now NU Metal" }),
    );
    await waitFor(() => expect(mocked.genreTracks).toHaveBeenCalledWith(2));
    expect(mocked.play).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledWith(
      '"NU Metal" has no tracks yet. Add a playlist.',
    );
    expect(onJump).not.toHaveBeenCalled();
  });

  it("edit supports changing the colour", async () => {
    mocked.updateGenre.mockResolvedValue({ ...genres[0], color: "#d8c18a" });
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Edit Emo Night" }));
    const swatches = screen.getAllByRole("radiogroup", {
      name: "Genre colour",
    })[1];
    fireEvent.click(within(swatches).getAllByRole("radio")[7]);
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(mocked.updateGenre).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ color: "#d8c18a" }),
      ),
    );
    await waitFor(() =>
      expect(
        screen
          .getByText("Emo Night")
          .closest(".gcard")
          ?.className.includes("flash"),
      ).toBe(true),
    );
    expect(screen.getByRole("button", { name: "Edit Emo Night" })).toBeEnabled();
  });

  it("Save stays disabled while name or slug is empty and calls nothing", () => {
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Edit Emo Night" }));
    const save = screen.getByRole("button", { name: "Save" });
    expect(save).toBeEnabled();
    fireEvent.change(screen.getByLabelText("Edit genre name"), {
      target: { value: "" },
    });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Edit genre slug"), {
      target: { value: "  " },
    });
    expect(save).toBeDisabled();
    expect(mocked.updateGenre).not.toHaveBeenCalled();
  });

  it("delete keeps the confirm dialog flow and cancel aborts", async () => {
    mocked.deleteGenre.mockResolvedValue({ status: "deleted" });
    const { onNotice } = renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Delete Emo Night" }));
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText(/playlists, tracks, and schedule slots/),
    ).toBeInTheDocument();
    fireEvent.click(within(dialog).getByText("Cancel"));
    expect(mocked.deleteGenre).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete NU Metal" }));
    fireEvent.click(
      within(await screen.findByRole("dialog")).getByText("Delete"),
    );
    await waitFor(() => expect(mocked.deleteGenre).toHaveBeenCalledWith(2));
    expect(onNotice).toHaveBeenCalledWith("Genre deleted.");
  });

  it("shows the empty state when there are no genres", () => {
    renderPanel({ genres: [] });
    expect(
      screen.getByText("No genres yet. Create your first one above."),
    ).toBeInTheDocument();
  });
});
