import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { GenreChipRadio } from "./GenreChipRadio";
import type { Genre } from "../../types";

const genres: Genre[] = [
  { id: 1, name: "Emo Night", slug: "EN", is_default: false, color: "#f2a33a", track_count: 3 },
  { id: 2, name: "NU Metal", slug: "numetal", is_default: false, color: "#e0654a", track_count: 5 },
];

describe("GenreChipRadio", () => {
  it("chips carry the genre colour + radiogroup semantics", () => {
    render(<GenreChipRadio label="Genre" genres={genres} value={2} onChange={() => {}} />);
    const group = screen.getByRole("radiogroup", { name: "Genre" });
    const radios = within(group).getAllByRole("radio");
    expect(radios).toHaveLength(2);
    expect(radios[1]).toHaveAttribute("aria-checked", "true");
    expect(radios[0].style.getPropertyValue("--gc")).toBe("#f2a33a");
    expect(radios[0]).toHaveTextContent("Emo Night");
  });

  it("falls back to amber for an empty colour", () => {
    const withEmpty: Genre[] = [{ ...genres[0], color: "" }];
    render(<GenreChipRadio label="Genre" genres={withEmpty} value={1} onChange={() => {}} />);
    expect(screen.getByRole("radio").style.getPropertyValue("--gc")).toBe("var(--amber)");
  });

  it("shows the empty hint when there are no genres", () => {
    render(<GenreChipRadio label="Genre" genres={[]} value={null} onChange={() => {}} />);
    expect(screen.getByText(/Create a genre first/i)).toBeInTheDocument();
    expect(screen.queryByRole("radiogroup")).toBeNull();
  });

  it("selects on click", () => {
    const onChange = vi.fn();
    render(<GenreChipRadio label="Genre" genres={genres} value={1} onChange={onChange} />);
    fireEvent.click(screen.getByText("NU Metal"));
    expect(onChange).toHaveBeenCalledWith(2);
  });
});
