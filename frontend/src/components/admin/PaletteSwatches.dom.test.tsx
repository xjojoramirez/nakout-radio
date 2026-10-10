import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { GENRE_PALETTE } from "../../palette";
import { PaletteSwatches } from "./PaletteSwatches";

describe("PaletteSwatches", () => {
  it("renders one radio per palette colour, checked on selected", () => {
    render(
      <PaletteSwatches label="Genre colour" value={GENRE_PALETTE[0]} onChange={() => {}} />,
    );
    const group = screen.getByRole("radiogroup", { name: "Genre colour" });
    const radios = within(group).getAllByRole("radio");
    expect(radios).toHaveLength(GENRE_PALETTE.length);
    expect(radios[0]).toHaveAttribute("aria-checked", "true");
    expect(radios[0].style.getPropertyValue("--gc")).toBe(GENRE_PALETTE[0]);
  });

  it("reports clicked colour", () => {
    const onChange = vi.fn();
    render(<PaletteSwatches label="Genre colour" value="" onChange={onChange} />);
    const group = screen.getByRole("radiogroup", { name: "Genre colour" });
    fireEvent.click(within(group).getAllByRole("radio")[2]);
    expect(onChange).toHaveBeenCalledWith(GENRE_PALETTE[2]);
  });
});
