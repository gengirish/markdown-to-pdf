import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";

import { SiteHeader } from "@/components/site-header";
import { Eyebrow } from "@/components/dashboard/ui";
import { publicApi, toApiError, type Tier } from "@/lib/api";

export const metadata: Metadata = {
  title: "Pricing",
  description:
    "CertForge plans: credentials a month, custom templates, and what each tier includes. Community is free.",
};

/**
 * The public plan catalog.
 *
 * Rendered on the server from `GET /api/v1/tiers`, not from a table kept here.
 * The same table backs the credential quota an org receives and the template
 * gate in the API, so a price shown beside a number nobody is granted is not a
 * copy problem — it is the API and the page disagreeing, and the only way to
 * make that impossible is to have one source.
 *
 * Rendered on demand, never prerendered — that is what `connection()` below
 * buys. Vercel builds this app independently of the Fly deploy that serves
 * /api/v1/tiers, so a build-time fetch can run against an API that does not
 * have the route yet: the build succeeds, the catch below renders "Pricing is
 * unavailable", and that page is what ships. It was observed doing exactly
 * that before this line existed.
 *
 * The fetch itself is still cached for five minutes (`listTiers`), so
 * on-demand does not mean one API call per visitor.
 */

const INR = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

/** Paise to rupees. The wire carries integer minor units so that nothing
 *  upstream of here has to hold money in a float. */
function price(tier: Tier): string {
  if (tier.price_paise === 0) return "Free";
  return INR.format(tier.price_paise / 100);
}

/** `null` is the wire's unlimited. The -1 sentinel never leaves the API. */
function limit(value: number | null, suffix = ""): string {
  if (value === null) return "Unlimited";
  return `${value.toLocaleString("en-IN")}${suffix}`;
}

export default async function PricingPage() {
  // Opt out of prerendering. See the note above the file's imports.
  await connection();

  let tiers: Tier[];
  try {
    tiers = await publicApi.listTiers();
  } catch (err) {
    return (
      <PricingShell>
        <div className="mx-auto mt-20 max-w-md rounded-xl border border-hair bg-surface p-8 text-center shadow-[var(--cf-shadow-card)]">
          <h1 className="font-display text-2xl font-semibold tracking-[-0.02em] text-ink">
            Pricing is unavailable
          </h1>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            {toApiError(err).message}
          </p>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            Email{" "}
            <a className="text-accent no-underline" href="mailto:support@intelliforge.tech">
              support@intelliforge.tech
            </a>{" "}
            and we will send you the plans directly.
          </p>
        </div>
      </PricingShell>
    );
  }

  return (
    <PricingShell>
      <section className="mx-auto max-w-[1200px] px-6 pb-12 pt-16 sm:px-8">
        <div className="mb-4">
          <Eyebrow>Plans</Eyebrow>
        </div>
        <h1 className="mb-5 max-w-[720px] font-display text-[40px] font-semibold leading-[1.05] tracking-[-0.035em] text-ink text-pretty sm:text-[52px]">
          Pay for the cohort you issue, not the seats you fill.
        </h1>
        <p className="max-w-[560px] text-lg leading-relaxed text-muted text-pretty">
          Every plan issues the same credential: signed, verifiable from its ID alone, and
          exportable as an Open Badges 3.0 document. What changes is how many you issue a month,
          how many designs you keep, and whether you issue every cohort from CSV, on your own
          artwork, from your own code.
        </p>
      </section>

      <section className="border-y border-hair bg-surface">
        <div className="mx-auto grid max-w-[1200px] grid-cols-1 gap-5 px-6 py-12 sm:px-8 md:grid-cols-2 lg:grid-cols-4">
          {tiers.map((tier) => (
            <TierCard key={tier.key} tier={tier} />
          ))}
        </div>
      </section>

      {/* Say what actually happens, including the part that is not instant:
          the plan moves on Dodo's signed webhook, not on the browser's return. */}
      <section className="mx-auto max-w-[1200px] px-6 py-12 sm:px-8">
        <div className="grid grid-cols-1 gap-10 md:grid-cols-3">
          <Note title="How an upgrade works">
            The organization&apos;s owner upgrades from the Plan tab in the Credential Studio and
            pays through Dodo Payments, with GST added at checkout. The new limits apply as soon
            as the payment is confirmed, usually within seconds. Card, invoices and cancellation
            live in the billing portal. Nothing you have already issued is affected.
          </Note>
          <Note title="What counts as a credential">
            One rendered, signed credential — whether it came from the API, the dashboard or a
            CSV batch. Re-rendering a PDF, verifying one, or a recipient claiming one does not
            count again. Revoking does not give the month back.
          </Note>
          <Note title="What counts as a template">
            A design your organization holds, not one you issue from. The allowance is a stock:
            delete a template and the slot is free again the same second. The seeded designs
            everyone shares do not count against you.
          </Note>
        </div>
      </section>
    </PricingShell>
  );
}

