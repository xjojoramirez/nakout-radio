import { describe, expect, it } from "vitest";
import { applyVolumeOffset } from "./loudness";

describe("applyVolumeOffset", () => {
  it("returns the volume unchanged without data", () => {
    expect(applyVolumeOffset(70, 0)).toBe(70);
    expect(applyVolumeOffset(70, null)).toBe(70);
    expect(applyVolumeOffset(70, undefined)).toBe(70);
    expect(applyVolumeOffset(70, Number.NaN)).toBe(70);
  });

  it("attenuates loud tracks", () => {
    expect(applyVolumeOffset(70, -6.02)).toBe(35);
  });

  it("boosts quiet tracks", () => {
    expect(applyVolumeOffset(40, 6.02)).toBe(80);
  });

  it("clamps at the player ceiling", () => {
    expect(applyVolumeOffset(90, 6)).toBe(100);
  });

  it("keeps silence silent", () => {
    expect(applyVolumeOffset(0, -8)).toBe(0);
  });
});
