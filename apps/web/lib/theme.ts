/** Light/dark theme, as an explicit choice that overrides the OS setting.
 *
 *  The source of truth is the `data-theme` attribute on `<html>`, not React
 *  state — it has to be, because it is set before React ever mounts (see
 *  `THEME_BOOTSTRAP_SCRIPT` below) to avoid a flash of the wrong theme on
 *  load. Every function here reads or writes that attribute plus the one
 *  `localStorage` key; there is no other state to keep in sync.
 */

export type Theme = "light" | "dark";

export const THEME_STORAGE_KEY = "cf-theme";

/** The theme currently painted, read from the DOM rather than localStorage —
 *  the attribute is what CSS actually keys on, and the two could only drift
 *  if something else wrote the attribute directly. */
export function currentTheme(): Theme {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

/** An explicit choice. Persisted, and pinned until the person clears storage
 *  or picks again — from this point the OS toggle stops mattering, which is
 *  the entire point of a manual override existing. */
export function setTheme(theme: Theme): void {
  document.documentElement.setAttribute("data-theme", theme);
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Private browsing, or storage disabled. The attribute is already set,
    // so the theme still applies for this load — it just will not survive
    // a reload, which is the correct degradation, not a broken toggle.
  }
}

/** Re-synced to the OS on load and live thereafter, for exactly as long as
 *  nobody has clicked the toggle. Called once, from the client component
 *  that owns the toggle button — not from the bootstrap script, which only
 *  needs to run once per page load and is not a React effect. */
export function watchSystemTheme(onChange: (theme: Theme) => void): () => void {
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  const handler = () => {
    let stored: string | null = null;
    try {
      stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    } catch {
      // Treated as "nothing stored" below.
    }
    if (stored === "light" || stored === "dark") return; // pinned; ignore the OS
    onChange(media.matches ? "dark" : "light");
  };
  media.addEventListener("change", handler);
  return () => media.removeEventListener("change", handler);
}

/** Inlined verbatim into `<head>` by layout.tsx, before any stylesheet or
 *  React code runs. Must stay synchronous and dependency-free — it is
 *  deliberately not a call into this module, because by the time a bundled
 *  script could load, the flash it exists to prevent has already happened.
 *
 *  Mirrors currentTheme()/systemPrefersDark() by hand for that reason; if the
 *  storage key or the resolution order changes, both copies need it.
 */
export const THEME_BOOTSTRAP_SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem("${THEME_STORAGE_KEY}");
    var theme = stored === "light" || stored === "dark"
      ? stored
      : (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.setAttribute("data-theme", theme);
  } catch (e) {
    // localStorage or matchMedia unavailable: leave data-theme unset. The
    // CSS @media fallback in globals.css still honors the OS preference.
  }
})();
`.trim();
