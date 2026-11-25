/** Extracts the playlist id from a YouTube playlist URL or a bare id. */
export function parsePlaylistId(value: string): string | null {
  const match =
    value.match(/[?&]list=([\w-]+)/) ?? value.match(/^(PL[\w-]{6,})$/);
  return match ? match[1] : null;
}
