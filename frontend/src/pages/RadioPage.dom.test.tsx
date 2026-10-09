import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SlotToday, Track } from "../types";
import { api } from "../api/client";
import { RadioPage } from "./RadioPage";

vi.mock("../api/client", () => ({
  api: {
    now: vi.fn(),
    scheduleToday: vi.fn(),
  },
}));

const mocked = api as unknown as {
  now: ReturnType<typeof vi.fn>;
  scheduleToday: ReturnType<typeof vi.fn>;
};

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

const slots: SlotToday[] = [
  { id: 1, genre_id: 1, genre_name: "Morning", start_time: "05:00" },
  { id: 2, genre_id: 2, genre_name: "Evening", start_time: "17:00" },
];

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

window.matchMedia =
  window.matchMedia ||
  ((query: string) =>
    ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }) as unknown as MediaQueryList);

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
  mocked.scheduleToday.mockResolvedValue({ current_id: null, slots: [] });
});

afterEach(() => {
  vi.clearAllMocks();
  delete (globalThis as unknown as { WebSocket?: unknown }).WebSocket;
  delete (window as unknown as { YT?: unknown }).YT;
});

describe("RadioPage", () => {
  it("shows the live broadcast track and genre kicker", async () => {
    render(<RadioPage />);
    expect(await screen.findByText("live")).toBeInTheDocument();
    expect(await screen.findByText("Morning · live now")).toBeInTheDocument();
  });

  it("opens with Tune in and flips to Tune out on click", async () => {
    render(<RadioPage />);
    const tune = await screen.findByRole("button", { name: "Tune in" });
    fireEvent.click(tune);
    expect(
      await screen.findByRole("button", { name: "Tune out" }),
    ).toBeInTheDocument();
  });

  it("offers a volume knob slider", async () => {
    render(<RadioPage />);
    const slider = await screen.findByRole("slider", { name: "Volume" });
    expect(slider).toHaveAttribute("aria-valuemax", "100");
  });

  it("has no next-record or stop station controls", async () => {
    render(<RadioPage />);
    await screen.findByRole("button", { name: "Tune in" });
    expect(
      screen.queryByRole("button", { name: /next record/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /stop/i }),
    ).not.toBeInTheDocument();
  });

  it("renders today's schedule and highlights the current slot", async () => {
    mocked.scheduleToday.mockResolvedValue({ current_id: 1, slots });
    render(<RadioPage />);
    expect(await screen.findByText("Evening")).toBeInTheDocument();
    expect(await screen.findByText("5 am – 5 pm")).toBeInTheDocument();
    const rows = screen.getAllByRole("listitem");
    expect(rows[0].className).toContain("now");
    expect(rows[1].className).not.toContain("now");
  });

  it("falls back gracefully when the schedule request fails", async () => {
    mocked.scheduleToday.mockRejectedValue(new Error("boom"));
    render(<RadioPage />);
    expect(await screen.findByText("live")).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("shows the offline notice with a disabled tune control", async () => {
    mocked.now.mockResolvedValue({
      genre: null,
      track: null,
      offset_seconds: 0,
      server_time: "2026-01-01T00:00:00+00:00",
      source: "none",
    });
    render(<RadioPage />);
    expect(await screen.findByText(/radio offline/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tune in" })).toBeDisabled();
    expect(screen.queryByText(/off air/i)).not.toBeInTheDocument();
  });
});
