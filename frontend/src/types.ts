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


// --------------------------------------------------------------------------
// Track details
// --------------------------------------------------------------------------

export interface TrackChartEntry {
  chart_name: string;
  country: string;
  peak: number;
  weeks_on_chart: number | null;
  year: number | null;
  source_url: string;
}

export interface TrackCredit {
  role: string;
  name: string;
}

export interface TrackLink {
  label: string;
  url: string;
}

export interface SimilarTrack {
  youtube_video_id: string;
  title: string;
  artist: string;
}

export interface TrackDetail {
  youtube_video_id: string;
  title: string;
  artist: string;
  album: string | null;
  album_artist: string | null;
  release_date: string | null;
  release_year: number | null;
  label: string | null;
  catalog_number: string | null;
  isrc: string | null;
  track_number: number | null;
  disc_number: number | null;
  genres: string[];
  country: string | null;
  language: string | null;
  bpm: number | null;
  musical_key: string | null;
  cover_url: string | null;
  summary: string | null;
  story: string | null;
  dj_note: string | null;
  lyric_snippet: string | null;
  moods: string[];
  credits: TrackCredit[];
  links: TrackLink[];
  charts: TrackChartEntry[];
  similar: SimilarTrack[];
  metadata_sources: string[];
}

/** Lifecycle of the on-air track's details request. */
export type TrackDetailStatus =
  | "idle"
  | "loading"
  | "ready"
  | "missing"
  | "error";

export interface StudioTrackDetail extends TrackDetail {
  dj_note_public: boolean;
  sources: Record<string, Record<string, string>>;
  locked_fields: string[];
  needs_review: boolean;
  enriched_at: string | null;
  enrich_error: string | null;
  story_at: string | null;
  story_error: string | null;
  created_at: string | null;
  updated_at: string | null;
  status: "empty" | "auto" | "curated";
  completeness: number;
}

export interface TrackLibraryItem {
  youtube_video_id: string;
  title: string;
  artist: string;
  thumbnail_url: string;
  duration_seconds: number;
  album: string | null;
  release_year: number | null;
  status: "empty" | "auto" | "curated";
  completeness: number;
  genres: string[];
  needs_review: boolean;
  has_story: boolean;
  has_playlist: boolean;
}

export interface TrackLibraryPage {
  items: TrackLibraryItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface EnrichmentStatus {
  running: boolean;
  total: number;
  enriched: number;
  failed: number;
  remaining: number;
  stories: number;
  stories_failed: number;
}

export type TrackDetailInput = Omit<
  StudioTrackDetail,
  | "youtube_video_id"
  | "title"
  | "artist"
  | "similar"
  | "sources"
  | "metadata_sources"
  | "needs_review"
  | "enriched_at"
  | "enrich_error"
  | "story_at"
  | "story_error"
  | "created_at"
  | "updated_at"
  | "status"
  | "completeness"
> & { similar_video_ids: string[] };
