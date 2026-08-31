import type { Metadata } from "next";
import Link from "next/link";

import { SiteHeader } from "@/components/site-header";
import { Eyebrow, Mono, StatusTag } from "@/components/dashboard/ui";
import { publicApi, toApiError, type PassportView } from "@/lib/api";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ username: string }>;
}): Promise<Metadata> {
  const { username } = await params;
  return {
    title: `@${username}`,
    description: `Verified credentials earned by @${username}.`,
  };
}

/**
 * A recipient's public credential passport.
 *
 * Rendered on the server: the page is public, has no session to read, and is
 * something we want search engines and link previews to see. The route has no
 * `generateStaticParams`, so it is server-rendered on demand and never fetches
 * at build time.
 */
export default async function PassportPage({
  params,
}: {
  params: Promise<{ username: string }>;
}) {
  const { username } = await params;

  let passport: PassportView;
  try {
    passport = await publicApi.getPassport(username);
  } catch (err) {
    const error = toApiError(err);
    return (
      <PassportShell>
        <div className="mx-auto mt-24 max-w-md rounded-xl border border-hair bg-surface p-8 text-center shadow-[var(--cf-shadow-card)]">
          <h1 className="font-display text-2xl font-semibold tracking-[-0.02em] text-ink">
            {error.isNotFound
              ? "No passport here"
              : error.isForbidden
                ? "This passport is private"
                : "Passport unavailable"}
          </h1>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            {error.isNotFound
              ? `Nobody has claimed the passport “${username}” yet.`
              : error.message}
          </p>
          <Link
            href="/"
            className="mt-6 inline-block rounded-lg border border-hair-strong px-5 py-2.5 text-sm font-medium text-ink no-underline transition-colors hover:border-accent hover:text-accent"
          >
            Back to CertForge
          </Link>
        </div>
      </PassportShell>
    );
  }

  const { profile, credentials } = passport;
  const displayName = profile.display_name?.trim() || profile.username;

  /* The design shows three counters. Each is computed from what the API
   * actually returned — a passport with one credential must not read "3
   * issuers" because the mock did. */
  const issuers = new Set(
    credentials
      .map((c) => (typeof c.metadata?.issuer === "string" ? c.metadata.issuer : null))
      .filter((name): name is string => Boolean(name)),
  );
  const years = credentials
    .map((c) => new Date(c.issued_at).getFullYear())
    .filter((year) => !Number.isNaN(year));
  const firstYear = years.length > 0 ? Math.min(...years) : null;

  return (
    <PassportShell>
      {/* ── Identity ─────────────────────────────────────────────────────── */}
      <section className="overflow-hidden rounded-xl border border-hair bg-surface shadow-[var(--cf-shadow-card)]">
        <div className="h-1 bg-accent" />
        <div className="p-6 sm:p-8">
          <div className="flex flex-wrap items-center gap-5">
            <span
              aria-hidden
              className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl border border-accent-line bg-accent-wash font-display text-lg font-semibold text-accent"
            >
              {initials(displayName)}
            </span>
            <div className="min-w-0 flex-1">
              <h1 className="font-display text-[28px] font-semibold leading-tight tracking-[-0.025em] text-ink">
                {displayName}
              </h1>
              <Mono className="text-sm text-muted">@{profile.username}</Mono>
            </div>
          </div>

          {profile.bio ? (
            <p className="mt-5 max-w-2xl text-sm leading-relaxed text-muted">{profile.bio}</p>
          ) : null}

          <dl className="mt-7 flex flex-wrap items-start gap-x-12 gap-y-5">
            <Stat value={String(credentials.length)} label="credentials" />
            <Stat value={String(issuers.size)} label={issuers.size === 1 ? "issuer" : "issuers"} />
            {firstYear ? <Stat value={String(firstYear)} label="first credential" /> : null}
            <p className="max-w-xs text-xs leading-relaxed text-faint">
              {displayName.split(" ")[0]} controls what is public here. A hidden credential still
              verifies by its ID.
            </p>
          </dl>
        </div>
      </section>

      {/* ── Credentials ──────────────────────────────────────────────────── */}
      <div className="mb-4 mt-10 flex items-center justify-between gap-4">
        <h2 className="font-display text-xl font-semibold tracking-[-0.02em] text-ink">
          Credentials
        </h2>
        <Eyebrow>
          {credentials.length} {credentials.length === 1 ? "record" : "records"}
        </Eyebrow>
      </div>

      {credentials.length === 0 ? (
        <div className="rounded-xl border border-dashed border-hair-strong p-12 text-center">
          <p className="text-sm text-ink">No credentials claimed yet.</p>
          <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-faint">
            Credentials appear here once they are claimed from an issuer&apos;s invitation link.
            Until then they still verify by ID — claiming only adds them to this page.
          </p>
        </div>
      ) : (
        <ul className="grid list-none grid-cols-1 gap-3 p-0 md:grid-cols-2">
          {credentials.map((credential) => {
            const issuer =
              typeof credential.metadata?.issuer === "string" ? credential.metadata.issuer : null;
            return (
              <li
                key={credential.id}
                className="rounded-xl border border-hair bg-surface p-5 transition-colors hover:border-hair-strong"
              >
                <div className="mb-3.5 flex items-center justify-between gap-3">
                  <StatusTag tone={credential.pinned ? "ok" : "neutral"}>
                    {credential.pinned ? "Pinned" : "Verified"}
                  </StatusTag>
                  <span className="text-xs text-faint">{formatIssueDate(credential.issued_at)}</span>
                </div>

                <h3 className="mb-1 text-[15px] font-medium leading-snug text-ink">
                  {credential.title}
                </h3>
                {issuer ? <p className="mb-3.5 text-xs text-muted">{issuer}</p> : null}

                <Mono className="mb-4 block text-xs text-faint">{credential.id}</Mono>

                <div className="flex flex-wrap items-center gap-4 text-xs">
                  <a
                    href={publicApi.verificationPageUrl(credential.id)}
                    target="_blank"
                    rel="noreferrer"
                    className="text-accent no-underline hover:underline"
                  >
                    Verification page
                  </a>
                  <a
                    href={publicApi.badgeUrl(credential.id)}
                    target="_blank"
                    rel="noreferrer"
                    className="text-muted no-underline hover:text-ink"
                  >
                    JSON
                  </a>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {/* ── Claim prompt ─────────────────────────────────────────────────── */}
      <section className="mt-10 flex flex-wrap items-center justify-between gap-5 rounded-xl border border-hair bg-well px-6 py-5">
        <div>
          <p className="text-[15px] font-medium text-ink">
            Got a credential email you haven&apos;t claimed?
          </p>
          <p className="mt-1 text-sm text-muted">
            Open the link in that email and it joins this passport in one step.
          </p>
        </div>
      </section>
    </PassportShell>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <dt className="sr-only">{label}</dt>
      <dd className="m-0">
        <span className="block font-display text-[26px] font-semibold leading-none tracking-[-0.02em] text-ink">
          {value}
        </span>
        <span className="mt-1.5 block font-mono text-[10px] uppercase tracking-[0.12em] text-faint">
          {label}
        </span>
      </dd>
    </div>
  );
}

function PassportShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-ground">
      <SiteHeader />
      <main className="mx-auto max-w-[900px] px-6 pb-24 pt-10 sm:px-8">{children}</main>
    </div>
  );
}

/** Up to two initials, so "Ananya Rao" reads AR rather than A. */
function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

function formatIssueDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("en-US", { month: "short", year: "numeric" });
}
