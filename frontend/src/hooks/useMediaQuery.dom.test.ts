import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { useMediaQuery } from "./useMediaQuery";

type ChangeHandler = (event: { matches: boolean }) => void;

type FakeMql = {
  matches: boolean;
  listeners: ChangeHandler[];
};

const fakeTable = new Map<string, FakeMql>();

function installFakeMatchMedia() {
  const stub = (query: string): MediaQueryList => {
    const mql: FakeMql = fakeTable.get(query) ?? {
      matches: false,
      listeners: [],
    };
    fakeTable.set(query, mql);
    return {
      get matches() {
        return mql.matches;
      },
      addEventListener: (_type: string, cb: ChangeHandler) => {
        mql.listeners.push(cb);
      },
      removeEventListener: (_type: string, cb: ChangeHandler) => {
        mql.listeners = mql.listeners.filter((l) => l !== cb);
      },
    } as unknown as MediaQueryList;
  };
  (globalThis as unknown as { matchMedia: unknown }).matchMedia = stub;
}

describe("useMediaQuery (dom)", () => {
  afterEach(() => {
    fakeTable.clear();
    delete (globalThis as unknown as { matchMedia?: unknown }).matchMedia;
  });

  it("reports false for a non-matching query", () => {
    installFakeMatchMedia();
    const { result } = renderHook(() => useMediaQuery("(max-width: 600px)"));
    expect(result.current).toBe(false);
  });

  it("follows match events while mounted", () => {
    installFakeMatchMedia();
    const { result } = renderHook(() => useMediaQuery("(max-width: 600px)"));
    const mql = fakeTable.get("(max-width: 600px)")!;
    expect(mql.listeners).toHaveLength(1);
    act(() => {
      mql.matches = true;
      mql.listeners.forEach((cb) => cb({ matches: true }));
    });
    expect(result.current).toBe(true);
    act(() => {
      mql.matches = false;
      mql.listeners.forEach((cb) => cb({ matches: false }));
    });
    expect(result.current).toBe(false);
  });
});
