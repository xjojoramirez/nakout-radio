import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { VUMeter } from "./VUMeter";

const LEVELS = [41, 48, 55, 62, 69, 76, 83, 90, 97, 44, 51, 58];

describe("VUMeter", () => {
  it("renders the twelve reference levels while playing", () => {
    const { container } = render(<VUMeter playing />);
    const meter = container.querySelector(".vu-meter");
    expect(meter).toHaveClass("playing");
    const bars = [...container.querySelectorAll<HTMLElement>(".vu-bar")];
    expect(bars).toHaveLength(LEVELS.length);
    expect(bars.map((bar) => bar.style.height)).toEqual(
      LEVELS.map((level) => `${level}%`),
    );
  });

  it("rests every bar when playback is stopped", () => {
    const { container } = render(<VUMeter playing={false} />);
    const meter = container.querySelector(".vu-meter");
    expect(meter).not.toHaveClass("playing");
    const bars = [...container.querySelectorAll<HTMLElement>(".vu-bar")];
    expect(bars).toHaveLength(LEVELS.length);
    expect(bars.every((bar) => bar.style.height === "6%")).toBe(true);
  });
});
