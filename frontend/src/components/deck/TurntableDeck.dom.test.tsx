import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TurntableDeck } from "./TurntableDeck";

describe("TurntableDeck", () => {
  it("puts the cover art on the record label", () => {
    const { container } = render(
      <TurntableDeck playing={false} artUrl="http://img/cover.png" />,
    );
    const label = container.querySelector(".deck .label") as HTMLElement;
    expect(label).not.toBeNull();
    expect(label.style.backgroundImage).toContain("cover.png");
  });

  it("toggles playing state for arm + spin classes", () => {
    const { container, rerender } = render(
      <TurntableDeck playing={false} artUrl={null} />,
    );
    const deck = container.querySelector(".deck") as HTMLElement;
    expect(deck.classList.contains("playing")).toBe(false);
    rerender(<TurntableDeck playing artUrl={null} />);
    expect(deck.classList.contains("playing")).toBe(true);
  });
});
