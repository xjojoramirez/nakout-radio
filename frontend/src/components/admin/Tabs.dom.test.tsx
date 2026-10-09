import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Tabs } from "./Tabs";

describe("Tabs", () => {
  it("marks the active tab and reports clicks", () => {
    const onChange = vi.fn();
    render(
      <Tabs
        tabs={[
          { id: "a", label: "A" },
          { id: "b", label: "B" },
        ]}
        active="a"
        onChange={onChange}
      />,
    );
    expect(screen.getByRole("tab", { name: "A" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    fireEvent.click(screen.getByRole("tab", { name: "B" }));
    expect(onChange).toHaveBeenCalledWith("b");
  });

  it("shows a count pill when a count is provided and omits it for null", () => {
    const onChange = vi.fn();
    render(
      <Tabs
        tabs={[
          { id: "a", label: "A", count: 3 },
          { id: "b", label: "B", count: null },
        ]}
        active="a"
        onChange={onChange}
      />,
    );
    const counted = screen.getByRole("tab", { name: /^A/ });
    const pill = within(counted).getByText("3");
    expect(pill).toHaveClass("count");
    expect(screen.getByRole("tab", { name: "B" })).toBeInTheDocument();
  });
});
