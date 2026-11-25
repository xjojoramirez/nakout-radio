import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ThemeSwitch } from "./ThemeSwitch";
import { THEME_STORAGE_KEY } from "../theme";

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.dataset.theme = "dark";
});

afterEach(() => {
  cleanup();
  delete document.documentElement.dataset.theme;
  document.documentElement.style.colorScheme = "";
});

describe("ThemeSwitch", () => {
  it("marks the current theme and switches to light", () => {
    render(<ThemeSwitch />);

    expect(screen.getByRole("button", { name: "Use dark theme" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    fireEvent.click(screen.getByRole("button", { name: "Use light theme" }));

    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    expect(
      screen.getByRole("button", { name: "Use light theme" }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("starts from the theme already on the document", () => {
    document.documentElement.dataset.theme = "light";

    render(<ThemeSwitch />);

    expect(
      screen.getByRole("button", { name: "Use light theme" }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("switches back to dark", () => {
    document.documentElement.dataset.theme = "light";
    render(<ThemeSwitch />);

    fireEvent.click(screen.getByRole("button", { name: "Use dark theme" }));

    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
  });
});
