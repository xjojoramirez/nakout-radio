import { describe, expect, it } from "vitest";
import { reorder, shuffle } from "./queue";

describe("reorder", () => {
  it("moves an item forward", () => {
    expect(reorder(["a", "b", "c", "d"], 0, 2)).toEqual(["b", "c", "a", "d"]);
  });

  it("moves an item backward", () => {
    expect(reorder(["a", "b", "c", "d"], 3, 1)).toEqual(["a", "d", "b", "c"]);
  });

  it("clamps the destination and ignores bad sources", () => {
    expect(reorder(["a", "b"], 0, 99)).toEqual(["b", "a"]);
    expect(reorder(["a", "b"], 5, 0)).toEqual(["a", "b"]);
  });
});

describe("shuffle", () => {
  it("permutes deterministically with a fixed random source", () => {
    expect(shuffle(["a", "b", "c"], () => 0)).toEqual(["b", "c", "a"]);
  });

  it("keeps every element", () => {
    const out = shuffle([1, 2, 3, 4, 5]);
    expect(out.slice().sort()).toEqual([1, 2, 3, 4, 5]);
  });
});
