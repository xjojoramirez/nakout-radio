import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../../api/client";
import type { AddedPlaylist, Genre } from "../../types";
import { PlaylistsPanel } from "./PlaylistsPanel";

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
      refreshPlaylist: vi.fn(),
      deletePlaylist: vi.fn(),
      updatePlaylist: vi.fn(),
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

const iso = (msAgo: number) => new Date(Date.now() - msAgo).toISOString();

const added: AddedPlaylist[] = [
  {
    id: 11,
    genre_id: 1,
    genre_name: "Emo Night",
    youtube_playlist_id: "PLGIA_2k2o8yAAAA",
    label: "",
    track_count: 56,
    synced_at: iso(2 * 60_000),
  },
  {
    id: 12,
    genre_id: 2,
    genre_name: "NU Metal",
    youtube_playlist_id: "PLGIA_2k2o8yBBBB",
    label: "Work Drive Mix",
    track_count: 37,
    synced_at: iso(6 * 86_400_000),
  },
];

const addedTwoInEmo: AddedPlaylist[] = [
  { ...added[0], track_count: 30 },
  {
    id: 13,
    genre_id: 1,
    genre_name: "Emo Night",
    youtube_playlist_id: "PLGIA_2k2o8yCCCC",
    label: "",
    track_count: 26,
    synced_at: iso(30 * 60_000),
  },
];

afterEach(() => {
  vi.clearAllMocks();
});

function renderPanel(
  overrides: Partial<Parameters<typeof PlaylistsPanel>[0]> = {},
) {
  const onNotice = overrides.onNotice ?? vi.fn();
  const onError = overrides.onError ?? vi.fn();
  const onCountChange = overrides.onCountChange ?? vi.fn();
  const onJump = overrides.onJump ?? vi.fn();
  render(
    <PlaylistsPanel
      genres={overrides.genres ?? genres}
      onGenresChanged={overrides.onGenresChanged ?? (async () => {})}
      onNotice={onNotice}
      onError={onError}
      onCountChange={onCountChange}
      onJump={onJump}
    />,
  );
  return { onNotice, onError, onCountChange, onJump };
}

