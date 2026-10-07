import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PanelSkeleton, Skeleton, SkeletonForm, SkeletonList } from "./Skeleton";

describe("Skeleton", () => {
  it("renders an aria-hidden block with the variant class", () => {
    const { container } = render(<Skeleton variant="row" />);
    const el = container.firstElementChild as HTMLElement;
    expect(el).toHaveAttribute("aria-hidden", "true");
    expect(el).toHaveClass("skeleton", "skeleton-row");
  });

  it("SkeletonForm renders the requested field count", () => {
    const { container } = render(<SkeletonForm count={3} />);
    expect(container.querySelectorAll(".skeleton-field")).toHaveLength(3);
  });

  it("SkeletonList renders the requested row count", () => {
    const { container } = render(<SkeletonList rows={5} />);
    expect(container.querySelectorAll(".skeleton-list li")).toHaveLength(5);
  });

  it("PanelSkeleton hides real text and sizes to the panel", () => {
    const { container } = render(<PanelSkeleton tab="genres" />);
    expect(screen.queryByText(/Genres|Name|Slug/i)).toBeNull();
    expect(
      container.querySelectorAll(".skeleton"),
    ).toHaveLength(7); // title + 2 form fields + 4 list rows
  });

  it("PanelSkeleton renders something for unknown tabs", () => {
    const { container } = render(<PanelSkeleton tab="bogus" />);
    expect(container.querySelector(".admin-panel")).toBeInTheDocument();
  });
});
