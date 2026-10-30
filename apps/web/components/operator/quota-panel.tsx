"use client";

import { useEffect, useState } from "react";

import {
  toApiError,
  type OperatorOrg,
  type OperatorQuotaDetail,
  type QuotaOverride,
  type Tier,
} from "@/lib/api";
import { useCertForge } from "@/lib/use-api";
import { ErrorNote, Eyebrow, Mono, Skeleton, buttonClass, inputClass } from "@/components/dashboard/ui";

/** Mirrors `services/plans.py`; the API enforces both, these only save a round trip. */
const MIN_REASON_LENGTH = 10;
const MAX_OVERRIDE = 1_000_000;

export function formatLimit(limit: number | null): string {
  return limit === null ? "Unlimited" : limit.toLocaleString("en-US");
}

function formatOverride(override: QuotaOverride | null): string {
  return override === null ? "none" : formatLimit(override.limit);
}

/**
 * One org's credential quota: set or remove an override, change its plan,
 * and read the change log. Every write goes back to the API and the panel
 * re-reads the org afterwards, so what it shows is what issuance enforces.
 * Mount with `key={slug}`: a different org is a different form.
 */
export function QuotaPanel({
  slug,
  tiers,
  onChanged,
  onClose,
}: {
  slug: string;
  /** `null` while loading or if the catalog failed; the plan control hides. */
  tiers: Tier[] | null;
  onChanged: (org: OperatorOrg) => void;
  onClose: () => void;
}) {
  const api = useCertForge();
  const [detail, setDetail] = useState<OperatorQuotaDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const [limitText, setLimitText] = useState("");
  const [unlimited, setUnlimited] = useState(false);
  const [tier, setTier] = useState("");
  const [reason, setReason] = useState("");
  // Set when the limit asked for is below this month's usage: the next click
  // sends it, after the numbers have been on screen.
  const [confirmBelowUsage, setConfirmBelowUsage] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoadError(null);
    api
      .getCredentialQuota(slug, controller.signal)
      .then((data) => {
        setDetail(data);
        setLimitText(data.override && data.override.limit !== null ? String(data.override.limit) : "");
        setUnlimited(data.override !== null && data.override.limit === null);
        setTier(data.tier);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setLoadError(toApiError(err).message);
      });
    return () => controller.abort();
  }, [api, slug, reloadToken]);

  const trimmedReason = reason.trim();
  const reasonOk = trimmedReason.length >= MIN_REASON_LENGTH;
  const parsedLimit = /^\d+$/.test(limitText.trim()) ? Number(limitText.trim()) : null;
  const limitOk = unlimited || (parsedLimit !== null && parsedLimit <= MAX_OVERRIDE);
  const requestedLimit = unlimited ? null : parsedLimit;

  async function run<T extends OperatorOrg>(action: () => Promise<T>, describe: (result: T) => string) {
    setBusy(true);
    setActionError(null);
    setNotice(null);
    try {
      const result = await action();
      setNotice(describe(result));
      setReason("");
      setConfirmBelowUsage(false);
      onChanged(result);
      setReloadToken((current) => current + 1);
    } catch (err) {
      setActionError(toApiError(err).message);
    } finally {
      setBusy(false);
    }
  }

  function saveOverride() {
    if (!detail || !limitOk || !reasonOk) return;
    if (requestedLimit !== null && requestedLimit < detail.used && !confirmBelowUsage) {
      setConfirmBelowUsage(true);
      return;
    }
    void run(
      () => api.setCredentialQuota(slug, { limit: requestedLimit, reason: trimmedReason }),
      (result) => {
        if (!result.changed) return "That is already this org's override. Nothing changed.";
        const parts = [`Override set. ${result.name} may now issue ${formatLimit(result.effective)} a month.`];
        if (result.over_by) parts.push(`It is ${result.over_by.toLocaleString("en-US")} over, so issuance is stopped until next month.`);
        if (result.note) parts.push(result.note);
        return parts.join(" ");
      },
    );
  }

  function removeOverride() {
    if (!reasonOk) return;
    void run(
      () => api.clearCredentialQuota(slug, trimmedReason),
      (result) =>
        result.changed
          ? `Override removed. ${result.name} follows the ${result.tier_name} plan's ${formatLimit(result.effective)} again.`
          : "This org had no override. Nothing changed.",
    );
  }

  function changePlan() {
    if (!detail || !reasonOk || !tier || tier === detail.tier) return;
    void run(
      () => api.setOrgTier(slug, { tier, reason: trimmedReason }),
      (result) =>
        result.changed
          ? `Moved from ${result.previous_tier} to ${result.tier_name}.` +
            (result.override_cleared ? " Its credential override was removed." : "")
          : "The org is already on that plan. Nothing changed.",
    );
  }

  return (
    <aside className="rounded-xl border border-hair bg-surface p-6 shadow-[var(--cf-shadow-card)]">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <Eyebrow>Organization</Eyebrow>
          <h2 className="mt-2 truncate font-display text-xl font-semibold tracking-[-0.02em] text-ink">
            {detail?.name ?? slug}
          </h2>
          <Mono className="text-xs text-faint">{slug}</Mono>
        </div>
        <button type="button" onClick={onClose} className={buttonClass("quiet", "sm")}>
          Close
        </button>
      </div>

      {loadError ? <ErrorNote>{loadError}</ErrorNote> : null}
      {!detail && !loadError ? <Skeleton rows={4} /> : null}

      {detail ? (
        <div className="space-y-6">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            <Fact label="Plan" value={detail.tier_known ? detail.tier_name : `${detail.tier} (unknown, read as ${detail.tier_name})`} />
            <Fact label="Plan quota" value={formatLimit(detail.tier_quota)} />
            <Fact label="Override" value={formatOverride(detail.override)} />
            <Fact label="Enforced" value={formatLimit(detail.effective)} strong />
            <Fact label="Used this month" value={detail.used.toLocaleString("en-US")} />
          </dl>

          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-ink">Reason</span>
            <textarea
              value={reason}
              onChange={(event) => {
                setReason(event.target.value);
                setConfirmBelowUsage(false);
              }}
              rows={2}
              maxLength={1000}
              placeholder="Why, for whoever asks in six months. Required for every change."
              className={inputClass}
            />
            <span className="mt-1 block text-xs text-faint">
              At least {MIN_REASON_LENGTH} characters. Saved in the change log with your user id.
            </span>
          </label>

          <section className="space-y-3">
            <Eyebrow tone="muted">Credential override</Eyebrow>
            <div className="flex flex-wrap items-center gap-3">
              <input
                type="number"
                inputMode="numeric"
                min={0}
                max={MAX_OVERRIDE}
                step={1}
                value={unlimited ? "" : limitText}
                disabled={unlimited}
                onChange={(event) => {
                  setLimitText(event.target.value);
                  setConfirmBelowUsage(false);
                }}
                placeholder="e.g. 1000"
                aria-label="Monthly credential limit"
                className={`${inputClass} max-w-40 disabled:bg-well disabled:text-muted`}
              />
              <label className="inline-flex items-center gap-2 text-sm text-ink">
                <input
                  type="checkbox"
                  checked={unlimited}
                  onChange={(event) => {
                    setUnlimited(event.target.checked);
                    setConfirmBelowUsage(false);
                  }}
                  className="accent-[var(--cf-accent)]"
                />
                Unlimited
              </label>
            </div>
            <p className="text-xs text-faint">A plan change removes this limit.</p>
            {!unlimited && limitText.trim() !== "" && !limitOk ? (
              <p className="text-xs text-danger">
                A whole number from 0 to {MAX_OVERRIDE.toLocaleString("en-US")}.
              </p>
            ) : null}

            {confirmBelowUsage && requestedLimit !== null ? (
              <p role="alert" className="rounded-lg border border-warn-line bg-warn-wash px-4 py-3 text-sm text-warn-ink">
                {detail.name} has already issued {detail.used.toLocaleString("en-US")} this month. A limit of{" "}
                {requestedLimit.toLocaleString("en-US")} stops all issuance until next month. Click again to confirm.
              </p>
            ) : null}

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={saveOverride}
                disabled={busy || !limitOk || !reasonOk}
                className={buttonClass("primary", "sm")}
              >
                {confirmBelowUsage ? "Confirm and save" : "Save override"}
              </button>
              {detail.override !== null ? (
                <button
                  type="button"
                  onClick={removeOverride}
                  disabled={busy || !reasonOk}
                  className={buttonClass("secondary", "sm")}
                >
                  Remove override
                </button>
              ) : null}
            </div>
          </section>

          {tiers && tiers.length > 0 ? (
            <section className="space-y-3">
              <Eyebrow tone="muted">Plan</Eyebrow>
              <div className="flex flex-wrap items-center gap-2">
                <select
                  value={tier}
                  onChange={(event) => setTier(event.target.value)}
                  aria-label="Plan"
                  className={`${inputClass} max-w-48`}
                >
                  {detail.tier_known ? null : <option value={detail.tier}>{detail.tier} (unknown)</option>}
                  {tiers.map((option) => (
                    <option key={option.key} value={option.key}>
                      {option.name} · {formatLimit(option.monthly_quota)}/mo
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={changePlan}
                  disabled={busy || !reasonOk || tier === detail.tier}
                  className={buttonClass("secondary", "sm")}
                >
                  Change plan
                </button>
              </div>
              <p className="text-xs text-faint">
                No payment is taken. Changing the plan removes any credential override.
              </p>
            </section>
          ) : null}

          {actionError ? <ErrorNote>{actionError}</ErrorNote> : null}
          {notice ? (
            <p role="status" className="rounded-lg border border-accent-line bg-accent-wash px-4 py-3 text-sm text-accent">
              {notice}
            </p>
          ) : null}

          <section>
            <Eyebrow tone="muted">History</Eyebrow>
            {detail.history.length === 0 ? (
              <p className="mt-3 text-sm text-faint">No changes have been made to this org&apos;s override.</p>
            ) : (
              <ol className="mt-3 space-y-3">
                {detail.history.map((change) => (
                  <li key={`${change.created_at}-${change.actor}`} className="border-l-2 border-hair pl-3 text-sm">
                    <div className="text-ink">
                      Override {formatOverride(change.previous_override)} → {formatOverride(change.new_override)}
                      <span className="text-faint">
                        {" "}· enforced {formatLimit(change.effective_before)} → {formatLimit(change.effective_after)}
                      </span>
                    </div>
                    <div className="mt-0.5 text-muted">{change.reason}</div>
                    <div className="mt-0.5 text-xs text-faint">
                      {new Date(change.created_at).toLocaleString("en-US")} · <Mono>{change.actor}</Mono>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>
      ) : null}
    </aside>
  );
}

function Fact({ label, value, strong = false }: { label: string; value: string; strong?: boolean }) {
  return (
    <div>
      <dt className="text-faint">{label}</dt>
      <dd className={`font-mono ${strong ? "font-semibold text-ink" : "text-ink"}`}>{value}</dd>
    </div>
  );
}
