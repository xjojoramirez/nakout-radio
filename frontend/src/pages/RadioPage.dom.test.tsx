import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Track } from "../types";
import { api } from "../api/client";
import { RadioPage } from "./RadioPage";

vi.mock("../api/client", () => ({
  api: { now: vi.fn() },
}));

const mocked = api as unknown as { now: ReturnType<typeof vi.fn> };

function track(id: string): Track {
  return {
    youtube_video_id: id,
    title: id,
    artist: "",
    thumbnail_url: "",
    duration_seconds: 200,
    position: 0,
  };
}

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  close = vi.fn();
  constructor(_url: string) {
    FakeWebSocket.instances.push(this);
  }
}

class FakePlayer {
  opts: { videoId: string };
  loadVideoById = vi.fn();
  playVideo = vi.fn();
  pauseVideo = vi.fn();
  mute = vi.fn();
  unMute = vi.fn();
  setVolume = vi.fn();
  seekTo = vi.fn();
  getPlayerState = vi.fn(() => 1);
  getCurrentTime = vi.fn(() => 0);
  destroy = vi.fn();
  constructor(_el: string, opts: { videoId: string }) {
    this.opts = opts;
  }
}

beforeEach(() => {
  window.localStorage.clear();
  FakeWebSocket.instances = [];
  (globalThis as unknown as { WebSocket: unknown }).WebSocket = FakeWebSocket;
  (window as unknown as { YT: unknown }).YT = {
    PlayerState: { PLAYING: 1, ENDED: 8 },
    Player: FakePlayer,
  };
  mocked.now.mockResolvedValue({
    genre: {
      id: 1,
      name: "Morning",
      slug: "morning",
      is_default: true,
      track_count: 1,
    },
    track: track("live"),
    offset_seconds: 0,
    server_time: "2026-01-01T00:00:00+00:00",
    source: "schedule",
  });
});

afterEach(() => {
  vi.clearAllMocks();
  delete (globalThis as unknown as { WebSocket?: unknown }).WebSocket;
  delete (window as unknown as { YT?: unknown }).YT;
});

describe("RadioPage", () => {
  it("shows the live broadcast track and genre", async () => {
    render(<RadioPage />);
    expect(await screen.findByText("live")).toBeInTheDocument();
    expect(await screen.findByText(/Tuned: Morning/)).toBeInTheDocument();
  });

  it("starts muted and offers an Unmute control", async () => {
    render(<RadioPage />);
    expect(
      await screen.findByRole("button", { name: "Unmute" }),
    ).toBeInTheDocument();
  });

  it("toggles the mute control", async () => {
    render(<RadioPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Unmute" }));
    expect(
      await screen.findByRole("button", { name: "Mute" }),
    ).toBeInTheDocument();
  });

  it("shows the offline screen and hides controls when nothing is broadcasting", async () => {
    mocked.now.mockResolvedValue({
      genre: null,
      track: null,
      offset_seconds: 0,
      server_time: "2026-01-01T00:00:00+00:00",
      source: "none",
    });
    render(<RadioPage />);
    expect(await screen.findByText(/radio offline/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /mute/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Volume")).not.toBeInTheDocument();
    expect(screen.queryByText(/off air/i)).not.toBeInTheDocument();
  });
});
