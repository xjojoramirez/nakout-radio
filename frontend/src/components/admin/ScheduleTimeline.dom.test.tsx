import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ScheduleTimeline } from "./ScheduleTimeline";
import type { ScheduleSlot } from "../../types";

const slots: ScheduleSlot[] = [
  {
    id: 1,
    genre_id: 1,
    genre_name: "Emo Night",
    days_of_week: [0, 1, 2, 3, 4],
    start_time: "06:00",
  },
  {
    id: 2,
    genre_id: 2,
    genre_name: "NU Metal",
    days_of_week: [0, 1, 2, 3, 4],
    start_time: "09:30",
  },
];

const colours = new Map([
  [1, "#f2a33a"],
  [2, "#e0654a"],
]);

function renderTimeline(
  overrides: Partial<Parameters<typeof ScheduleTimeline>[0]> = {},
) {
  const onOpenSlot = overrides.onOpenSlot ?? vi.fn();
  const onOpenNew = overrides.onOpenNew ?? vi.fn();
  const utils = render(
    <ScheduleTimeline
      day={overrides.day ?? 0}
      slots={overrides.slots ?? slots}
      colours={overrides.colours ?? colours}
      nowMinutes={
        overrides.nowMinutes !== undefined ? overrides.nowMinutes : 300
      }
      onOpenSlot={onOpenSlot}
      onOpenNew={onOpenNew}
    />,
  );
  return { onOpenSlot, onOpenNew, ...utils };
}

function mockStripRect(tl: Element) {
  Object.defineProperty(tl, "getBoundingClientRect", {
    value: () => ({
      left: 0,
      width: 1440,
      top: 0,
      right: 1440,
      bottom: 66,
      height: 66,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    }),
    configurable: true,
  });
}

describe("ScheduleTimeline", () => {
  it("renders slot blocks with the genre colour and 12h labels", () => {
    renderTimeline();
    const emo = screen.getByRole("button", { name: /Emo Night/ });
    expect(emo.style.getPropertyValue("--gc")).toBe("#f2a33a");
    expect(emo.style.left).toContain("%");
    expect(emo.style.width).toContain("%");
    expect(screen.getByText("6:00 AM")).toBeInTheDocument();
    expect(screen.getByText("9:30 AM")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /NU Metal/ })).toBeInTheDocument();
  });

  it("labels the strip for the selected weekday and carries the previous day's last slot over", () => {
    const { container } = renderTimeline({
      day: 0,
      slots: [
        {
          id: 7,
          genre_id: 2,
          genre_name: "NU Metal",
          days_of_week: [6],
          start_time: "22:00",
        },
      ],
      nowMinutes: null,
    });
    expect(
      screen.getByLabelText("Timeline for Monday"),
    ).toBeInTheDocument();
    const carry = container.querySelector<HTMLElement>(".blk.carry");
    expect(carry).not.toBeNull();
    expect(carry?.textContent).toContain("NU Metal");
    expect(carry?.textContent).toContain("continues");
  });

  it("renders a nothing-scheduled gap before the first slot", () => {
    const { container } = renderTimeline({
      slots: [
        {
          id: 3,
          genre_id: 1,
          genre_name: "Emo Night",
          days_of_week: [0],
          start_time: "12:00",
        },
      ],
      nowMinutes: null,
    });
    const gap = container.querySelector<HTMLElement>(".blk.none");
    expect(gap).not.toBeNull();
    expect(gap?.textContent).toContain("Nothing scheduled");
    expect(gap?.style.width).toBe("50%");
  });

  it("clicking an empty strip opens the add form at the rounded minute", () => {
    const { onOpenNew, container } = renderTimeline({
      slots: [
        {
          id: 3,
          genre_id: 1,
          genre_name: "Emo Night",
          days_of_week: [0],
          start_time: "12:00",
        },
      ],
      nowMinutes: null,
    });
    const tl = container.querySelector(".tl") as HTMLElement;
    mockStripRect(tl);
    fireEvent.click(tl, { clientX: 361, clientY: 20 });
    expect(onOpenNew).toHaveBeenCalledWith(360);
  });

  it("clicking a slot block opens it for edit and never opens the add form", () => {
    const { onOpenSlot, onOpenNew } = renderTimeline({ nowMinutes: null });
    fireEvent.click(screen.getByRole("button", { name: /Emo Night/ }));
    expect(onOpenSlot).toHaveBeenCalledWith(1);
    expect(onOpenNew).not.toHaveBeenCalled();
  });

  it("ignores strip clicks when the strip has no measurable width", () => {
    const { onOpenNew, container } = renderTimeline({
      slots: [],
      nowMinutes: null,
    });
    const tl = container.querySelector(".tl") as HTMLElement;
    // jsdom's default getBoundingClientRect is a zero rect
    fireEvent.click(tl, { clientX: 361, clientY: 20 });
    expect(onOpenNew).not.toHaveBeenCalled();
  });

  it("clamps strip clicks to the 0..1410 minute range", () => {
    const { onOpenNew, container } = renderTimeline({
      slots: [],
      nowMinutes: null,
    });
    const tl = container.querySelector(".tl") as HTMLElement;
    mockStripRect(tl);
    fireEvent.click(tl, { clientX: 1441, clientY: 20 });
    expect(onOpenNew).toHaveBeenLastCalledWith(1410);
  });

  it("shows the Now marker only when nowMinutes is a number", () => {
    const withNow = renderTimeline({ nowMinutes: 300 });
    expect(withNow.container.querySelector(".nowl")).not.toBeNull();
    expect(withNow.container.querySelector(".nowl")?.textContent).toContain(
      "Now",
    );
    withNow.unmount();
    const withoutNow = renderTimeline({ nowMinutes: null });
    expect(withoutNow.container.querySelector(".nowl")).toBeNull();
  });

  it("renders 3-hour ticks from 12 AM to 12 AM with no Midnight label", () => {
    const { container } = renderTimeline();
    const ticks = container.querySelector(".ticks") as HTMLElement;
    const labels = Array.from(ticks.querySelectorAll("span")).map(
      (s) => s.textContent,
    );
    expect(labels[0]).toBe("12 AM");
    expect(labels[labels.length - 1]).toBe("12 AM");
    expect(labels[4]).toBe("12 PM");
    expect(labels).not.toContain("Midnight");
    expect(ticks.querySelector("span.f")).not.toBeNull();
    expect(ticks.querySelector("span.l")).not.toBeNull();
  });
});
