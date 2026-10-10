import { describe, expect, it } from "vitest";
import { GENRE_PALETTE } from "./palette";

describe("GENRE_PALETTE", () => {
  it("has 8 hex colours starting with the amber", () => {
    expect(GENRE_PALETTE).toHaveLength(8);
    expect(GENRE_PALETTE[0]).toBe("#f2a33a");
  });
});
