import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./client";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("api client", () => {
  it("does not set Content-Type on GET requests", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));
    await api.listGenres();
    const headers = spy.mock.calls[0][1]?.headers as Headers;
    expect(headers.has("Content-Type")).toBe(false);
  });

  it("sets Content-Type when a body is present", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
      );
    await api.login("pw");
    const headers = spy.mock.calls[0][1]?.headers as Headers;
    expect(headers.get("Content-Type")).toBe("application/json");
  });

  it("throws ApiError carrying the backend detail", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "invalid password" }), {
        status: 401,
      }),
    );
    await expect(api.login("nope")).rejects.toMatchObject({
      status: 401,
      message: "invalid password",
    });
  });

  it("GETs the saved channel source", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ channel_id: "UC1", title: "Mine" }), {
        status: 200,
      }),
    );
    const result = await api.getChannelSource();
    expect(spy.mock.calls[0][0]).toBe("/api/studio/youtube/channel");
    expect(result).toEqual({ channel_id: "UC1", title: "Mine" });
  });

  it("PUTs the channel as JSON", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ channel_id: "UC1", title: "Mine" }), {
        status: 200,
      }),
    );
    await api.setChannelSource("@me");
    const [url, init] = spy.mock.calls[0];
    expect(url).toBe("/api/studio/youtube/channel");
    expect(init?.method).toBe("PUT");
    expect(init?.body).toBe(JSON.stringify({ channel: "@me" }));
  });

  it("GETs channel playlists", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 }),
    );
    await api.listChannelPlaylists();
    expect(spy.mock.calls[0][0]).toBe("/api/studio/youtube/playlists");
  });

  it("GETs added playlists", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));
    await api.listPlaylists();
    expect(spy.mock.calls[0][0]).toBe("/api/studio/playlists");
  });

  it("POSTs a playlist refresh", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: 3, synced: 2 }), { status: 200 }),
    );
    await api.refreshPlaylist(3);
    const [url, init] = spy.mock.calls[0];
    expect(url).toBe("/api/studio/playlists/3/refresh");
    expect(init?.method).toBe("POST");
  });

  it("DELETEs a playlist", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ status: "deleted" }), { status: 200 }),
    );
    await api.deletePlaylist(3);
    const [url, init] = spy.mock.calls[0];
    expect(url).toBe("/api/studio/playlists/3");
    expect(init?.method).toBe("DELETE");
  });

  it("GETs the admin session status", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
      );
    const result = await api.session();
    expect(spy.mock.calls[0][0]).toBe("/api/studio/session");
    expect(result).toEqual({ status: "ok" });
  });

  it("GETs the live broadcast", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(
          JSON.stringify({
            genre: null,
            track: null,
            offset_seconds: 0,
            server_time: "2026-01-01T00:00:00+00:00",
            source: "none",
          }),
          { status: 200 },
        ),
      );
    const result = await api.now();
    expect(spy.mock.calls[0][0]).toBe("/api/now");
    expect(result.source).toBe("none");
  });

  it("PUTs a genre order", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
      );
    await api.setGenreOrder(3, ["a", "b"]);
    const [url, init] = spy.mock.calls[0];
    expect(url).toBe("/api/studio/genres/3/order");
    expect(init?.method).toBe("PUT");
    expect(init?.body).toBe(JSON.stringify({ video_ids: ["a", "b"] }));
  });

  it("POSTs a play-now request", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
      );
    await api.play(3, "vid");
    const [url, init] = spy.mock.calls[0];
    expect(url).toBe("/api/studio/playback/play");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(
      JSON.stringify({ genre_id: 3, youtube_video_id: "vid" }),
    );
  });

  it("POSTs next and prev", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(() =>
        Promise.resolve(
          new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
        ),
      );
    await api.playbackNext(3);
    await api.playbackPrev(3);
    expect(spy.mock.calls[0][0]).toBe("/api/studio/playback/next");
    expect(spy.mock.calls[1][0]).toBe("/api/studio/playback/prev");
  });

  it("GETs a genre's ordered tracks", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));
    await api.genreTracks(3);
    expect(spy.mock.calls[0][0]).toBe("/api/studio/genres/3/tracks");
  });
});
