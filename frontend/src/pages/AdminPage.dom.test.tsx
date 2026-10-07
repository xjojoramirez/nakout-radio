import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import { AdminPage } from "./AdminPage";

vi.mock("../api/client", async () => {
  const actual =
    await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    api: {
      login: vi.fn(),
      logout: vi.fn(),
      session: vi.fn(),
      listGenres: vi.fn(),
      createGenre: vi.fn(),
      updateGenre: vi.fn(),
      deleteGenre: vi.fn(),
      createPlaylist: vi.fn(),
      listSlots: vi.fn(),
      createSlot: vi.fn(),
      updateSlot: vi.fn(),
      deleteSlot: vi.fn(),
      syncAll: vi.fn(),
      now: vi.fn(),
      getChannelSource: vi.fn(),
      setChannelSource: vi.fn(),
      listChannelPlaylists: vi.fn(),
      listPlaylists: vi.fn(),
      refreshPlaylist: vi.fn(),
      deletePlaylist: vi.fn(),
      genreTracks: vi.fn(),
      play: vi.fn(),
      playbackNext: vi.fn(),
      playbackPrev: vi.fn(),
      playbackAuto: vi.fn(),
      setGenreOrder: vi.fn(),
    },
  };
});

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

beforeEach(() => {
  mocked.session.mockRejectedValue(new ApiError(401, "not authenticated"));
  mocked.getChannelSource.mockResolvedValue({ channel_id: null, title: null });
  mocked.listChannelPlaylists.mockResolvedValue([]);
  mocked.listPlaylists.mockResolvedValue([]);
  mocked.genreTracks.mockResolvedValue([]);
  mocked.listSlots.mockResolvedValue([]);
  mocked.now.mockResolvedValue({
    genre: null,
    track: null,
    offset_seconds: 0,
    server_time: "2026-01-01T00:00:00+00:00",
    source: "none",
  });
});

afterEach(() => {
  vi.clearAllMocks();
});

async function login() {
  await screen.findByPlaceholderText("Password");
  fireEvent.change(screen.getByPlaceholderText("Password"), {
    target: { value: "pw" },
  });
  fireEvent.click(screen.getByText("Log in"));
  await screen.findByRole("tab", { name: "Genres" });
}

