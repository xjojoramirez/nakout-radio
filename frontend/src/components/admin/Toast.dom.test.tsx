import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Toast } from "./Toast";

describe("Toast", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("renders the message with role=status", () => {
    render(<Toast message="Genre added." onDone={() => {}} />);
    expect(screen.getByRole("status")).toHaveTextContent("Genre added.");
  });

  it("auto-hides after 2.2s and calls onDone", () => {
    const onDone = vi.fn();
    render(<Toast message="Saved." onDone={onDone} />);
    act(() => {
      vi.advanceTimersByTime(2200);
    });
    expect(onDone).toHaveBeenCalled();
  });

  it("renders nothing when message is empty", () => {
    render(<Toast message="" onDone={() => {}} />);
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("restarts the timer when a new message arrives", () => {
    const onDone = vi.fn();
    const { rerender } = render(<Toast message="One" onDone={onDone} />);
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    rerender(<Toast message="Two" onDone={onDone} />);
    act(() => {
      vi.advanceTimersByTime(2500);
    });
    expect(onDone).toHaveBeenCalledTimes(1);
  });
});
