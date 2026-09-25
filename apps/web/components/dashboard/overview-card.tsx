"use client";

import { useEffect, useState, type ReactNode } from "react";

import { toApiError, type CredentialListQuery, type UsageSummary } from "@/lib/api";
import { useCertForge } from "@/lib/use-api";
import { Eyebrow, buttonClass } from "./ui";

/** The dashboard's front page: how much has gone out, and whether it arrived.
 *
 *  Every number is one the API already records. What it does not record is
 *  shown as "—" with the reason, never estimated. Verify-page views are the
 *  obvious gap: nothing counts them yet, and a plausible-looking figure there
 *  is the fabricated-data failure this app has shipped before.
 *
 *  The counts are `total`s off filtered one-row list calls, so they agree
 *  with the Credentials tab by construction: the same filters, the same
 *  endpoint.
 */

type Count = { status: "loading" } | { status: "ready"; value: number } | { status: "error"; message: string };

function useCount(slug: string, query: CredentialListQuery, refreshToken: number): Count {
  const api = useCertForge();
  const [count, setCount] = useState<Count>({ status: "loading" });
  // The query is rebuilt every render; its JSON is the stable identity.
  const key = JSON.stringify(query);

  useEffect(() => {
    const controller = new AbortController();
    api
      .listOrgCredentials(slug, { ...JSON.parse(key), limit: 1 }, controller.signal)
      .then((page) => setCount({ status: "ready", value: page.total }))
      .catch((err) => {
        if (!controller.signal.aborted) setCount({ status: "error", message: toApiError(err).message });
      });
    return () => controller.abort();
  }, [api, slug, key, refreshToken]);

  return count;
}

export function OverviewCard({
  slug,
  refreshToken,
  onViewCredentials,
  onViewPlan,
}: {
  slug: string;
  refreshToken: number;
  onViewCredentials: () => void;
  onViewPlan: () => void;
}) {
  const api = useCertForge();
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [usageError, setUsageError] = useState<string | null>(null);

  // Test credentials are excluded from every count here: they are not awards,
  // and the Credentials tab labels them separately.
  const allTime = useCount(slug, { test: "exclude" }, refreshToken);
  const sent = useCount(slug, { test: "exclude", deliveryStatus: "sent" }, refreshToken);
  const failed = useCount(slug, { test: "exclude", deliveryStatus: "failed" }, refreshToken);

  useEffect(() => {
    const controller = new AbortController();
    api
      .getUsage(slug, controller.signal)
      .then((result) => {
        setUsage(result);
        setUsageError(null);
      })
      .catch((err) => {
        if (!controller.signal.aborted) setUsageError(toApiError(err).message);
      });
    return () => controller.abort();
  }, [api, slug, refreshToken]);

  const meter = usage?.credentials;

  return (
    <section className="rounded-xl border border-hair bg-surface p-6 shadow-[var(--cf-shadow-card)] sm:p-7">
      <h2 className="font-display text-xl font-semibold tracking-[-0.02em] text-ink">Overview</h2>

      <dl className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat
          label="Issued this month"
          value={meter ? meter.used : usageError ? null : undefined}
          unavailable={usageError}
          hint={
            meter
              ? meter.limit === null
                ? "No monthly limit on your plan"
                : `of ${meter.limit} on your plan`
              : undefined
          }
        />
        <Stat label="Issued all time" count={allTime} hint="Excluding test credentials" />
        <Stat label="Emails sent" count={sent} hint="Accepted by the mail provider" />
        <Stat
          label="Emails failed"
          count={failed}
          hint="Rejected when sent. Resend from Credentials."
          warn
        />
      </dl>

      {meter && meter.limit !== null ? (
        <div className="mt-6">
          <div className="flex items-baseline justify-between gap-2 text-sm">
            <span className="text-muted">Plan usage, {usage?.period}</span>
            <span className="font-mono text-ink">
              {meter.used} / {meter.limit}
            </span>
          </div>
          <div
            className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-well"
            role="meter"
            aria-label="Credentials issued this month against the plan limit"
            aria-valuemin={0}
            aria-valuemax={meter.limit}
            aria-valuenow={meter.used}
          >
            <div
              className={`h-full rounded-full ${
                meter.limit > 0 && meter.used / meter.limit >= 0.9 ? "bg-danger" : "bg-accent"
              }`}
              style={{
                width: `${Math.round(Math.min(1, meter.limit === 0 ? 1 : meter.used / meter.limit) * 100)}%`,
              }}
            />
          </div>
        </div>
      ) : null}

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-hair pt-4">
        <p className="text-xs text-muted">
          <span className="font-medium text-ink">Verify-page views: —</span> not tracked yet.
        </p>
        <div className="flex gap-2">
          <button type="button" onClick={onViewCredentials} className={buttonClass("secondary", "sm")}>
            All credentials
          </button>
          <button type="button" onClick={onViewPlan} className={buttonClass("quiet", "sm")}>
            Plan &amp; usage
          </button>
        </div>
      </div>
    </section>
  );
}

function Stat({
  label,
  count,
  value,
  unavailable,
  hint,
  warn = false,
}: {
  label: string;
  count?: Count;
  /** For a value not from `useCount`: undefined while loading, null if unavailable. */
  value?: number | null;
  unavailable?: string | null;
  hint?: ReactNode;
  warn?: boolean;
}) {
  const resolved =
    count === undefined
      ? value
      : count.status === "ready"
        ? count.value
        : count.status === "error"
          ? null
          : undefined;
  const reason = count?.status === "error" ? count.message : unavailable;

  return (
    <div className="rounded-lg border border-hair px-4 py-4">
      <dt>
        <Eyebrow tone="muted">{label}</Eyebrow>
      </dt>
      <dd className="mt-3">
        {resolved === undefined ? (
          <span aria-hidden className="block h-8 w-12 animate-pulse rounded bg-well" />
        ) : (
          <span
            className={`block font-display text-3xl font-semibold tabular-nums tracking-[-0.02em] ${
              warn && resolved ? "text-warn-ink" : "text-ink"
            }`}
            title={resolved === null && reason ? `Unavailable: ${reason}` : undefined}
          >
            {resolved === null ? "—" : resolved.toLocaleString()}
          </span>
        )}
        {hint ? <span className="mt-1 block text-xs text-muted">{hint}</span> : null}
      </dd>
    </div>
  );
}
