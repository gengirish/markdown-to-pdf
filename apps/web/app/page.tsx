import type { Metadata } from "next";
import Link from "next/link";

import { AccountPanel } from "@/components/account-panel";
import { SiteHeader } from "@/components/site-header";
import { SpecimenCertificate } from "@/components/specimen-certificate";
import { VerifyLookup } from "@/components/verify-lookup";
import { Eyebrow } from "@/components/dashboard/ui";

export const metadata: Metadata = {
  title: { absolute: "CertForge — verifiable credentials" },
  description:
    "Issue tamper-evident certificates in bulk, let recipients claim them into a public passport, and let anyone verify one from its ID.",
};

/** The three audiences, in the redesign's order. */
const AUDIENCES = [
  {
    index: "01",
    who: "Issuers",
    title: "Validate before you sign",
    body: "Map a CSV to a template and CertForge reports every row it could not render before anything is issued — so a typo never becomes a credential you have to revoke.",
    cta: "See the issuing flow",
    href: "#lifecycle",
  },
  {
    index: "02",
    who: "Recipients",
    title: "A passport that outlives the cohort",
    body: "One public URL holding everything a person has earned — still resolving after the programme, the employer or the issuer has wound down.",
    cta: "See a passport",
    href: "#lifecycle",
  },
  {
    index: "03",
    who: "Developers",
    title: "Issue from one call",
    body: "Templates, credentials, batches and revocation are the whole surface. Every issuance returns its verify URL, its badge document and its PDF.",
    cta: "Read the API",
    href: "https://api.certforge.intelliforge.tech/docs",
  },
];

const LIFECYCLE = [
  {
    step: "1",
    title: "Define a template",
    body: "The guided form, hand-written HTML, or your own certificate design with the fields dragged onto it.",
  },
  {
    step: "2",
    title: "Upload the cohort",
    body: "A CSV against that template. Every row is rendered and signed; the batch reports what succeeded and what did not.",
  },
  {
    step: "3",
    title: "Recipients claim",
    body: "Unclaimed credentials still verify. Claiming only adds the passport — it never changes whether the credential is valid.",
  },
  {
    step: "4",
    title: "Anyone verifies",
    body: "One ID resolves to a human page and an Open Badges 3.0 document. No login, no account, no email to your team.",
  },
];

/** The redesign asks for this section, and it is the most useful thing on the
 *  page — so it has to be true. Each line below is a surface that exists in
 *  this repository today, not a roadmap. */
const STATUS = [
  {
    label: "Live",
    tone: "ok" as const,
    items: [
      "Public verification page",
      "Open Badges 3.0 export",
      "CSV bulk issuance",
      "Single-credential API issuance",
      "Certificates rendered on demand",
      "Issuer revocation",
    ],
  },
  {
    label: "In build",
    tone: "warn" as const,
    items: [
      "Recipient passports",
      "Claim-by-email flow",
      "Your own artwork as a template",
      "Email delivery reporting",
    ],
  },
  {
    label: "Not yet",
    tone: "neutral" as const,
    items: ["Self-serve billing and plan upgrades", "Webhook delivery retries", "Usage reporting"],
  },
];