function TierCard({ tier }: { tier: Tier }) {
  return (
    <div className="flex flex-col overflow-hidden rounded-xl border border-hair bg-ground shadow-[var(--cf-shadow-card)]">
      <div className="h-1 bg-accent" />
      <div className="flex flex-1 flex-col gap-5 p-6">
        <div>
          <p className="font-display text-[22px] font-semibold leading-none tracking-[-0.02em] text-ink">
            {tier.name}
          </p>
          <p className="mt-2.5 text-sm leading-relaxed text-muted">{tier.tagline}</p>
        </div>

        <div>
          <p className="font-display text-[32px] font-semibold leading-none tracking-[-0.03em] text-ink">
            {price(tier)}
          </p>
          <p className="mt-1.5 font-mono text-[11px] text-faint">
            {tier.price_paise === 0 ? "no card required" : "per month"}
          </p>
        </div>

        <dl className="m-0 grid grid-cols-1 gap-2 border-y border-hair py-4">
          <Row term="Credentials" value={limit(tier.monthly_quota, " / month")} />
          <Row term="Templates" value={limit(tier.template_limit)} />
          <Row term="CSV uploads" value={limit(tier.csv_batch_limit, " / month")} />
        </dl>

        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {tier.features.map((feature) => (
            <li key={feature} className="flex gap-2.5 text-sm leading-relaxed text-muted">
              <span aria-hidden className="mt-[7px] h-[5px] w-[5px] shrink-0 rounded-full bg-accent" />
              {feature}
            </li>
          ))}
        </ul>

        <div className="mt-auto pt-2">
          {tier.price_paise === 0 ? (
            <Link
              href="/sign-up"
              className="block rounded-lg bg-accent px-4 py-2.5 text-center text-sm font-medium text-ground no-underline transition-opacity hover:opacity-90"
            >
              Start free
            </Link>
          ) : (
            // Checkout is started from the plan card, not here: it needs an
            // org and its owner, which /dashboard resolves (signing in first
            // if need be) before landing on the Plan tab.
            <Link
              href="/dashboard?tab=plan"
              className="block rounded-lg border border-hair-strong px-4 py-2.5 text-center text-sm font-medium text-ink no-underline transition-colors hover:border-accent hover:text-accent"
            >
              Upgrade to {tier.name}
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}

function Row({ term, value }: { term: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-sm text-muted">{term}</dt>
      <dd className="m-0 text-right font-mono text-[13px] text-ink">{value}</dd>
    </div>
  );
}

function Note({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h2 className="mb-2.5 font-display text-[19px] font-semibold tracking-[-0.02em] text-ink">
        {title}
      </h2>
      <p className="text-sm leading-relaxed text-muted">{children}</p>
    </div>
  );
}

function PricingShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-ground">
      <SiteHeader>
        <nav className="hidden items-center gap-6 text-sm text-muted sm:flex">
          <Link href="/" className="no-underline hover:text-ink">
            Home
          </Link>
          <Link href="/pricing" className="text-ink no-underline">
            Pricing
          </Link>
          <a
            href="https://api.certforge.intelliforge.tech/docs"
            className="no-underline hover:text-ink"
          >
            API
          </a>
        </nav>
      </SiteHeader>
      <main className="pb-24">{children}</main>
    </div>
  );
}
