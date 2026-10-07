import type {
  AddedPlaylist,
  BroadcastNow,
  ChannelPlaylist,
  ChannelSource,
  CurrentGenre,
  Genre,
  GenreDetail,
  ScheduleSlot,
  Track,
} from "../types";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const resp = await fetch(`/api${path}`, {
    ...init,
    credentials: "include",
    headers,
  });

  if (!resp.ok) {
    let detail = `Request failed: ${resp.status}`;
    try {
      const body = (await resp.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      // non-JSON error body; keep the default detail
    }
    throw new ApiError(resp.status, detail);
  }

  return (await resp.json()) as T;
}

export const api = {
  listGenres: () => request<Genre[]>("/genres"),
  getGenre: (slug: string) => request<GenreDetail>(`/genres/${slug}`),
  scheduleNow: () => request<CurrentGenre>("/schedule/now"),
  now: () => request<BroadcastNow>("/now"),
  advance: (cursor: string, direction: "next" | "prev" | "random") =>
    request<{ track: Track | null; cursor: string }>("/queue/advance", {
      method: "POST",
      body: JSON.stringify({ cursor, direction }),
    }),
  login: (password: string) =>
    request<{ status: string }>("/admin/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),
  logout: () => request<{ status: string }>("/admin/logout", { method: "POST" }),
  session: () => request<{ status: string }>("/admin/session"),
  genreTracks: (genreId: number) =>
    request<Track[]>(`/admin/genres/${genreId}/tracks`),
  play: (genreId: number, youtubeVideoId: string) =>
    request<{ status: string }>("/admin/playback/play", {
      method: "POST",
      body: JSON.stringify({
        genre_id: genreId,
        youtube_video_id: youtubeVideoId,
      }),
    }),
  playbackNext: (genreId: number) =>
    request<{ status: string }>("/admin/playback/next", {
      method: "POST",
      body: JSON.stringify({ genre_id: genreId }),
    }),
  playbackPrev: (genreId: number) =>
    request<{ status: string }>("/admin/playback/prev", {
      method: "POST",
      body: JSON.stringify({ genre_id: genreId }),
    }),
  playbackAuto: () =>
    request<{ status: string }>("/admin/playback/auto", { method: "POST" }),
  setGenreOrder: (genreId: number, videoIds: string[]) =>
    request<{ status: string }>(`/admin/genres/${genreId}/order`, {
      method: "PUT",
      body: JSON.stringify({ video_ids: videoIds }),
    }),
  syncAll: () =>
    request<{ results: { id: number; synced: number; error: string | null }[] }>(
      "/admin/sync",
      { method: "POST" },
    ),
  getChannelSource: () => request<ChannelSource>("/admin/youtube/channel"),
  setChannelSource: (channel: string) =>
    request<ChannelSource>("/admin/youtube/channel", {
      method: "PUT",
      body: JSON.stringify({ channel }),
    }),
  listChannelPlaylists: () =>
    request<ChannelPlaylist[]>("/admin/youtube/playlists"),
  createGenre: (name: string, slug: string) =>
    request<Genre>("/admin/genres", {
      method: "POST",
      body: JSON.stringify({ name, slug }),
    }),
  updateGenre: (
    id: number,
    updates: Partial<Pick<Genre, "name" | "slug" | "is_default">>,
  ) =>
    request<Genre>(`/admin/genres/${id}`, {
      method: "PUT",
      body: JSON.stringify(updates),
    }),
  deleteGenre: (id: number) =>
    request<{ status: string }>(`/admin/genres/${id}`, { method: "DELETE" }),
  createPlaylist: (genreId: number, url: string, label: string) =>
    request<{
      id: number;
      youtube_playlist_id: string;
      synced: number;
      sync_error: string | null;
    }>("/admin/playlists", {
      method: "POST",
      body: JSON.stringify({
        genre_id: genreId,
        youtube_playlist_url: url,
        label,
      }),
    }),
  listPlaylists: () => request<AddedPlaylist[]>("/admin/playlists"),
  refreshPlaylist: (id: number) =>
    request<{ id: number; synced: number }>(
      `/admin/playlists/${id}/refresh`,
      { method: "POST" },
    ),
  deletePlaylist: (id: number) =>
    request<{ status: string }>(`/admin/playlists/${id}`, { method: "DELETE" }),
  listSlots: () => request<ScheduleSlot[]>("/admin/slots"),
  createSlot: (slot: {
    genre_id: number;
    days_of_week: number[];
    start_time: string;
  }) =>
    request<ScheduleSlot>("/admin/slots", {
      method: "POST",
      body: JSON.stringify(slot),
    }),
  updateSlot: (
    id: number,
    updates: Partial<{
      genre_id: number;
      days_of_week: number[];
      start_time: string;
    }>,
  ) =>
    request<ScheduleSlot>(`/admin/slots/${id}`, {
      method: "PUT",
      body: JSON.stringify(updates),
    }),
  deleteSlot: (id: number) =>
    request<{ status: string }>(`/admin/slots/${id}`, { method: "DELETE" }),
};
