import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import type { AddedPlaylist, ChannelPlaylist, Genre } from "../../types";
import { AddPlaylistDialog } from "./AddPlaylistDialog";

vi.mock("../../utils/profile", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../utils/profile")>()),
  cssCover: () => 'url("https://example.com/cover.png")',
}));

vi.mock("../../api/client", async () => {
  const actual =
    await vi.importActual<typeof import("../../api/client")>(
      "../../api/client",
    );
  return {
    ...actual,
    api: {
      ...actual.api,
      listPlaylists: vi.fn(),
      createPlaylist: vi.fn(),
      getChannelSource: vi.fn(),
      setChannelSource: vi.fn(),
      listChannelPlaylists: vi.fn(),
    },
  };
});

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

const genres: Genre[] = [
  {
    id: 1,
    name: "Emo Night",
    slug: "emo",
    is_default: false,
    color: "#f2a33a",
    track_count: 56,
  },
  {
    id: 2,
    name: "NU Metal",
    slug: "numetal",
    is_default: false,
    color: "#6fa3e0",
    track_count: 37,
  },
];

const added: AddedPlaylist[] = [
  {
    id: 11,
    genre_id: 1,
    genre_name: "Emo Night",
    youtube_playlist_id: "PLGIA_2k2o8yAAAA",
    label: "",
    track_count: 56,
    synced_at: new Date().toISOString(),
  },
];

const channelPlaylists: ChannelPlaylist[] = [
  {
    youtube_playlist_id: "PLnew",
    title: "New One",
    item_count: 5,
    thumbnail_url: "u",
    already_added: false,
  },
  {
    youtube_playlist_id: "PLGIA_2k2o8yAAAA",
    title: "Old One",
    item_count: 9,
    thumbnail_url: "",
    already_added: true,
  },
];

function renderDialog(
  overrides: Partial<Parameters<typeof AddPlaylistDialog>[0]> = {},
) {
  const onClose = overrides.onClose ?? vi.fn();
  const onAdded = overrides.onAdded ?? vi.fn(async () => {});
  const onSchedule = overrides.onSchedule ?? vi.fn();
  render(
    <AddPlaylistDialog
      genres={overrides.genres ?? genres}
      lockedGenreId={overrides.lockedGenreId}
      onClose={onClose}
      onAdded={onAdded}
      onSchedule={onSchedule}
    />,
  );
  return { onClose, onAdded, onSchedule };
}

