import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../../api/client";
import { ChangelogDialog } from "./ChangelogDialog";

vi.mock("../../api/client", async () => {
  const actual =
    await vi.importActual<typeof import("../../api/client")>(
      "../../api/client",
    );
  return {
    ...actual,
    api: {
      ...actual.api,
      changelog: vi.fn(),
    },
  };
});

const mocked = api as unknown as {
  changelog: ReturnType<typeof vi.fn>;
};

beforeEach(() => {
  mocked.changelog.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("ChangelogDialog", () => {
  it("loads and displays the latest changes", async () => {
    mocked.changelog.mockResolvedValue([
      {
        date: "2026-10-23",
        title: "Newest change",
        summary: "What changed.",
      },
    ]);

    render(<ChangelogDialog onClose={() => {}} />);

    expect(
      screen.getByRole("dialog", { name: "Changelog" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Newest change")).toBeInTheDocument();
    expect(screen.getByText("Oct 23, 2026")).toBeInTheDocument();
    expect(screen.getByText("What changed.")).toBeInTheDocument();
    expect(mocked.changelog).toHaveBeenCalledWith();
  });

  it("shows an empty state when there are no changes", async () => {
    mocked.changelog.mockResolvedValue([]);

    render(<ChangelogDialog onClose={() => {}} />);

    expect(await screen.findByText("No changes yet.")).toBeInTheDocument();
  });

  it("shows an error and retries the request", async () => {
    mocked.changelog
      .mockRejectedValueOnce(new ApiError(503, "Changelog unavailable"))
      .mockResolvedValueOnce([
        {
          date: "2026-10-22",
          title: "Recovered",
          summary: "It works now.",
        },
      ]);

    render(<ChangelogDialog onClose={() => {}} />);

    expect(await screen.findByText("Changelog unavailable")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Recovered")).toBeInTheDocument();
    expect(mocked.changelog).toHaveBeenCalledTimes(2);
  });

  it("closes with the close button", async () => {
    mocked.changelog.mockResolvedValue([]);
    const onClose = vi.fn();

    render(<ChangelogDialog onClose={onClose} />);
    await screen.findByText("No changes yet.");
    fireEvent.click(screen.getByRole("button", { name: "Close changelog" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes with Escape", async () => {
    mocked.changelog.mockResolvedValue([]);
    const onClose = vi.fn();

    render(<ChangelogDialog onClose={onClose} />);
    await screen.findByText("No changes yet.");
    fireEvent.keyDown(window, { key: "Escape" });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes when the backdrop is clicked", async () => {
    mocked.changelog.mockResolvedValue([]);
    const onClose = vi.fn();

    render(<ChangelogDialog onClose={onClose} />);
    await screen.findByText("No changes yet.");
    const overlay = screen.getByRole("dialog").parentElement;
    expect(overlay).not.toBeNull();
    fireEvent.mouseDown(overlay as HTMLElement);

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("restores focus to the element that opened it", async () => {
    mocked.changelog.mockResolvedValue([]);
    const trigger = document.createElement("button");
    trigger.textContent = "Open changelog";
    document.body.appendChild(trigger);
    trigger.focus();

    const { unmount } = render(<ChangelogDialog onClose={() => {}} />);
    await screen.findByText("No changes yet.");
    expect(screen.getByRole("button", { name: "Close changelog" })).toHaveFocus();

    unmount();
    expect(trigger).toHaveFocus();
    trigger.remove();
  });
});
