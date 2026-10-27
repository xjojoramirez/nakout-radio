import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { TrackDetail } from "../types";
import { api } from "../api/client";
import { useTrackDetails } from "./useTrackDetails";

vi.mock("../api/client", () => ({
  api: { trackDetail: vi.fn() },
}));

const mocked = api as unknown as {
  trackDetail: ReturnType<typeof vi.fn>;
};

function detail(id: string, overrides: Partial<TrackDetail> = {}): TrackDetail {
  return {
    youtube_video_id: id,
    title: `Title ${id}`,
    artist: "Artist",
    album: "Album",
    album_artist: null,
    release_date: null,
    release_year: 1991,
    label: null,
    catalog_number: null,
    isrc: null,
    track_number: null,
    disc_number: null,
    genres: [],
    country: null,
    language: null,
    bpm: null,
    musical_key: null,
    cover_url: null,
    summary: null,
    story: null,
    dj_note: null,
    lyric_snippet: null,
    moods: [],
    credits: [],
    links: [],
    charts: [],
    similar: [],
    metadata_sources: [],
    ...overrides,
  };
}

beforeEach(() => {
  mocked.trackDetail.mockReset();
});

describe("useTrackDetails", () => {
  it("loads the details for the on-air track", async () => {
    mocked.trackDetail.mockResolvedValue(detail("a"));

    const { result } = renderHook(() => useTrackDetails("a"));

    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.detail?.album).toBe("Album");
    expect(mocked.trackDetail).toHaveBeenCalledWith("a");
  });

  it("reports a 404 as missing, not as an error", async () => {
    mocked.trackDetail.mockRejectedValue({ status: 404 });

    const { result } = renderHook(() => useTrackDetails("a"));

    await waitFor(() => expect(result.current.status).toBe("missing"));
    expect(result.current.detail).toBeNull();
  });

  it("reports other failures as temporarily unavailable and retries", async () => {
    mocked.trackDetail
      .mockRejectedValueOnce(new Error("network down"))
      .mockResolvedValueOnce(detail("a"));

    const { result } = renderHook(() => useTrackDetails("a"));
    await waitFor(() => expect(result.current.status).toBe("error"));

    act(() => result.current.retry());

    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(mocked.trackDetail).toHaveBeenCalledTimes(2);
  });

  it("caches a loaded track so switching back does not refetch", async () => {
    mocked.trackDetail.mockImplementation((id: string) =>
      Promise.resolve(detail(id)),
    );
    const { result, rerender } = renderHook(
      ({ id }: { id: string }) => useTrackDetails(id),
      { initialProps: { id: "a" } },
    );
    await waitFor(() => expect(result.current.status).toBe("ready"));

    rerender({ id: "b" });
    await waitFor(() =>
      expect(result.current.detail?.youtube_video_id).toBe("b"),
    );
    rerender({ id: "a" });

    expect(result.current.detail?.youtube_video_id).toBe("a");
    expect(mocked.trackDetail).toHaveBeenCalledTimes(2);
  });

  it("ignores a late response for a track that is no longer on air", async () => {
    let resolveA: (value: TrackDetail) => void = () => {};
    mocked.trackDetail.mockImplementation((id: string) =>
      id === "a"
        ? new Promise<TrackDetail>((resolve) => {
            resolveA = resolve;
          })
        : Promise.resolve(detail("b")),
    );
    const { result, rerender } = renderHook(
      ({ id }: { id: string }) => useTrackDetails(id),
      { initialProps: { id: "a" } },
    );

    rerender({ id: "b" });
    expect(result.current.detail).toBeNull();
    await waitFor(() =>
      expect(result.current.detail?.youtube_video_id).toBe("b"),
    );

    await act(async () => {
      resolveA(detail("a"));
    });

    expect(result.current.detail?.youtube_video_id).toBe("b");
  });

  it("clears when there is no track on air", async () => {
    const { result } = renderHook(() => useTrackDetails(null));

    expect(result.current.status).toBe("idle");
    expect(result.current.detail).toBeNull();
    expect(mocked.trackDetail).not.toHaveBeenCalled();
  });
});