describe("AdminPage", () => {
  it("shows the tabs after a successful login", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listGenres.mockResolvedValue([]);
    render(<AdminPage />);
    await login();
    expect(screen.getByRole("tab", { name: "Now Playing" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Playlists" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Schedule" })).toBeInTheDocument();
  });

  it("restores the session on mount after a refresh", async () => {
    mocked.session.mockResolvedValue({ status: "ok" });
    mocked.listGenres.mockResolvedValue([]);
    render(<AdminPage />);
    expect(
      await screen.findByRole("tab", { name: "Now Playing" }),
    ).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("Password")).not.toBeInTheDocument();
  });

  it("shows the API error message on a bad login", async () => {
    mocked.login.mockRejectedValue(new ApiError(401, "invalid password"));
    render(<AdminPage />);
    fireEvent.change(await screen.findByPlaceholderText("Password"), {
      target: { value: "x" },
    });
    fireEvent.click(screen.getByText("Log in"));
    expect(await screen.findByText("invalid password")).toBeInTheDocument();
  });

  it("creates a genre and refreshes the list", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listGenres.mockResolvedValue([]);
    mocked.createGenre.mockResolvedValue({
      id: 1,
      name: "Chill",
      slug: "chill",
      is_default: false,
      track_count: 0,
    });
    render(<AdminPage />);
    await login();
    fireEvent.click(screen.getByRole("tab", { name: "Genres" }));
    fireEvent.change(screen.getByPlaceholderText("Name"), {
      target: { value: "Chill" },
    });
    fireEvent.change(screen.getByPlaceholderText("Slug"), {
      target: { value: "chill" },
    });
    fireEvent.click(screen.getByText("Add genre"));
    await waitFor(() =>
      expect(mocked.createGenre).toHaveBeenCalledWith("Chill", "chill"),
    );
    expect(mocked.listGenres).toHaveBeenCalledTimes(2);
  });

  it("edits a genre", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listGenres.mockResolvedValue([
      { id: 1, name: "Chill", slug: "chill", is_default: false, track_count: 0 },
    ]);
    mocked.updateGenre.mockResolvedValue({
      id: 1,
      name: "Chillhop",
      slug: "chillhop",
      is_default: true,
      track_count: 0,
    });
    render(<AdminPage />);
    await login();
    fireEvent.click(screen.getByRole("tab", { name: "Genres" }));
    fireEvent.click(await screen.findByText("Edit"));
    fireEvent.change(screen.getByLabelText("Edit genre name"), {
      target: { value: "Chillhop" },
    });
    fireEvent.change(screen.getByLabelText("Edit genre slug"), {
      target: { value: "chillhop" },
    });
    fireEvent.click(screen.getByLabelText("Default genre"));
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() =>
      expect(mocked.updateGenre).toHaveBeenCalledWith(1, {
        name: "Chillhop",
        slug: "chillhop",
        is_default: true,
      }),
    );
  });

  it("deletes a genre after confirmation", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listGenres.mockResolvedValue([
      { id: 1, name: "Chill", slug: "chill", is_default: false, track_count: 0 },
    ]);
    mocked.deleteGenre.mockResolvedValue({ status: "deleted" });
    render(<AdminPage />);
    await login();
    fireEvent.click(screen.getByRole("tab", { name: "Genres" }));
    fireEvent.click(await screen.findByText("Delete"));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByText("Delete"));
    await waitFor(() => expect(mocked.deleteGenre).toHaveBeenCalledWith(1));
  });

  it("logs out and returns to the login screen", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listGenres.mockResolvedValue([]);
    mocked.logout.mockResolvedValue({ status: "ok" });
    render(<AdminPage />);
    await login();
    fireEvent.click(screen.getByText("Log out"));
    await waitFor(() => expect(mocked.logout).toHaveBeenCalled());
    expect(await screen.findByText("Log in")).toBeInTheDocument();
  });

  it("adds a playlist by URL and reports the synced count", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listGenres.mockResolvedValue([
      { id: 1, name: "Chill", slug: "chill", is_default: false, track_count: 0 },
    ]);
    mocked.createPlaylist.mockResolvedValue({
      id: 9,
      youtube_playlist_id: "PL1",
      synced: 3,
      sync_error: null,
    });
    render(<AdminPage />);
    await login();
    fireEvent.click(screen.getByRole("tab", { name: "Playlists" }));
    fireEvent.change(screen.getByLabelText("Playlist genre"), {
      target: { value: "1" },
    });
    fireEvent.change(screen.getByPlaceholderText("YouTube playlist URL"), {
      target: { value: "https://www.youtube.com/playlist?list=PL1" },
    });
    fireEvent.click(screen.getByText("Add playlist"));
    await waitFor(() =>
      expect(mocked.createPlaylist).toHaveBeenCalledWith(
        1,
        "https://www.youtube.com/playlist?list=PL1",
        "",
      ),
    );
    expect(
      await screen.findByText(/Playlist synced \(3 tracks\)/),
    ).toBeInTheDocument();
  });

  it("lists added playlists with genre and track count", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listGenres.mockResolvedValue([
      { id: 1, name: "Chill", slug: "chill", is_default: false, track_count: 0 },
    ]);
    mocked.listPlaylists.mockResolvedValue([
      {
        id: 9,
        genre_id: 1,
        genre_name: "Chill",
        youtube_playlist_id: "PL1",
        label: "",
        track_count: 4,
      },
    ]);
    render(<AdminPage />);
    await login();
    fireEvent.click(screen.getByRole("tab", { name: "Playlists" }));
    expect(await screen.findByText("PL1")).toBeInTheDocument();
    expect(screen.getByText("4 tracks")).toBeInTheDocument();
  });

  it("refreshes and removes an added playlist", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listGenres.mockResolvedValue([
      { id: 1, name: "Chill", slug: "chill", is_default: false, track_count: 0 },
    ]);
    mocked.listPlaylists.mockResolvedValue([
      {
        id: 9,
        genre_id: 1,
        genre_name: "Chill",
        youtube_playlist_id: "PL1",
        label: "",
        track_count: 4,
      },
    ]);
    mocked.refreshPlaylist.mockResolvedValue({ id: 9, synced: 4 });
    mocked.deletePlaylist.mockResolvedValue({ status: "deleted" });
    render(<AdminPage />);
    await login();
    fireEvent.click(screen.getByRole("tab", { name: "Playlists" }));
    await screen.findByText("PL1");
    fireEvent.click(screen.getByText("Refresh"));
    await waitFor(() =>
      expect(mocked.refreshPlaylist).toHaveBeenCalledWith(9),
    );
    fireEvent.click(screen.getByText("Remove"));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByText("Remove"));
    await waitFor(() => expect(mocked.deletePlaylist).toHaveBeenCalledWith(9));
  });

  it("saves a channel and lists its playlists", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listGenres.mockResolvedValue([
      { id: 1, name: "Chill", slug: "chill", is_default: false, track_count: 0 },
    ]);
    mocked.getChannelSource.mockResolvedValue({ channel_id: null, title: null });
    mocked.setChannelSource.mockResolvedValue({
      channel_id: "UC1",
      title: "My Channel",
    });
    mocked.listChannelPlaylists.mockResolvedValue([
      {
        youtube_playlist_id: "PLnew",
        title: "New One",
        item_count: 5,
        thumbnail_url: "u",
        already_added: false,
      },
    ]);
    render(<AdminPage />);
    await login();
    fireEvent.click(screen.getByRole("tab", { name: "Playlists" }));
    await screen.findByPlaceholderText("@handle or channel URL");
    fireEvent.change(screen.getByPlaceholderText("@handle or channel URL"), {
      target: { value: "@me" },
    });
    fireEvent.click(screen.getByText("Save channel"));
    await waitFor(() =>
      expect(mocked.setChannelSource).toHaveBeenCalledWith("@me"),
    );
    expect(await screen.findByText("New One")).toBeInTheDocument();
    expect(await screen.findByText("(5 tracks)")).toBeInTheDocument();
  });

  it("adds a browsed playlist to the chosen genre", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listGenres.mockResolvedValue([
      { id: 1, name: "Chill", slug: "chill", is_default: false, track_count: 0 },
    ]);
    mocked.getChannelSource.mockResolvedValue({
      channel_id: "UC1",
      title: "My Channel",
    });
    mocked.listChannelPlaylists.mockResolvedValue([
      {
        youtube_playlist_id: "PLnew",
        title: "New One",
        item_count: 5,
        thumbnail_url: "u",
        already_added: false,
      },
    ]);
    mocked.createPlaylist.mockResolvedValue({
      id: 9,
      youtube_playlist_id: "PLnew",
      synced: 5,
      sync_error: null,
    });
    render(<AdminPage />);
    await login();
    fireEvent.click(screen.getByRole("tab", { name: "Playlists" }));
    await screen.findByText("New One");
    fireEvent.change(screen.getByLabelText("Genre for New One"), {
      target: { value: "1" },
    });
    fireEvent.click(screen.getByText("Add"));
    await waitFor(() =>
      expect(mocked.createPlaylist).toHaveBeenCalledWith(
        1,
        "https://www.youtube.com/playlist?list=PLnew",
        "",
      ),
    );
    expect(
      await screen.findByText(/Playlist synced \(5 tracks\)/),
    ).toBeInTheDocument();
  });

  it("adds a schedule slot and refreshes the list", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listGenres.mockResolvedValue([
      { id: 1, name: "Chill", slug: "chill", is_default: false, track_count: 0 },
    ]);
    mocked.createSlot.mockResolvedValue({});
    render(<AdminPage />);
    await login();
    fireEvent.click(screen.getByRole("tab", { name: "Schedule" }));
    fireEvent.change(screen.getByLabelText("Slot genre"), {
      target: { value: "1" },
    });
    fireEvent.click(screen.getByText("Add slot"));
    await waitFor(() =>
      expect(mocked.createSlot).toHaveBeenCalledWith({
        genre_id: 1,
        days_of_week: [0, 1, 2, 3, 4],
        start_time: "06:00",
      }),
    );
    expect(mocked.listSlots).toHaveBeenCalledTimes(2);
  });

  it("lists schedule slots with genre, days, and time", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listGenres.mockResolvedValue([
      { id: 1, name: "Chill", slug: "chill", is_default: false, track_count: 0 },
    ]);
    mocked.listSlots.mockResolvedValue([
      {
        id: 5,
        genre_id: 1,
        genre_name: "Chill",
        days_of_week: [0, 2],
        start_time: "06:00",
      },
    ]);
    render(<AdminPage />);
    await login();
    fireEvent.click(screen.getByRole("tab", { name: "Schedule" }));
    expect(await screen.findByText("Chill")).toBeInTheDocument();
    expect(screen.getByText("Mon, Wed")).toBeInTheDocument();
    expect(screen.getByText("from 06:00")).toBeInTheDocument();
  });

  it("edits a schedule slot", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listGenres.mockResolvedValue([
      { id: 1, name: "Chill", slug: "chill", is_default: false, track_count: 0 },
    ]);
    mocked.listSlots.mockResolvedValue([
      {
        id: 5,
        genre_id: 1,
        genre_name: "Chill",
        days_of_week: [0],
        start_time: "06:00",
      },
    ]);
    mocked.updateSlot.mockResolvedValue({});
    render(<AdminPage />);
    await login();
    fireEvent.click(screen.getByRole("tab", { name: "Schedule" }));
    fireEvent.click(await screen.findByText("Edit"));
    fireEvent.change(screen.getByLabelText("Edit slot start"), {
      target: { value: "08:00" },
    });
    fireEvent.click(screen.getByLabelText("Edit slot Wed"));
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() =>
      expect(mocked.updateSlot).toHaveBeenCalledWith(5, {
        genre_id: 1,
        days_of_week: [0, 2],
        start_time: "08:00",
      }),
    );
  });

  it("deletes a schedule slot after confirmation", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listGenres.mockResolvedValue([
      { id: 1, name: "Chill", slug: "chill", is_default: false, track_count: 0 },
    ]);
    mocked.listSlots.mockResolvedValue([
      {
        id: 5,
        genre_id: 1,
        genre_name: "Chill",
        days_of_week: [0],
        start_time: "06:00",
      },
    ]);
    mocked.deleteSlot.mockResolvedValue({ status: "deleted" });
    render(<AdminPage />);
    await login();
    fireEvent.click(screen.getByRole("tab", { name: "Schedule" }));
    fireEvent.click(await screen.findByText("Delete"));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByText("Delete"));
    await waitFor(() => expect(mocked.deleteSlot).toHaveBeenCalledWith(5));
  });

  it("shows a skeleton card instead of the login form while checking the session", async () => {
    mocked.session.mockReturnValue(new Promise(() => {})); // never resolves
    render(<AdminPage />);
    await waitFor(() =>
      expect(document.querySelector(".admin-skeleton-card")).toBeInTheDocument(),
    );
    expect(screen.queryByPlaceholderText("Password")).not.toBeInTheDocument();
    expect(document.querySelector('[role="tabpanel"]')).toBeNull();
  });

  it("shows panel skeletons while genres load, then the real panel", async () => {
    mocked.session.mockResolvedValue({ status: "ok" });
    let resolveGenres!: () => void;
    mocked.listGenres.mockImplementation(
      () =>
        new Promise((res) => {
          resolveGenres = () => res([]);
        }),
    );
    render(<AdminPage />);
    await screen.findByRole("tab", { name: "Now Playing" });
    expect(
      document.querySelector('[role="tabpanel"] .skeleton'),
    ).not.toBeNull();
    resolveGenres();
    await waitFor(() =>
      expect(document.querySelector('[role="tabpanel"] .skeleton')).toBeNull(),
    );
  });

  it("reaches the admin shell with empty content when the genre list fails to load", async () => {
    mocked.session.mockResolvedValue({ status: "ok" });
    mocked.listGenres.mockRejectedValue(new ApiError(500, "boom"));
    render(<AdminPage />);
    await screen.findByRole("tab", { name: "Now Playing" });
    expect(
      document.querySelector('[role="tabpanel"] .skeleton'),
    ).toBeNull();
    expect(screen.queryByText("boom")).not.toBeInTheDocument();
  });
});
