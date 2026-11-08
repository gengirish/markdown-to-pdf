"use client";

import { useEffect, useState } from "react";

import { toApiError, type OperatorKpis } from "@/lib/api";
import { useCertForge } from "@/lib/use-api";

export type KpiKey = "active" | "issued" | "near" | "failed";

/**
 * Four numbers, each a button that applies the filter it counts. Computed by
 * the API in four aggregate queries (`GET /operator/kpis`); nothing here sums
 * rows. A failed load says so in place of the numbers rather than showing 0s.
 */
export function KpiStrip({
  active,
  onPick,
  reloadToken,
}: {
  /** Which card's filter is currently applied, for its pressed state. */
  active: KpiKey | null;
  onPick: (key: KpiKey) => void;
  /** Bump to re-read after a change that could move a number. */
  reloadToken: number;
}) {
  const api = useCertForge();
  const [kpis, setKpis] = useState<OperatorKpis | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api
      .getOperatorKpis(controller.signal)
      .then((data) => {
        setError(null);
        setKpis(data);
      })
      .catch((err) => {
        if (!controller.signal.aborted) setError(toApiError(err).message);
      });
    return () => controller.abort();
  }, [api, reloadToken]);

  if (error) {
    return <p className="mb-6 text-sm text-danger">Summary unavailable: {error}</p>;
  }

  const cards: { key: KpiKey; label: string; value: number | undefined; hint: string; tone?: "warn" | "bad" }[] = [
    { key: "active", label: "Active orgs this month", value: kpis?.active_orgs, hint: "Show orgs that issued this month" },
    {
      key: "issued",
      label: "Credentials issued this month",
      value: kpis?.credentials_issued,
      hint: "Show active orgs, most issued first",
    },
    {
      key: "near",
      label: `Orgs at ≥ ${kpis?.near_limit_percent ?? 80}% of limit`,
      value: kpis?.near_limit_orgs,
      hint: "Show orgs near their limit",
      tone: kpis && kpis.near_limit_orgs > 0 ? "warn" : undefined,
    },
    {
      key: "failed",
      label: "Failed emails, last 7 days",
      value: kpis?.failed_emails_7d,
      hint: "Show failed emails from the last 7 days",
      tone: kpis && kpis.failed_emails_7d > 0 ? "bad" : undefined,
    },
  ];

  return (
    <ul className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="This month at a glance">
      {cards.map((card) => {
        const pressed = active === card.key;
        const valueColor = card.tone === "bad" ? "text-danger" : card.tone === "warn" ? "text-warn-ink" : "text-ink";
        return (
          <li key={card.key}>
            <button
              type="button"
              onClick={() => onPick(card.key)}
              aria-pressed={pressed}
              title={card.hint}
              className={`h-full w-full rounded-xl border bg-surface p-4 text-left transition-colors hover:border-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent ${
                pressed ? "border-accent ring-1 ring-accent" : "border-hair"
              }`}
            >
              <span className="block text-xs text-muted">{card.label}</span>
              {card.value === undefined ? (
                <span aria-hidden className="mt-2 block h-7 w-16 animate-pulse rounded bg-well" />
              ) : (
                <span className={`mt-1 block font-display text-2xl font-semibold tabular-nums ${valueColor}`}>
                  {card.value.toLocaleString("en-US")}
                </span>
              )}
              <span className="sr-only">. {card.hint}.</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
