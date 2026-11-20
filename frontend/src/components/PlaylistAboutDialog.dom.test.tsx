import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import type { GenreDetail } from "../types";
import { PlaylistAboutDialog } from "./PlaylistAboutDialog";

vi.mock("../api/client", async () => {
  const actual =
    await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    api: { ...actual.api, getGenre: vi.fn() },
  };
});

const mocked = api as unknown as {
  getGenre: ReturnType<typeof vi.fn>;
};

const detail: GenreDetail = {
  id: 1,
  name: "Emo Night",
  slug: "EN",
  is_default: false,
  color: "#f2a33a",
  description: "Heartbreak anthems for the drive home.",
  track_count: 12,
  track: null,
  cursor: null,
  top_artists: ["Paramore", "Taking Back Sunday", "Jimmy Eat World"],
};

afterEach(() => {
  vi.clearAllMocks();
});

describe("PlaylistAboutDialog", () => {
  it("shows the playlist description and top artists without tracks", async () => {
    mocked.getGenre.mockResolvedValue(detail);
    render(<PlaylistAboutDialog slug="EN" onClose={vi.fn()} />);
    expect(await screen.findByText("Emo Night")).toBeInTheDocument();
    expect(
      screen.getByText("Heartbreak anthems for the drive home."),
    ).toBeInTheDocument();
    expect(screen.getByText("Paramore")).toBeInTheDocument();
    expect(screen.getByText("Taking Back Sunday")).toBeInTheDocument();
    expect(
      screen.getByText("Top artists in this playlist"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Track list")).not.toBeInTheDocument();
  });

  it("shows the empty description state and hides empty artists", async () => {
    mocked.getGenre.mockResolvedValue({
      ...detail,
      description: "",
      top_artists: [],
    });
    render(<PlaylistAboutDialog slug="EN" onClose={vi.fn()} />);
    expect(await screen.findByText("No description yet.")).toBeInTheDocument();
    expect(
      screen.queryByText("Top artists in this playlist"),
    ).not.toBeInTheDocument();
  });

  it("closes with Escape, the overlay and the Close button", async () => {
    mocked.getGenre.mockResolvedValue(detail);
    const onClose = vi.fn();
    render(<PlaylistAboutDialog slug="EN" onClose={onClose} />);
    await screen.findByText("Emo Night");

    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);

    const overlay = document.querySelector(".modal-overlay");
    if (!overlay) throw new Error("overlay not rendered");
    fireEvent.mouseDown(overlay);
    expect(onClose).toHaveBeenCalledTimes(2);

    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it("shows the request error and retries", async () => {
    mocked.getGenre
      .mockRejectedValueOnce(new ApiError(500, "boom"))
      .mockResolvedValueOnce(detail);
    render(<PlaylistAboutDialog slug="EN" onClose={vi.fn()} />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("boom");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(mocked.getGenre).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("Paramore")).toBeInTheDocument();
  });
});
