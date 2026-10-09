import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../../api/client";
import type { AddedPlaylist, ChannelPlaylist, Genre } from "../../types";
import { PlaylistsPanel } from "./PlaylistsPanel";

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

afterEach(() => {
  vi.clearAllMocks();
});

function renderPanel(
  overrides: Partial<Parameters<typeof PlaylistsPanel>[0]> = {},
) {
  const onNotice = overrides.onNotice ?? vi.fn();
  const onError = overrides.onError ?? vi.fn();
  const onCountChange = overrides.onCountChange ?? vi.fn();
  const onIntentConsumed = overrides.onIntentConsumed ?? vi.fn();
  const onJump = overrides.onJump ?? vi.fn();
  render(
    <PlaylistsPanel
      genres={overrides.genres ?? genres}
      onGenresChanged={overrides.onGenresChanged ?? (async () => {})}
      onNotice={onNotice}
      onError={onError}
      onCountChange={onCountChange}
      initialGenre={overrides.initialGenre}
      onIntentConsumed={onIntentConsumed}
      onJump={onJump}
    />,
  );
  return { onNotice, onError, onCountChange, onIntentConsumed, onJump };
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

  it("summarises playlist and track totals across genres", async () => {
    renderPanel();
    expect(
      await screen.findByText(/2 playlists · 93 tracks across 2 genres/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Playlists are re-synced with YouTube when you refresh/),
    ).toBeInTheDocument();
  });

  it("groups playlists under genre headers with counts and Refresh all", async () => {
    renderPanel();
    const metalRow = await screen.findByRole("link", {
      name: "Work Drive Mix",
    });
    const metalGroup = metalRow.closest(".group");
    expect(metalGroup).not.toBeNull();
    const emoGroup = screen
      .getByRole("link", { name: "PLGIA_2k2o8yAAAA" })
      .closest(".group");
    expect(emoGroup).not.toBeNull();
    expect(
      within(emoGroup as HTMLElement).getByText("1 playlist · 56 tracks"),
    ).toBeInTheDocument();
    expect(
      within(metalGroup as HTMLElement).getByText("1 playlist · 37 tracks"),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: "Refresh all" }).length,
    ).toBe(2);
  });

  it("shows an empty group with an Add one link and no Refresh all", async () => {
    mocked.listPlaylists.mockResolvedValue([]);
    renderPanel();
    expect((await screen.findAllByText("No playlists yet.")).length).toBe(2);
    expect(screen.getAllByRole("button", { name: "Add one" })).toHaveLength(2);
    expect(
      screen.queryByRole("button", { name: "Refresh all" }),
    ).not.toBeInTheDocument();
  });

  it("renders per-row link, chips, sync age and actions", async () => {
    renderPanel();
    const link = await screen.findByRole("link", { name: "Work Drive Mix" });
    expect(link).toHaveAttribute(
      "href",
      "https://www.youtube.com/playlist?list=PLGIA_2k2o8yBBBB",
    );
    const rawLink = screen.getByRole("link", { name: "PLGIA_2k2o8yAAAA" });
    expect(rawLink).toHaveAttribute(
      "href",
      "https://www.youtube.com/playlist?list=PLGIA_2k2o8yAAAA",
    );
    expect(screen.getByText("56 tracks")).toBeInTheDocument();
    expect(screen.getByText("37 tracks")).toBeInTheDocument();
    expect(screen.getByText("Synced 2 min ago")).toBeInTheDocument();
    expect(screen.getByText("Synced 6d ago")).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: "Refresh" }).length,
    ).toBe(2);
    expect(screen.getAllByRole("button", { name: "Remove" }).length).toBe(2);
    const moveSelect = screen.getByLabelText("Genre for Work Drive Mix");
    expect(
      Array.from((moveSelect as HTMLSelectElement).options).map(
        (o) => o.text,
      ),
    ).toEqual(["Emo Night", "NU Metal"]);
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

  it("shows a Syncing chip while a refresh is in flight", async () => {
    let resolve!: (value: { id: number; synced: number }) => void;
    mocked.refreshPlaylist.mockImplementation(
      () =>
        new Promise((res) => {
          resolve = res;
        }),
    );
    renderPanel();
    fireEvent.click(
      (await screen.findAllByRole("button", { name: "Refresh" }))[0],
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
    const search = screen.getByLabelText("Search playlists");
    fireEvent.change(search, { target: { value: "PLGIA_2k2o8yBBBB" } });
    expect(screen.queryByText("PLGIA_2k2o8yAAAA")).not.toBeInTheDocument();
    expect(screen.getByText("Work Drive Mix")).toBeInTheDocument();
    fireEvent.change(search, { target: { value: "zzz" } });
    expect(screen.getByText('No playlists match "zzz".')).toBeInTheDocument();
  });

  it("offers a segmented control between link and channel modes", async () => {
    renderPanel();
    await screen.findByText("56 tracks");
    const linkBtn = screen.getByRole("button", { name: "Paste a link" });
    const channelBtn = screen.getByRole("button", {
      name: "From your channel",
    });
    expect(linkBtn).toHaveAttribute("aria-pressed", "true");
    expect(channelBtn).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByLabelText("YouTube playlist link")).toBeInTheDocument();
    fireEvent.click(channelBtn);
    expect(channelBtn).toHaveAttribute("aria-pressed", "true");
    expect(linkBtn).toHaveAttribute("aria-pressed", "false");
    expect(
      screen.queryByLabelText("YouTube playlist link"),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText("YouTube channel")).toBeInTheDocument();
    fireEvent.click(linkBtn);
    expect(screen.getByLabelText("YouTube playlist link")).toBeInTheDocument();
  });

  it("hints a valid link, an invalid link and a duplicate", async () => {
    renderPanel();
    await screen.findByText("56 tracks");
    const input = screen.getByLabelText("YouTube playlist link");
    const hintOf = () =>
      (input.closest(".addlink") as HTMLElement).querySelector(
        ".hint",
      ) as HTMLElement;
    fireEvent.change(input, {
      target: { value: "https://www.youtube.com/playlist?list=PLnew" },
    });
    expect(hintOf().className).toBe("hint ok");
    expect(hintOf().textContent).toBe("Playlist ID found: PLnew");
    fireEvent.change(input, { target: { value: "not a link" } });
    expect(hintOf().className).toBe("hint err");
    fireEvent.change(input, {
      target: {
        value: "https://www.youtube.com/playlist?list=PLGIA_2k2o8yAAAA",
      },
    });
    expect(hintOf().className).toBe("hint err");
    expect(hintOf().textContent).toBe(
      "This playlist is already added under Emo Night.",
    );
    expect(screen.getByRole("button", { name: "Add playlist" })).toBeDisabled();
  });

  it("adds a playlist from a genre chip selection", async () => {
    mocked.createPlaylist.mockResolvedValue({
      id: 30,
      youtube_playlist_id: "PLnew",
      synced: 7,
      sync_error: null,
    });
    const { onNotice } = renderPanel();
    await screen.findByText("56 tracks");
    const add = screen.getByRole("button", { name: "Add playlist" });
    fireEvent.change(screen.getByLabelText("YouTube playlist link"), {
      target: { value: "https://www.youtube.com/playlist?list=PLnew" },
    });
    expect(add).toBeDisabled();
    const radioGroup = screen.getByRole("radiogroup", { name: "Genre" });
    fireEvent.click(
      within(radioGroup).getByRole("radio", { name: "Emo Night" }),
    );
    expect(add).toBeEnabled();
    fireEvent.click(add);
    await waitFor(() =>
      expect(mocked.createPlaylist).toHaveBeenCalledWith(
        1,
        "https://www.youtube.com/playlist?list=PLnew",
        "",
      ),
    );
    expect(onNotice).toHaveBeenCalledWith("Playlist synced (7 tracks).");
  });

  it("surfaces a create failure on the error path", async () => {
    mocked.createPlaylist.mockRejectedValue(
      new ApiError(400, "That doesn't look like a playlist link."),
    );
    const { onError } = renderPanel();
    await screen.findByText("56 tracks");
    fireEvent.change(screen.getByLabelText("YouTube playlist link"), {
      target: { value: "https://www.youtube.com/playlist?list=PLnew" },
    });
    const radioGroup = screen.getByRole("radiogroup", { name: "Genre" });
    fireEvent.click(
      within(radioGroup).getByRole("radio", { name: "Emo Night" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Add playlist" }));
    await waitFor(() => expect(mocked.createPlaylist).toHaveBeenCalled());
    expect(onError).toHaveBeenCalledWith(
      "That doesn't look like a playlist link.",
    );
  });

  it("surfaces a refresh 502 on the error path", async () => {
    mocked.refreshPlaylist.mockRejectedValue(
      new ApiError(502, "YouTube fetch failed"),
    );
    const { onError } = renderPanel();
    await screen.findByText("Work Drive Mix");
    fireEvent.click(screen.getAllByRole("button", { name: "Refresh all" })[0]);
    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith("YouTube fetch failed"),
    );
  });

  it("saves a channel and browses its playlists as cards", async () => {
    mocked.setChannelSource.mockResolvedValue({
      channel_id: "UC1",
      title: "My Channel",
    });
    mocked.listChannelPlaylists.mockResolvedValue(channelPlaylists);
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "From your channel" }));
    fireEvent.change(screen.getByLabelText("YouTube channel"), {
      target: { value: "@me" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save channel" }));
    await waitFor(() =>
      expect(mocked.setChannelSource).toHaveBeenCalledWith("@me"),
    );
    const pcard = (await screen.findByText("New One")).closest(".pcard");
    expect(pcard).not.toBeNull();
    expect((pcard as HTMLElement).querySelector("img")).toHaveAttribute(
      "src",
      "u",
    );
    expect(within(pcard as HTMLElement).getByText("5 tracks")).toBeInTheDocument();
    const oldCard = screen.getByText("Old One").closest(".pcard");
    expect(
      within(oldCard as HTMLElement).getByText("Emo Night"),
    ).toBeInTheDocument();
    expect(
      (oldCard as HTMLElement).querySelector("select"),
    ).toBeNull();
    expect(
      within(pcard as HTMLElement).getByLabelText("Genre for New One"),
    ).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Change" }));
    expect(screen.getByLabelText("YouTube channel")).toBeInTheDocument();
  });

  it("reloads the channel list on its Refresh button", async () => {
    mocked.getChannelSource.mockResolvedValue({
      channel_id: "UC1",
      title: "My Channel",
    });
    mocked.listChannelPlaylists.mockResolvedValue(channelPlaylists);
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "From your channel" }));
    await screen.findByText("New One");
    fireEvent.click(screen.getByRole("button", { name: "Refresh list" }));
    await waitFor(() => {
      expect(mocked.getChannelSource).toHaveBeenCalledTimes(2);
      expect(mocked.listChannelPlaylists).toHaveBeenCalledTimes(2);
    });
  });

  it("adds a browsed channel playlist to the chosen genre", async () => {
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
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "From your channel" }));
    fireEvent.change(await screen.findByLabelText("Genre for New One"), {
      target: { value: "2" },
    });
    fireEvent.click(
      within(screen.getByText("New One").closest(".pcard") as HTMLElement).getByRole(
        "button",
        { name: "Add" },
      ),
    );
    await waitFor(() =>
      expect(mocked.createPlaylist).toHaveBeenCalledWith(
        2,
        "https://www.youtube.com/playlist?list=PLnew",
        "",
      ),
    );
  });

  it("falls back to a generated cover when a thumbnail is missing", async () => {
    mocked.getChannelSource.mockResolvedValue({
      channel_id: "UC1",
      title: "My Channel",
    });
    mocked.listChannelPlaylists.mockResolvedValue(channelPlaylists);
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "From your channel" }));
    const oldCard = (await screen.findByText("Old One")).closest(".pcard");
    const img = (oldCard as HTMLElement).querySelector("img") as HTMLElement;
    expect(img.style.backgroundImage).toContain("/cover.png");
  });

  it("consumes the initialGenre intent once on mount", async () => {
    const { onIntentConsumed } = renderPanel({ initialGenre: 2 });
    const radioGroup = screen.getByRole("radiogroup", { name: "Genre" });
    const chip = within(radioGroup).getByRole("radio", { name: "NU Metal" });
    await waitFor(() => expect(chip).toHaveAttribute("aria-checked", "true"));
    expect(screen.getByLabelText("YouTube playlist link")).toBeInTheDocument();
    expect(onIntentConsumed).toHaveBeenCalledTimes(1);
  });

  it("refresh-all fans out to every playlist in the group", async () => {
    mocked.listPlaylists.mockResolvedValue(addedTwoInEmo);
    mocked.refreshPlaylist.mockResolvedValue({ id: 11, synced: 5 });
    const { onNotice } = renderPanel();
    await screen.findByText("PLGIA_2k2o8yCCCC");
    fireEvent.click(screen.getByRole("button", { name: "Refresh all" }));
    expect(onNotice).toHaveBeenCalledWith("Refreshing Emo Night...");
    await waitFor(() => {
      expect(mocked.refreshPlaylist).toHaveBeenCalledWith(11);
      expect(mocked.refreshPlaylist).toHaveBeenCalledWith(13);
    });
    await waitFor(() =>
      expect(onNotice).toHaveBeenCalledWith(
        "Refreshed Emo Night (2 playlists, 10 tracks).",
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
      within(dialog).getByText(/Remove "Work Drive Mix" and its tracks/),
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
    expect(onNotice).toHaveBeenCalledWith("Playlist removed.");
  });

  it("reports the count callback after load", async () => {
    const { onCountChange } = renderPanel();
    await screen.findByText("Work Drive Mix");
    await waitFor(() => expect(onCountChange).toHaveBeenCalledWith(2));
  });

  it("shows the create-a-genre empty state when there are no genres", async () => {
    mocked.listPlaylists.mockResolvedValue([]);
    const { onJump } = renderPanel({ genres: [] });
    await screen.findByText(/Create a genre first, then add playlists to it\./);
    fireEvent.click(screen.getByRole("button", { name: "Go to Genres" }));
    expect(onJump).toHaveBeenCalledWith("genres");
  });
});