describe("PlaylistsPanel", () => {
  beforeEach(() => {
    mocked.listPlaylists.mockResolvedValue(added);
    mocked.getChannelSource.mockResolvedValue({
      channel_id: null,
      title: null,
    });
    mocked.listChannelPlaylists.mockResolvedValue([]);
  });

  it("summarises Nakout playlists and track totals across genres", async () => {
    renderPanel();
    expect(
      await screen.findByText(/2 Nakout playlists · 93 tracks across 2 genres/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Sync pulls the latest tracks from YouTube/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "+ Add Nakout playlist" }),
    ).toBeInTheDocument();
  });

  it("groups playlists under genre headers with counts and Sync all", async () => {
    renderPanel();
    const metalRow = await screen.findByRole("link", {
      name: "Work Drive Mix",
    });
    const metalGroup = metalRow.closest(".group");
    expect(metalGroup).not.toBeNull();
    const emoGroup = screen
      .getAllByRole("link", { name: "Nakout playlist" })[0]
      .closest(".group");
    expect(emoGroup).not.toBeNull();
    expect(
      within(emoGroup as HTMLElement).getByText(
        "1 Nakout playlist · 56 tracks",
      ),
    ).toBeInTheDocument();
    expect(
      within(metalGroup as HTMLElement).getByText(
        "1 Nakout playlist · 37 tracks",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: "Sync all" }).length,
    ).toBe(2);
  });

  it("shows an empty group with an Add one link and no Sync all", async () => {
    mocked.listPlaylists.mockResolvedValue([]);
    renderPanel();
    expect(
      (await screen.findAllByText("No Nakout playlists yet.")).length,
    ).toBe(2);
    expect(screen.getAllByRole("button", { name: "Add one" })).toHaveLength(2);
    expect(
      screen.queryByRole("button", { name: "Sync all" }),
    ).not.toBeInTheDocument();
  });

  it("renders per-row link, chips, sync age and actions", async () => {
    renderPanel();
    const link = await screen.findByRole("link", { name: "Work Drive Mix" });
    expect(link).toHaveAttribute(
      "href",
      "https://www.youtube.com/playlist?list=PLGIA_2k2o8yBBBB",
    );
    const rawLink = screen.getAllByRole("link", { name: "Nakout playlist" })[0];
    expect(rawLink).toHaveAttribute(
      "href",
      "https://www.youtube.com/playlist?list=PLGIA_2k2o8yAAAA",
    );
    expect(rawLink).toHaveAttribute(
      "title",
      "YouTube playlist PLGIA_2k2o8yAAAA",
    );
    expect(screen.getByText("56 tracks")).toBeInTheDocument();
    expect(screen.getByText("37 tracks")).toBeInTheDocument();
    expect(screen.getByText("Synced 2 min ago")).toBeInTheDocument();
    expect(screen.getByText("Synced 6d ago")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Sync" }).length).toBe(2);
    expect(screen.getAllByRole("button", { name: "Remove" }).length).toBe(2);
    const moveSelect = screen.getByLabelText("Genre for Work Drive Mix");
    expect(
      Array.from((moveSelect as HTMLSelectElement).options).map(
        (option) => option.text,
      ),
    ).toEqual(["Emo Night", "NU Metal"]);
  });

  it("opens the add dialog unlocked from the header and locked from a group", async () => {
    renderPanel();
    await screen.findByText("Work Drive Mix");

    fireEvent.click(
      screen.getByRole("button", { name: "+ Add Nakout playlist" }),
    );
    let dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByRole("heading", { name: "Add a Nakout playlist" }),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("radiogroup", { name: "Genre" }),
    ).toBeInTheDocument();
    fireEvent.click(
      within(dialog).getByRole("button", {
        name: "Close add playlist dialog",
      }),
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Add a Nakout playlist to Emo Night" }),
    );
    dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByRole("heading", { name: "Add to Emo Night" }),
    ).toBeInTheDocument();
    expect(
      within(dialog).queryByRole("radiogroup", { name: "Genre" }),
    ).not.toBeInTheDocument();
    expect(within(dialog).getByText("Will play in")).toBeInTheDocument();
  });

  it("moves a playlist to another genre via the row select and flashes it", async () => {
    mocked.updatePlaylist.mockResolvedValue({ status: "updated" });
    renderPanel();
    const select = await screen.findByLabelText("Genre for Work Drive Mix");
    fireEvent.change(select, { target: { value: "1" } });
    await waitFor(() =>
      expect(mocked.updatePlaylist).toHaveBeenCalledWith(12, {
        genre_id: 1,
      }),
    );
    const row = screen.getByRole("link", { name: "Work Drive Mix" }).closest(
      ".prow",
    );
    await waitFor(() =>
      expect((row as HTMLElement).className.includes("flash")).toBe(true),
    );
  });

  it("reports a move failure while still refetching the list", async () => {
    mocked.updatePlaylist.mockRejectedValue(
      new ApiError(409, "Move rejected by the server."),
    );
    const { onError } = renderPanel();
    const select = await screen.findByLabelText("Genre for Work Drive Mix");
    fireEvent.change(select, { target: { value: "1" } });
    await waitFor(() =>
      expect(mocked.updatePlaylist).toHaveBeenCalledWith(12, {
        genre_id: 1,
      }),
    );
    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith("Move rejected by the server."),
    );
    expect(mocked.listPlaylists.mock.calls.length).toBeGreaterThan(1);
  });

  it("shows a Syncing chip while a sync is in flight", async () => {
    let resolve!: (value: { id: number; synced: number }) => void;
    mocked.refreshPlaylist.mockImplementation(
      () =>
        new Promise((res) => {
          resolve = res;
        }),
    );
    renderPanel();
    fireEvent.click(
      (await screen.findAllByRole("button", { name: "Sync" }))[0],
    );
    expect(await screen.findByText("Syncing")).toBeInTheDocument();
    resolve({ id: 11, synced: 56 });
    await waitFor(() =>
      expect(mocked.refreshPlaylist).toHaveBeenCalledWith(11),
    );
    await waitFor(() =>
      expect(screen.queryByText("Syncing")).not.toBeInTheDocument(),
    );
  });

  it("search filters rows across groups and keeps an empty state for misses", async () => {
    renderPanel();
    await screen.findByText("Work Drive Mix");
    const search = screen.getByLabelText("Search Nakout playlists");
    fireEvent.change(search, { target: { value: "PLGIA_2k2o8yBBBB" } });
    expect(screen.queryByText("Nakout playlist")).not.toBeInTheDocument();
    expect(screen.getByText("Work Drive Mix")).toBeInTheDocument();
    fireEvent.change(search, { target: { value: "zzz" } });
    expect(
      screen.getByText("No Nakout playlists match “zzz”."),
    ).toBeInTheDocument();
  });

  it("surfaces a sync 502 on the error path", async () => {
    mocked.refreshPlaylist.mockRejectedValue(
      new ApiError(502, "YouTube fetch failed"),
    );
    const { onError } = renderPanel();
    await screen.findByText("Work Drive Mix");
    fireEvent.click(screen.getAllByRole("button", { name: "Sync all" })[0]);
    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith("YouTube fetch failed"),
    );
  });

  it("sync-all fans out to every playlist in the group", async () => {
    mocked.listPlaylists.mockResolvedValue(addedTwoInEmo);
    mocked.refreshPlaylist.mockResolvedValue({ id: 11, synced: 5 });
    const { onNotice } = renderPanel();
    await screen.findAllByRole("link", { name: "Nakout playlist" });
    fireEvent.click(screen.getByRole("button", { name: "Sync all" }));
    expect(onNotice).toHaveBeenCalledWith("Syncing Emo Night…");
    await waitFor(() => {
      expect(mocked.refreshPlaylist).toHaveBeenCalledWith(11);
      expect(mocked.refreshPlaylist).toHaveBeenCalledWith(13);
    });
    await waitFor(() =>
      expect(onNotice).toHaveBeenCalledWith(
        "Synced Emo Night (2 Nakout playlists, 10 tracks).",
      ),
    );
  });

  it("keeps the confirm dialog for removal", async () => {
    mocked.deletePlaylist.mockResolvedValue({ status: "deleted" });
    const { onNotice } = renderPanel();
    await screen.findByText("Work Drive Mix");
    fireEvent.click(screen.getAllByRole("button", { name: "Remove" })[1]);
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText(
        /Remove “Work Drive Mix” from NU Metal\? Its tracks stay in the Library\./,
      ),
    ).toBeInTheDocument();
    fireEvent.click(within(dialog).getByText("Cancel"));
    expect(mocked.deletePlaylist).not.toHaveBeenCalled();
    fireEvent.click(screen.getAllByRole("button", { name: "Remove" })[1]);
    fireEvent.click(
      within(await screen.findByRole("dialog")).getByText("Remove"),
    );
    await waitFor(() =>
      expect(mocked.deletePlaylist).toHaveBeenCalledWith(12),
    );
    expect(onNotice).toHaveBeenCalledWith("Nakout playlist removed.");
  });

  it("reports the count callback after load", async () => {
    const { onCountChange } = renderPanel();
    await screen.findByText("Work Drive Mix");
    await waitFor(() => expect(onCountChange).toHaveBeenCalledWith(2));
  });

  it("shows the create-a-genre empty state when there are no genres", async () => {
    mocked.listPlaylists.mockResolvedValue([]);
    const { onJump } = renderPanel({ genres: [] });
    await screen.findByText(
      /Create a genre first, then add Nakout playlists to it\./,
    );
    fireEvent.click(screen.getByRole("button", { name: "Go to Genres" }));
    expect(onJump).toHaveBeenCalledWith("genres");
  });
});
