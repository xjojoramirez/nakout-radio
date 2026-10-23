export interface Track {
  youtube_video_id: string;
  title: string;
  artist: string;
  thumbnail_url: string;
  duration_seconds: number;
  position: number;
  /** Loudness correction in dB applied to the player volume (0 = none). */
  volume_offset_db: number;
}

export interface Genre {
  id: number;
  name: string;
  slug: string;
  is_default: boolean;
  track_count: number;
  color: string;
}

export interface GenreDetail extends Genre {
  track: Track | null;
  cursor: string | null;
}

export interface CurrentGenre {
  genre: Genre | null;
  track: Track | null;
  cursor: string | null;
  source: string;
  offset_seconds: number;
  server_time: string | null;
}

export interface BroadcastNow {
  genre: Genre | null;
  track: Track | null;
  offset_seconds: number;
  server_time: string;
  source: string;
  phase: "playing" | "gap";
  next_track: Track | null;
  seconds_until_start: number | null;
  preload_lead_seconds?: number;
}

export interface QueueState {
  /** Tracks in the order the broadcast will play them. */
  tracks: Track[];
  /** Index of the on-air track, or -1 when the genre is not playing. */
  index: number;
  /** True when this genre is the one currently on air. */
  live: boolean;
  /** True when the operator has taken manual control of playback. */
  manual: boolean;
}

export interface ChannelSource {
  channel_id: string | null;
  title: string | null;
}

export interface ChannelPlaylist {
  youtube_playlist_id: string;
  title: string;
  item_count: number;
  thumbnail_url: string;
  already_added: boolean;
}

export interface ChangelogEntry {
  date: string;
  title: string;
  summary: string;
}

export interface AddedPlaylist {
  id: number;
  genre_id: number;
  genre_name: string;
  youtube_playlist_id: string;
  label: string;
  track_count: number;
  synced_at: string | null;
}

export interface ScheduleSlot {
  id: number;
  genre_id: number;
  genre_name: string;
  days_of_week: number[];
  start_time: string;
}

export interface SlotToday {
  id: number;
  genre_id: number;
  genre_name: string;
  start_time: string;
}

export interface ScheduleToday {
  current_id: number | null;
  slots: SlotToday[];
  /** Previous-day slot still running when nothing has started today. */
  carry?: SlotToday | null;
}
