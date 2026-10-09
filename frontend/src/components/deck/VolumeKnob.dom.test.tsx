import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { VolumeKnob } from "./VolumeKnob";

describe("VolumeKnob", () => {
  it("has slider semantics and reports its value", () => {
    render(<VolumeKnob value={50} onChange={() => {}} label="Volume" />);
    const knob = screen.getByRole("slider", { name: "Volume" });
    expect(knob).toHaveAttribute("aria-valuemin", "0");
    expect(knob).toHaveAttribute("aria-valuemax", "100");
    expect(knob).toHaveAttribute("aria-valuenow", "50");
  });

  it("changes value with arrow keys", () => {
    const onChange = vi.fn();
    render(<VolumeKnob value={50} onChange={onChange} label="Volume" />);
    fireEvent.keyDown(screen.getByRole("slider", { name: "Volume" }), {
      key: "ArrowUp",
    });
    expect(onChange).toHaveBeenLastCalledWith(52);
  });

  it("uses shift for bigger keyboard steps", () => {
    const onChange = vi.fn();
    render(<VolumeKnob value={50} onChange={onChange} label="Volume" />);
    fireEvent.keyDown(screen.getByRole("slider", { name: "Volume" }), {
      key: "ArrowUp",
      shiftKey: true,
    });
    expect(onChange).toHaveBeenLastCalledWith(60);
  });

  it("drags vertically to change value", () => {
    const onChange = vi.fn();
    render(<VolumeKnob value={50} onChange={onChange} label="Volume" />);
    const knob = screen.getByRole("slider", { name: "Volume" });
    fireEvent.pointerDown(knob, { pointerId: 1, clientY: 100 });
    fireEvent.pointerMove(knob, { pointerId: 1, clientY: 80 });
    fireEvent.pointerUp(knob, { pointerId: 1, clientY: 80 });
    expect(onChange).toHaveBeenLastCalledWith(60);
  });

  it("clamps to 0-100", () => {
    const onChange = vi.fn();
    render(<VolumeKnob value={100} onChange={onChange} label="Volume" />);
    fireEvent.keyDown(screen.getByRole("slider", { name: "Volume" }), {
      key: "ArrowUp",
    });
    expect(onChange).toHaveBeenLastCalledWith(100);
  });

  it("ignores keys when disabled", () => {
    const onChange = vi.fn();
    render(
      <VolumeKnob value={50} onChange={onChange} label="Volume" disabled />,
    );
    fireEvent.keyDown(screen.getByRole("slider", { name: "Volume" }), {
      key: "ArrowUp",
    });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("stops dragging when the pointer is cancelled", () => {
    const onChange = vi.fn();
    render(<VolumeKnob value={50} onChange={onChange} label="Volume" />);
    const knob = screen.getByRole("slider", { name: "Volume" });
    fireEvent.pointerDown(knob, { pointerId: 1, clientY: 100 });
    fireEvent.pointerCancel(knob);
    fireEvent.pointerMove(knob, { pointerId: 1, clientY: 80 });
    expect(onChange).not.toHaveBeenCalled();
  });
});
