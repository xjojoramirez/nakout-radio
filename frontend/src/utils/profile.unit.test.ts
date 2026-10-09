import { describe, expect, it } from "vitest";
import { cssCover } from "./profile";

describe("cssCover()", () => {
  it("is a data-URI CSS background for any string", () => {
    const a = cssCover("Endless Love");
    const b = cssCover("Du Hast");
    expect(a).toMatch(/^url\("data:image\/svg\+xml/);
    expect(a).not.toBe(b);
    expect(a).toBe(cssCover("Endless Love"));
  });
});
