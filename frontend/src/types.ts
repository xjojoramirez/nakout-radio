export interface Track {
  youtube_video_id: string;
  title: string;
  artist: string;
  thumbnail_url: string;
  duration_seconds: number;
  position: number;
}

export interface Genre {
  id: number;
  name: string;
  slug: string;
  is_default: boolean;
  track_count: number;
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
}

export interface BroadcastNow {
  genre: Genre | null;
  track: Track | null;
  offset_seconds: number;
  server_time: string;
  source: string;
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

export interface AddedPlaylist {
  id: number;
  genre_id: number;
  genre_name: string;
  youtube_playlist_id: string;
  label: string;
  track_count: number;
}

export interface ScheduleSlot {
  id: number;
  genre_id: number;
  genre_name: string;
  days_of_week: number[];
  start_time: string;
}
