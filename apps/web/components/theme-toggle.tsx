"use client";

import { useEffect, useState } from "react";

import { currentTheme, setTheme, watchSystemTheme, type Theme } from "@/lib/theme";

/** The light/dark switch. Its own component, not folded into SiteHeader,
 *  because the dashboard page has a different, bespoke header and needs the
 *  same control.
 *
 *  Always a <button> of the same shape on the server and on the client's
 *  first render — an earlier version of this read `document` in a lazy
 *  `useState` initializer to skip the placeholder frame, which sounds like a
 *  free win but is not one: the server pass (no `document`) rendered a
 *  <span> while the client's hydration pass (real `document`, real
 *  attribute) rendered a <button> in the very same slot. A different element
 *  type across the hydration boundary is not a mismatch React can patch —
 *  it discards and rebuilds the whole subtree, which is worse than the one
 *  frame it was trying to save. Defaulting to "light" and correcting after
 *  mount keeps the tag identical across both passes; only the label and icon
 *  differ, which `suppressHydrationWarning` on this element is the
 *  documented tool for.
 */
export function ThemeToggle({ className = "" }: { className?: string }) {
  const [theme, setLocalTheme] = useState<Theme>("light");

  // Reads a value that provably cannot exist before mount (the DOM attribute
  // an inline script sets ahead of hydration) and a subscription to it
  // changing later — there is no version of this that is not an effect.
  // Correcting a value guessed at render time from a browser API that does
  // not exist until mount is not "deriving state React already had", which
  // is what this rule is written to catch.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLocalTheme(currentTheme());
    return watchSystemTheme(setLocalTheme);
  }, []);

  const next: Theme = theme === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      suppressHydrationWarning
      onClick={() => {
        setTheme(next);
        setLocalTheme(next);
      }}
      aria-label={`Switch to ${next} theme`}
      title={`Switch to ${next} theme`}
      className={`flex h-8 w-8 items-center justify-center rounded-lg text-faint transition-colors hover:bg-well hover:text-ink ${className}`}
    >
      {theme === "dark" ? <SunIcon /> : <MoonIcon />}
    </button>
  );
}

function SunIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
      <circle cx="8" cy="8" r="3.5" stroke="currentColor" strokeWidth="1.3" />
      <path
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        d="M8 1v1.5M8 13.5V15M15 8h-1.5M2.5 8H1M12.9 3.1l-1.1 1.1M4.2 11.8l-1.1 1.1M12.9 12.9l-1.1-1.1M4.2 4.2 3.1 3.1"
      />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path
        fill="currentColor"
        d="M13.5 9.5a5.5 5.5 0 0 1-7-7 5.5 5.5 0 1 0 7 7Z"
      />
    </svg>
  );
}