export default function Home() {
  return (
    <div className="min-h-screen bg-ground">
      <SiteHeader>
        <nav className="hidden items-center gap-6 text-sm text-muted sm:flex">
          <a href="#lifecycle" className="no-underline hover:text-ink">
            How it works
          </a>
          <a href="#status" className="no-underline hover:text-ink">
            What is live
          </a>
          <a
            href="https://api.certforge.intelliforge.tech/docs"
            className="no-underline hover:text-ink"
          >
            API
          </a>
        </nav>
      </SiteHeader>

      <main className="pb-28">
        {/* ── Hero ─────────────────────────────────────────────────────── */}
        <section className="mx-auto grid max-w-[1200px] grid-cols-1 items-start gap-14 px-6 pb-14 pt-16 sm:px-8 lg:grid-cols-[1.1fr_0.9fr] lg:gap-16">
          <div>
            {/* The redesign said "Ed25519 signed". CertForge signs with
                HMAC-SHA256 — there is no Ed25519 anywhere in the codebase — and
                a cryptographic claim on a landing page has to be the one the
                software actually makes. */}
            <div className="mb-5">
              <Eyebrow>Open Badges 3.0 · HMAC-SHA256 signed</Eyebrow>
            </div>

            <h1 className="mb-5 font-display text-[40px] font-semibold leading-[1.03] tracking-[-0.035em] text-ink text-pretty sm:text-[54px] lg:text-[60px]">
              Ship a cohort&rsquo;s credentials in one upload.
            </h1>

            <p className="mb-8 max-w-[520px] text-lg leading-relaxed text-muted text-pretty">
              CertForge mints tamper-evident certificates for bootcamps, internships and events.
              Recipients keep them in a passport they own. Employers verify one from its ID alone —
              no login, no email to your team.
            </p>

            <div className="mb-8">
              <AccountPanel />
            </div>

            <ul className="flex list-none flex-wrap gap-x-6 gap-y-2.5 p-0">
              {["CSV or REST", "Your own artwork", "Issuer revocation", "No recipient account"].map(
                (feature) => (
                  <li
                    key={feature}
                    className="flex items-center gap-2 font-mono text-[11px] text-muted"
                  >
                    <span aria-hidden className="h-[5px] w-[5px] rounded-full bg-accent" />
                    {feature}
                  </li>
                ),
              )}
            </ul>
          </div>

          <div>
            <div className="rounded-xl border border-hair bg-surface p-5 shadow-[var(--cf-shadow-card)]">
              <VerifyLookup compact />
            </div>

            <div className="mt-5">
              <SpecimenCertificate />
            </div>

            <p className="mt-2.5 text-right text-xs leading-relaxed text-faint">
              Specimen — this ID resolves to nothing.
            </p>
          </div>
        </section>

        {/* ── Three audiences ──────────────────────────────────────────── */}
        <section className="border-y border-hair bg-surface">
          <div className="mx-auto grid max-w-[1200px] grid-cols-1 gap-12 px-6 py-14 sm:px-8 md:grid-cols-3">
            {AUDIENCES.map((audience) => (
              <div key={audience.index}>
                <div className="mb-3.5">
                  <Eyebrow tone="accent">
                    {audience.index} · {audience.who}
                  </Eyebrow>
                </div>
                <h2 className="mb-3 font-display text-[25px] font-semibold leading-tight tracking-[-0.025em] text-ink">
                  {audience.title}
                </h2>
                <p className="mb-3.5 text-sm leading-relaxed text-muted">{audience.body}</p>
                <a
                  href={audience.href}
                  className="border-b border-accent-line text-sm text-accent no-underline hover:border-accent"
                >
                  {audience.cta}
                </a>
              </div>
            ))}
          </div>
        </section>

        {/* ── Lifecycle ────────────────────────────────────────────────── */}
        <section id="lifecycle" className="mx-auto max-w-[1200px] px-6 pt-16 sm:px-8">
          <div className="mb-4">
            <Eyebrow>Lifecycle</Eyebrow>
          </div>
          <ol className="grid list-none grid-cols-1 gap-px overflow-hidden rounded-xl border border-hair bg-hair p-0 sm:grid-cols-2 lg:grid-cols-4">
            {LIFECYCLE.map((stage) => (
              <li key={stage.step} className="bg-surface px-6 py-7">
                <div
                  aria-hidden
                  className="mb-3 font-display text-[30px] font-bold leading-none text-accent-line"
                >
                  {stage.step}
                </div>
                <h3 className="mb-2 text-[15px] font-medium text-ink">{stage.title}</h3>
                <p className="text-sm leading-relaxed text-muted">{stage.body}</p>
              </li>
            ))}
          </ol>
        </section>

        {/* ── Where the product actually is ────────────────────────────── */}
        <section id="status" className="mx-auto max-w-[1200px] px-6 pt-16 sm:px-8">
          <div className="rounded-xl border border-hair bg-surface p-7 sm:p-8">
            <div className="mb-7 flex flex-wrap items-start justify-between gap-4">
              <div>
                <h2 className="mb-1.5 font-display text-[25px] font-semibold tracking-[-0.025em] text-ink">
                  Where CertForge actually is
                </h2>
                <p className="max-w-xl text-sm leading-relaxed text-muted">
                  Early access, in the open. Rather than a disclaimer, the state of each surface.
                </p>
              </div>
              <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-faint">
                Updated Aug 2026
              </span>
            </div>

            <div className="grid grid-cols-1 gap-8 sm:grid-cols-3">
              {STATUS.map((group) => (
                <div key={group.label}>
                  <div className="mb-3 flex items-center gap-2">
                    <span
                      aria-hidden
                      className={`h-[7px] w-[7px] rounded-full ${
                        group.tone === "ok"
                          ? "bg-accent"
                          : group.tone === "warn"
                            ? "bg-warn"
                            : "bg-hair-strong"
                      }`}
                    />
                    <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
                      {group.label}
                    </span>
                  </div>
                  <ul className="list-none space-y-1.5 p-0 text-sm leading-relaxed text-muted">
                    {group.items.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-hair">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-4 px-6 py-8 text-sm text-faint sm:px-8">
          <span>CertForge by IntelliForge</span>
          <span>
            Verification is free and public, forever.{" "}
            <Link href="/" className="text-accent no-underline hover:underline">
              Verify a credential
            </Link>
          </span>
        </div>
      </footer>
    </div>
  );
}