describe("AddPlaylistDialog", () => {
  beforeEach(() => {
    mocked.listPlaylists.mockResolvedValue(added);
    mocked.getChannelSource.mockResolvedValue({
      channel_id: null,
      title: null,
    });
    mocked.listChannelPlaylists.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("locks the genre when opened from a genre card", async () => {
    renderDialog({ lockedGenreId: 1 });
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByRole("heading", { name: "Add to Emo Night" }),
    ).toBeInTheDocument();
    expect(within(dialog).getByText("Will play in")).toBeInTheDocument();
    expect(
      within(dialog).queryByRole("radiogroup", { name: "Genre" }),
    ).not.toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: "Add to Emo Night" }),
    ).toBeDisabled();
  });

  it("validates a link, adds it and offers the next steps", async () => {
    mocked.createPlaylist.mockResolvedValue({
      id: 30,
      youtube_playlist_id: "PLnew",
      synced: 7,
      sync_error: null,
    });
    const { onAdded, onSchedule } = renderDialog({ lockedGenreId: 1 });
    const input = screen.getByLabelText("YouTube playlist link");

    fireEvent.change(input, {
      target: { value: "https://www.youtube.com/playlist?list=PLnew" },
    });
    expect(screen.getByText("Playlist ID found: PLnew")).toBeInTheDocument();
    const add = screen.getByRole("button", { name: "Add to Emo Night" });
    expect(add).toBeEnabled();
    fireEvent.click(add);

    await waitFor(() =>
      expect(mocked.createPlaylist).toHaveBeenCalledWith(
        1,
        "https://www.youtube.com/playlist?list=PLnew",
        "",
      ),
    );
    expect(onAdded).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ id: 30, synced: 7 }),
    );
    expect(
      await screen.findByText("Nakout playlist added to Emo Night."),
    ).toBeInTheDocument();
    expect(screen.getByText("Synced 7 tracks so far.")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Schedule this genre" }),
    );
    expect(onSchedule).toHaveBeenCalledWith(1);

    fireEvent.click(screen.getByRole("button", { name: "Add another" }));
    expect(
      screen.getByRole("button", { name: "Add to Emo Night" }),
    ).toBeInTheDocument();
  });

  it("requires a genre when opened without a lock", async () => {
    renderDialog();
    fireEvent.change(screen.getByLabelText("YouTube playlist link"), {
      target: { value: "https://www.youtube.com/playlist?list=PLnew" },
    });
    const add = screen.getByRole("button", { name: "Add Nakout playlist" });
    expect(add).toBeDisabled();
    expect(screen.getByText("Choose a genre to continue.")).toBeInTheDocument();

    const radioGroup = screen.getByRole("radiogroup", { name: "Genre" });
    fireEvent.click(
      within(radioGroup).getByRole("radio", { name: "NU Metal" }),
    );
    expect(add).toBeEnabled();
    expect(
      screen.getByRole("button", { name: "Add to NU Metal" }),
    ).toBeInTheDocument();
  });

  it("flags an invalid link and a duplicate", async () => {
    renderDialog({ lockedGenreId: 1 });
    const input = screen.getByLabelText("YouTube playlist link");
    const hint = () =>
      document.querySelector(".addpl-form .hint") as HTMLElement;

    fireEvent.change(input, { target: { value: "not a link" } });
    expect(hint().className).toBe("hint err");

    fireEvent.change(input, {
      target: {
        value: "https://www.youtube.com/playlist?list=PLGIA_2k2o8yAAAA",
      },
    });
    await waitFor(() =>
      expect(hint().textContent).toBe(
        "This is already a Nakout playlist under Emo Night.",
      ),
    );
    expect(
      screen.getByRole("button", { name: "Add to Emo Night" }),
    ).toBeDisabled();
  });

  it("connects the Nakout channel and browses its playlists", async () => {
    mocked.setChannelSource.mockResolvedValue({
      channel_id: "UC1",
      title: "My Channel",
    });
    mocked.listChannelPlaylists.mockResolvedValue(channelPlaylists);
    renderDialog({ lockedGenreId: 1 });

    fireEvent.click(
      screen.getByRole("button", { name: "From the Nakout channel" }),
    );
    fireEvent.change(await screen.findByLabelText("YouTube channel"), {
      target: { value: "@me" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Connect channel" }));

    await waitFor(() =>
      expect(mocked.setChannelSource).toHaveBeenCalledWith("@me"),
    );
    expect(await screen.findByText("New One")).toBeInTheDocument();
    const newCard = screen.getByText("New One").closest(".pcard");
    expect(newCard).not.toBeNull();
    expect(within(newCard as HTMLElement).getByText("5 tracks")).toBeInTheDocument();
    const oldCard = screen.getByText("Old One").closest(".pcard");
    expect(
      within(oldCard as HTMLElement).getByText("Emo Night"),
    ).toBeInTheDocument();
  });

  it("adds a channel playlist to the locked genre", async () => {
    mocked.getChannelSource.mockResolvedValue({
      channel_id: "UC1",
      title: "My Channel",
    });
    mocked.listChannelPlaylists.mockResolvedValue(channelPlaylists);
    mocked.createPlaylist.mockResolvedValue({
      id: 30,
      youtube_playlist_id: "PLnew",
      synced: 5,
      sync_error: null,
    });
    const { onAdded } = renderDialog({ lockedGenreId: 1 });

    fireEvent.click(
      screen.getByRole("button", { name: "From the Nakout channel" }),
    );
    await screen.findByText("New One");
    fireEvent.click(
      within(
        screen.getByText("New One").closest(".pcard") as HTMLElement,
      ).getByRole("button", { name: "Add" }),
    );

    await waitFor(() =>
      expect(mocked.createPlaylist).toHaveBeenCalledWith(
        1,
        "https://www.youtube.com/playlist?list=PLnew",
        "",
      ),
    );
    expect(onAdded).toHaveBeenCalled();
    expect(await screen.findByText("Added to Emo Night.")).toBeInTheDocument();
  });

  it("searches the channel list and falls back to a generated cover", async () => {
    mocked.getChannelSource.mockResolvedValue({
      channel_id: "UC1",
      title: "My Channel",
    });
    mocked.listChannelPlaylists.mockResolvedValue(channelPlaylists);
    renderDialog({ lockedGenreId: 1 });
    fireEvent.click(
      screen.getByRole("button", { name: "From the Nakout channel" }),
    );

    const oldCard = (await screen.findByText("Old One")).closest(".pcard");
    const image = (oldCard as HTMLElement).querySelector("img") as HTMLElement;
    expect(image.style.backgroundImage).toContain("/cover.png");

    fireEvent.change(screen.getByLabelText("Search channel playlists"), {
      target: { value: "new" },
    });
    expect(screen.getByText("New One")).toBeInTheDocument();
    expect(screen.queryByText("Old One")).not.toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    const { onClose } = renderDialog({ lockedGenreId: 1 });
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
