"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { toApiError, type UsageMeter, type UsageSummary } from "@/lib/api";
import { useCertForge } from "@/lib/use-api";
import { ErrorNote, Eyebrow, Skeleton } from "./ui";

export function PlanCard({ slug }: { slug: string }) {
  const api = useCertForge();
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    (signal?: AbortSignal) =>
      api
        .getUsage(slug, signal)
        .then((result) => {
          setUsage(result);
          setError(null);
        })
        .catch((err) => {
          if (signal?.aborted) return;
          setError(toApiError(err).message);
        }),
    [api, slug],
  );

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  return (
    <section className="overflow-hidden rounded-xl border border-hair bg-surface shadow-[var(--cf-shadow-card)]">
      <div className="h-1 bg-accent" />
      <div className="space-y-5 p-6">
        <div>
          <Eyebrow tone="accent">Plan</Eyebrow>
          {/* tier_name, not tier: the raw column is free text and has held
              values the API's plan table does not know. In that case the API
              reports the plan whose limits are actually in force, and printing
              the raw value here would name a plan nobody is being given. */}
          <p className="mt-3 font-display text-[30px] font-semibold leading-none tracking-[-0.03em] text-ink">
            {usage?.tier_name ?? "—"}
          </p>
          {usage && !usage.tier_known ? (
            <p className="mt-2 text-xs leading-relaxed text-faint">
              This account is recorded as “{usage.tier}”, which is not a current plan. It is
              being served Community limits until support corrects it.
            </p>
          ) : null}
        </div>

        {error ? <ErrorNote>{error}</ErrorNote> : null}

        {usage === null && !error ? (
          <Skeleton rows={2} />
        ) : usage ? (
          <div className="space-y-4">
            <MeterRow label="Credentials this month" meter={usage.credentials} />
            {/* A stock, not a monthly flow — no "this month". It is the same
                count the API gates template creation on, so the bar filling up
                is the only warning before a 402. */}
            <MeterRow label="Templates held" meter={usage.templates} />
            <MeterRow label="Design readings this month" meter={usage.vision_imports} />
          </div>
        ) : null}

        <p className="text-sm leading-relaxed text-muted">
          Self-serve checkout is not built yet:{" "}
          <Link href="/pricing" className="text-accent no-underline hover:underline">
            compare the plans
          </Link>{" "}
          and email support to move this organization over.
        </p>
      </div>
    </section>
  );
}

function MeterRow({ label, meter }: { label: string; meter: UsageMeter }) {
  const limit = meter.limit;
  const unlimited = limit === null;
  const fraction = unlimited ? 0 : limit === 0 ? 1 : Math.min(1, meter.used / limit);
  const nearLimit = !unlimited && fraction >= 0.9;

  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="text-muted">{label}</span>
        <span className="font-mono text-ink">
          {meter.used}
          {unlimited ? "" : ` / ${meter.limit}`}
        </span>
      </div>
      {unlimited ? null : (
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-well">
          <div
            className={`h-full rounded-full transition-[width] ${nearLimit ? "bg-danger" : "bg-accent"}`}
            style={{ width: `${Math.round(fraction * 100)}%` }}
          />
        </div>
      )}
    </div>
  );
}
