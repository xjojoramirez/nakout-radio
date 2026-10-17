const CLAMP_MIN = 0;
const CLAMP_MAX = 100;

/**
 * Applies a per-track loudness offset (in dB) to the user volume.
 *
 * Missing or non-finite offsets leave the volume untouched, so tracks without
 * loudness data behave exactly as before.
 */
export function applyVolumeOffset(
  volume: number,
  offsetDb: number | null | undefined,
): number {
  if (offsetDb == null || !Number.isFinite(offsetDb) || offsetDb === 0) {
    return volume;
  }
  const scaled = volume * Math.pow(10, offsetDb / 20);
  return Math.max(CLAMP_MIN, Math.min(CLAMP_MAX, Math.round(scaled)));
}
