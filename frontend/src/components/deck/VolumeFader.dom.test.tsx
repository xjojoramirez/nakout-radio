import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { VolumeFader } from "./VolumeFader";

describe("VolumeFader", () => {
  it("has vertical slider semantics", () => {
    render(<VolumeFader value={50} onChange={() => {}} label="Volume fader" />);
    const fader = screen.getByRole("slider", { name: "Volume fader" });
    expect(fader).toHaveAttribute("aria-orientation", "vertical");
    expect(fader).toHaveAttribute("aria-valuemin", "0");
    expect(fader).toHaveAttribute("aria-valuemax", "100");
    expect(fader).toHaveAttribute("aria-valuenow", "50");
  });

  it("changes value with arrow keys", () => {
    const onChange = vi.fn();
    render(<VolumeFader value={50} onChange={onChange} label="Volume fader" />);
    fireEvent.keyDown(screen.getByRole("slider", { name: "Volume fader" }), {
      key: "ArrowUp",
    });
    expect(onChange).toHaveBeenLastCalledWith(52);
  });

  it("uses shift for bigger keyboard steps", () => {
    const onChange = vi.fn();
    render(<VolumeFader value={50} onChange={onChange} label="Volume fader" />);
    fireEvent.keyDown(screen.getByRole("slider", { name: "Volume fader" }), {
      key: "ArrowUp",
      shiftKey: true,
    });
    expect(onChange).toHaveBeenLastCalledWith(60);
  });

  it("drags vertically to change value", () => {
    const onChange = vi.fn();
    render(<VolumeFader value={50} onChange={onChange} label="Volume fader" />);
    const fader = screen.getByRole("slider", { name: "Volume fader" });
    fireEvent.pointerDown(fader, { pointerId: 1, clientY: 100 });
    fireEvent.pointerMove(fader, { pointerId: 1, clientY: 80 });
    fireEvent.pointerUp(fader, { pointerId: 1, clientY: 80 });
    expect(onChange).toHaveBeenLastCalledWith(70);
  });

  it("clamps to 0-100", () => {
    const onChange = vi.fn();
    render(
      <VolumeFader value={100} onChange={onChange} label="Volume fader" />,
    );
    fireEvent.keyDown(screen.getByRole("slider", { name: "Volume fader" }), {
      key: "ArrowUp",
    });
    expect(onChange).toHaveBeenLastCalledWith(100);
  });

  it("ignores keys when disabled", () => {
    const onChange = vi.fn();
    render(
      <VolumeFader
        value={50}
        onChange={onChange}
        label="Volume fader"
        disabled
      />,
    );
    fireEvent.keyDown(screen.getByRole("slider", { name: "Volume fader" }), {
      key: "ArrowUp",
    });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("stops dragging when the pointer is cancelled", () => {
    const onChange = vi.fn();
    render(<VolumeFader value={50} onChange={onChange} label="Volume fader" />);
    const fader = screen.getByRole("slider", { name: "Volume fader" });
    fireEvent.pointerDown(fader, { pointerId: 1, clientY: 100 });
    fireEvent.pointerCancel(fader);
    fireEvent.pointerMove(fader, { pointerId: 1, clientY: 80 });
    expect(onChange).not.toHaveBeenCalled();
  });
});
