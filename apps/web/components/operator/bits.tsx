"use client";

import { useEffect, useId, useState, type ReactNode } from "react";

/** Small pieces the operator console shares. Tokens only, as everywhere. */

function Glyph({ children }: { children: ReactNode }) {
  return (
    <svg
      aria-hidden
      width="14"
      height="14"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="shrink-0"
    >
      {children}
    </svg>
  );
}

export const CloseIcon = () => (
  <Glyph>
    <path d="M4 4l8 8M12 4l-8 8" />
  </Glyph>
);

export const CopyIcon = () => (
  <Glyph>
    <rect x="5" y="5" width="8" height="8" rx="1.5" />
    <path d="M3 10.5V4a1 1 0 0 1 1-1h6.5" />
  </Glyph>
);

/** Decorative: whatever it sits in carries the accessible "Saving…" text. */
export function Spinner() {
  return (
    <svg aria-hidden width="14" height="14" viewBox="0 0 16 16" className="shrink-0 animate-spin">
      <circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" />
      <path d="M14 8a6 6 0 0 0-6-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

/** An icon button that copies an org slug, with the slug as its tooltip on
 *  hover and on keyboard focus. Replaces the slug printed under every name. */
export function CopySlug({ slug }: { slug: string }) {
  const tooltipId = useId();
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(timer);
  }, [copied]);

  return (
    <span className="group relative inline-flex">
      <button
        type="button"
        aria-label={`Copy slug ${slug}`}
        aria-describedby={tooltipId}
        onClick={(event) => {
          event.stopPropagation();
          // Clipboard access can be refused (permissions, insecure origin);
          // the tooltip still shows the slug to copy by hand.
          navigator.clipboard?.writeText(slug).then(
            () => setCopied(true),
            () => undefined,
          );
        }}
        className="rounded p-1 text-faint transition-colors hover:bg-well hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
      >
        <CopyIcon />
      </button>
      <span
        id={tooltipId}
        role="tooltip"
        className="pointer-events-none absolute left-1/2 top-full z-20 mt-1 -translate-x-1/2 whitespace-nowrap rounded-md bg-ink px-2 py-1 font-mono text-[11px] text-ground opacity-0 shadow-[var(--cf-shadow-card)] transition-opacity group-focus-within:opacity-100 group-hover:opacity-100"
      >
        {copied ? "Copied" : slug}
      </span>
    </span>
  );
}

/** A success message that outlives the dialog that produced it. */
export function Toast({ message, onDismiss }: { message: string | null; onDismiss: () => void }) {
  useEffect(() => {
    if (!message) return;
    const timer = setTimeout(onDismiss, 6000);
    return () => clearTimeout(timer);
  }, [message, onDismiss]);

  // The live region stays mounted so screen readers announce the change.
  return (
    <div role="status" aria-live="polite" className="pointer-events-none fixed bottom-6 right-6 z-50 max-w-sm">
      {message ? (
        <div className="pointer-events-auto flex items-start gap-3 rounded-lg border border-accent-line bg-accent-wash px-4 py-3 text-sm text-accent shadow-[var(--cf-shadow-lift)]">
          <span className="min-w-0 flex-1">{message}</span>
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Dismiss notification"
            className="rounded p-0.5 hover:bg-surface"
          >
            <CloseIcon />
          </button>
        </div>
      ) : null}
    </div>
  );
}

/** A column header that sorts. `aria-sort` sits on the `<th>`, as the ARIA
 *  table pattern requires; the button inside is what takes focus. */
export function SortHeader<T extends string>({
  label,
  column,
  sort,
  dir,
  onSort,
  align = "left",
  className = "",
}: {
  label: string;
  column: T;
  sort: T;
  dir: "asc" | "desc";
  onSort: (column: T) => void;
  align?: "left" | "right";
  className?: string;
}) {
  const current = sort === column;
  return (
    <th
      scope="col"
      aria-sort={current ? (dir === "asc" ? "ascending" : "descending") : "none"}
      className={`px-4 py-3 font-medium ${align === "right" ? "text-right" : ""} ${className}`}
    >
      <button
        type="button"
        onClick={() => onSort(column)}
        className={`inline-flex items-center gap-1 rounded hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent ${
          current ? "text-ink" : ""
        }`}
      >
        {label}
        <span aria-hidden className="w-3 text-[10px]">
          {current ? (dir === "asc" ? "▲" : "▼") : ""}
        </span>
      </button>
    </th>
  );
}

/** This month's usage against the limit. Neutral, amber at ≥ 80%, red at
 *  ≥ 100%. An unlimited org gets no bar — there is nothing to fill. */
export function UsageBar({ percent, tone }: { percent: number | null; tone: "neutral" | "warn" | "bad" | null }) {
  if (percent === null || tone === null) return null;
  const fill = { neutral: "bg-muted", warn: "bg-warn", bad: "bg-danger" }[tone];
  return (
    <span
      role="meter"
      aria-label="Usage this month"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.min(100, Math.round(percent))}
      aria-valuetext={`${Math.round(percent)}% of limit`}
      className="mt-1.5 ml-auto block h-1.5 w-full max-w-28 overflow-hidden rounded-full bg-well"
    >
      <span className={`block h-full rounded-full ${fill}`} style={{ width: `${Math.min(100, percent)}%` }} />
    </span>
  );
}

/** A small read-only flag beside a value, e.g. "Duplicate name". */
export function QualityBadge({ children, title }: { children: string; title: string }) {
  return (
    <span
      title={title}
      className="ml-1.5 inline-flex shrink-0 items-center rounded border border-warn-line bg-warn-wash px-1.5 py-px font-mono text-[10px] uppercase tracking-[0.06em] text-warn-ink"
    >
      {children}
    </span>
  );
}
