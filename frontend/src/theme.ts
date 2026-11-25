import { useCallback, useSyncExternalStore } from "react";

export type Theme = "light" | "dark";

export const THEME_STORAGE_KEY = "nakout-theme";
export const LIGHT_QUERY = "(prefers-color-scheme: light)";

const listeners = new Set<() => void>();

function notify() {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function hasDom() {
  return typeof document !== "undefined";
}

function systemTheme(): Theme {
  if (
    typeof window === "undefined" ||
    typeof window.matchMedia !== "function"
  ) {
    return "dark";
  }
  return window.matchMedia(LIGHT_QUERY).matches ? "light" : "dark";
}

export function storedTheme(): Theme | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.localStorage.getItem(THEME_STORAGE_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

export function getTheme(): Theme {
  if (!hasDom()) return "dark";
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

function apply(theme: Theme) {
  if (!hasDom()) return;
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) {
    meta.setAttribute("content", theme === "light" ? "#f3efe6" : "#090b0e");
  }
}

export function setTheme(theme: Theme) {
  apply(theme);
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Storage can be unavailable in private or sandboxed contexts; the
    // in-memory theme still applies for this visit.
  }
  notify();
}

/**
 * Applies the stored or system theme before the app renders. index.html runs
 * the same resolution inline so the first paint already has the right colour.
 */
export function initTheme() {
  const resolved =
    storedTheme() ??
    (document.documentElement.dataset.theme === "light" ||
    document.documentElement.dataset.theme === "dark"
      ? document.documentElement.dataset.theme
      : systemTheme());

  apply(resolved);

  if (typeof window.matchMedia !== "function") return;
  const media = window.matchMedia(LIGHT_QUERY);
  media.addEventListener?.("change", (event) => {
    // Follow the OS until the listener makes an explicit choice.
    if (storedTheme()) return;
    apply(event.matches ? "light" : "dark");
    notify();
  });
}

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, getTheme, () => "dark" as Theme);

  const choose = useCallback((next: Theme) => {
    setTheme(next);
  }, []);

  return { theme, setTheme: choose };
}
