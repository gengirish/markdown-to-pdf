import type { ReactNode } from "react";

/** Shared primitives, re-skinned to the CertForge redesign.
 *
 *  Every colour here is a token from app/globals.css, never a hex or a Tailwind
 *  palette name. That is what lets the whole product follow the viewer's theme:
 *  a `zinc-800` left in one component is a value that cannot move, and one of
 *  those is all it takes for a card to stay dark on a light page.
 */

export function Card({
  title,
  description,
  action,
  children,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-hair bg-surface p-6 shadow-[var(--cf-shadow-card)] sm:p-7">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="font-display text-xl font-semibold tracking-[-0.02em] text-ink">
            {title}
          </h2>
          {description ? <p className="mt-1.5 text-sm leading-relaxed text-muted">{description}</p> : null}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

/** The small tracked-out mono label the design uses above almost every value.
 *
 *  A component rather than a copied class string because it appears dozens of
 *  times across the redesign, and the letter-spacing is the thing people get
 *  wrong when they retype it. */
export function Eyebrow({
  children,
  tone = "faint",
}: {
  children: ReactNode;
  tone?: "faint" | "accent" | "muted";
}) {
  const color =
    tone === "accent" ? "text-accent" : tone === "muted" ? "text-muted" : "text-faint";
  return (
    <div
      className={`font-mono text-[10px] uppercase leading-none tracking-[0.14em] ${color}`}
    >
      {children}
    </div>
  );
}

/** A failed load. Always says what went wrong rather than showing plausible filler. */
export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-lg border border-danger-line bg-danger-wash px-4 py-3 text-sm text-danger">
      {children}
    </p>
  );
}

export function EmptyNote({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-lg border border-dashed border-hair-strong px-4 py-6 text-center text-sm text-faint">
      {children}
    </p>
  );
}

export function Skeleton({ rows = 2 }: { rows?: number }) {
  return (
    <div className="space-y-3" aria-hidden>
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="h-10 animate-pulse rounded-lg bg-well" />
      ))}
    </div>
  );
}

/** Filled, outline and quiet — the three buttons the design actually uses. */
export function buttonClass(
  variant: "primary" | "secondary" | "quiet" = "primary",
  size: "md" | "sm" = "md",
) {
  const base =
    "inline-flex items-center justify-center rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50";
  const sizing = size === "sm" ? "px-3 py-1.5 text-sm" : "px-5 py-2.5 text-sm";
  const skin = {
    // text-ground, never text-ink: the accent lightens in dark mode, where
    // white on it measures 2.42:1. The ground token inverts with the theme, so
    // one value passes on both (6.17 light, 7.66 dark).
    primary: "bg-accent text-ground hover:bg-accent-hover",
    secondary: "border border-hair-strong text-ink hover:border-accent hover:text-accent",
    quiet: "text-muted hover:text-ink",
  }[variant];
  return `${base} ${sizing} ${skin}`;
}

export const inputClass =
  "w-full rounded-lg border border-hair bg-surface px-4 py-2.5 text-sm text-ink transition-colors focus:border-accent focus:outline-none";

/** A credential ID, a batch id, an API path — anything read character by
 *  character. Mono, slightly tracked, and never wrapped mid-token. */
export function Mono({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <span className={`font-mono tracking-[0.03em] whitespace-nowrap ${className}`}>{children}</span>
  );
}

/** Status pills: verified, revoked, hidden, expired. Tone carries the meaning,
 *  so a caller cannot accidentally paint "revoked" in the affirmative green. */
export function StatusTag({
  children,
  tone,
}: {
  children: ReactNode;
  tone: "ok" | "warn" | "neutral" | "bad";
}) {
  const skin = {
    ok: "bg-accent-wash text-accent border-accent-line",
    warn: "bg-warn-wash text-warn-ink border-warn-line",
    neutral: "bg-well text-muted border-hair",
    bad: "bg-danger-wash text-danger border-danger-line",
  }[tone];
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em] ${skin}`}
    >
      {children}
    </span>
  );
}

export function formatDate(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" });
}
