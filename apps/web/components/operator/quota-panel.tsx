"use client";

import { useEffect, useId, useRef, useState } from "react";

import {
  toApiError,
  type OperatorContact,
  type OperatorOrg,
  type OperatorQuotaDetail,
  type OperatorQuotaResult,
  type OperatorTier,
  type QuotaOverride,
} from "@/lib/api";
import {
  MAX_OVERRIDE,
  MIN_REASON_LENGTH,
  describeHistoryEntry,
  describePlanChange,
  formatAbsolute,
  formatLimit,
  formatRelative,
  isReasonValid,
  planOptions,
} from "@/lib/operator";
import { useCertForge } from "@/lib/use-api";
import { ErrorNote, Eyebrow, Mono, Skeleton, buttonClass, inputClass } from "@/components/dashboard/ui";
import { CloseIcon, CopySlug, Spinner } from "./bits";
import { PlanChangeDialog } from "./plan-change-dialog";

export { formatLimit };

function formatOverride(override: QuotaOverride | null): string {
  return override === null ? "none" : formatLimit(override.limit);
}

/**
 * One org's credential quota: set or remove an override, change its plan,
 * and read the change log. Every write goes back to the API and the panel
 * re-reads the org afterwards, so what it shows is what issuance enforces.
 * Mount with `key={slug}`: a different org is a different form.
 *
 * The two writes each ask for their own reason. They used to share one field
 * above both, so a reason typed for an override could be spent on a plan
 * change — which also silently removed that override.
 */
export function QuotaPanel({
  slug,
  tiers,
  tiersError,
  onChanged,
  onClose,
  onToast,
  onViewEmails,
}: {
  slug: string;
  /** The operator catalog. `null` while loading or if it failed. */
  tiers: OperatorTier[] | null;
  tiersError: string | null;
  onChanged: (org: OperatorOrg) => void;
  onClose: () => void;
  onToast: (message: string) => void;
  /** Switch to the Emails tab, narrowed to this org. */
  onViewEmails: () => void;
}) {
  const api = useCertForge();
  const headingId = useId();
  const closeButton = useRef<HTMLButtonElement>(null);
  const [detail, setDetail] = useState<OperatorQuotaDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  // Move focus into the drawer when it opens, so Esc and Tab start here.
  useEffect(() => {
    closeButton.current?.focus();
  }, []);

  const [limitText, setLimitText] = useState("");
  const [unlimited, setUnlimited] = useState(false);
  const [overrideReason, setOverrideReason] = useState("");
  // Set when the limit asked for is below this month's usage: the next click
  // sends it, after the numbers have been on screen.
  const [confirmBelowUsage, setConfirmBelowUsage] = useState(false);
  const [saving, setSaving] = useState<"save" | "remove" | null>(null);
  const [overrideError, setOverrideError] = useState<string | null>(null);

  const [tier, setTier] = useState("");
  const [planTarget, setPlanTarget] = useState<string | null>(null);

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

  // Its own request: contacts come from Clerk, and a Clerk failure should
  // cost this section only, not the quota controls.
  const [contacts, setContacts] = useState<OperatorContact[] | null>(null);
  const [contactsError, setContactsError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    api
      .getOrgContacts(slug, controller.signal)
      .then(setContacts)
      .catch((err) => {
        if (controller.signal.aborted) return;
        setContactsError(toApiError(err).message);
      });
    return () => controller.abort();
  }, [api, slug]);

  const reasonOk = isReasonValid(overrideReason);
  const trimmedReason = overrideReason.trim();
  const parsedLimit = /^\d+$/.test(limitText.trim()) ? Number(limitText.trim()) : null;
  const limitOk = unlimited || (parsedLimit !== null && parsedLimit <= MAX_OVERRIDE);
  const requestedLimit = unlimited ? null : parsedLimit;

  async function runOverride(kind: "save" | "remove", action: () => Promise<OperatorQuotaResult>, describe: (r: OperatorQuotaResult) => string) {
    setSaving(kind);
    setOverrideError(null);
    try {
      const result = await action();
      onToast(describe(result));
      setOverrideReason("");
      setConfirmBelowUsage(false);
      onChanged(result);
      setReloadToken((current) => current + 1);
    } catch (err) {
      setOverrideError(toApiError(err).message);
    } finally {
      setSaving(null);
    }
  }

  function saveOverride() {
    if (!detail || !limitOk || !reasonOk) return;
    if (requestedLimit !== null && requestedLimit < detail.used && !confirmBelowUsage) {
      setConfirmBelowUsage(true);
      return;
    }
    void runOverride(
      "save",
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
    void runOverride(
      "remove",
      () => api.clearCredentialQuota(slug, trimmedReason),
      (result) =>
        result.changed
          ? `Override removed. ${result.name} follows the ${result.tier_name} plan's ${formatLimit(result.effective)} again.`
          : "This org had no override. Nothing changed.",
    );
  }

  const options = detail && tiers ? planOptions(tiers, detail) : [];
  const diff = detail && tiers && planTarget ? describePlanChange(detail, planTarget, tiers) : null;
  const tierName = (key: string) => tiers?.find((t) => t.key === key)?.name ?? key;
  const busy = saving !== null;
  // Owners come first from the API; fall back to any member with an email.
  const ownerEmail =
    contacts?.find((c) => c.role === "owner" && c.email)?.email ?? contacts?.find((c) => c.email)?.email ?? null;

  return (
    <aside
      aria-labelledby={headingId}
      className="h-full overflow-y-auto border-hair bg-surface p-6 shadow-[var(--cf-shadow-card)] lg:h-auto lg:overflow-visible lg:rounded-xl lg:border"
    >
      <div className="mb-5 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <Eyebrow>Organization</Eyebrow>
          <h2 id={headingId} className="mt-2 truncate font-display text-xl font-semibold tracking-[-0.02em] text-ink">
            {detail?.name ?? "Loading…"}
          </h2>
          <div className="flex min-w-0 items-center gap-1">
            <Mono className="truncate text-xs text-faint">{slug}</Mono>
            <CopySlug slug={slug} />
          </div>
        </div>
        <button
          ref={closeButton}
          type="button"
          onClick={onClose}
          aria-label="Close organization panel"
          title="Close (Esc)"
          className="rounded-lg p-2 text-muted transition-colors hover:bg-well hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
        >
          <CloseIcon />
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
            <Fact
              label="Used this month"
              value={
                detail.used.toLocaleString("en-US") +
                (detail.usage_percent === null ? "" : ` (${Math.round(detail.usage_percent)}%)`)
              }
            />
            <Fact label="All-time credentials" value={detail.credentials_all_time.toLocaleString("en-US")} />
            <Fact
              label="Last activity"
              value={formatRelative(detail.last_activity_at)}
              title={formatAbsolute(detail.last_activity_at) || undefined}
            />
            <Fact label="Members" value={detail.member_count.toLocaleString("en-US")} />
            <Fact
              label="Created"
              value={detail.created_at ? new Date(detail.created_at).toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" }) : "—"}
              title={formatAbsolute(detail.created_at) || undefined}
            />
          </dl>

          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={onViewEmails} className={buttonClass("secondary", "sm")}>
              View this org&apos;s emails
            </button>
            {ownerEmail ? (
              <a
                href={`mailto:${ownerEmail}?subject=${encodeURIComponent(`CertForge: ${detail.name}`)}`}
                className={buttonClass("secondary", "sm")}
              >
                Email owner
              </a>
            ) : (
              <button
                type="button"
                disabled
                title={contacts === null && !contactsError ? "Loading contacts…" : "No owner email on file"}
                className={buttonClass("secondary", "sm")}
              >
                Email owner
              </button>
            )}
          </div>

          <section>
            <Eyebrow tone="muted">Contacts</Eyebrow>
            {contactsError ? (
              <p className="mt-3 text-sm text-danger">Contacts unavailable: {contactsError}</p>
            ) : contacts === null ? (
              <div className="mt-3">
                <Skeleton rows={1} />
              </div>
            ) : contacts.length === 0 ? (
              <p className="mt-3 text-sm text-faint">This org has no members.</p>
            ) : (
              <ul className="mt-3 space-y-3">
                {contacts.map((contact) => (
                  <li key={contact.clerk_user_id} className="text-sm">
                    <div className="text-ink">
                      {contact.name ?? <span className="text-faint">No name</span>}
                      <span className="ml-2 text-faint">· {contact.role}</span>
                    </div>
                    {contact.found ? (
                      <div className="mt-0.5 flex flex-wrap gap-x-4 gap-y-0.5">
                        {contact.email ? (
                          <a href={`mailto:${contact.email}`} className="break-all text-accent underline-offset-2 hover:underline">
                            {contact.email}
                          </a>
                        ) : (
                          <span className="text-faint">No email on file</span>
                        )}
                        {/* No phone is the common case; saying so on every row is noise. */}
                        {contact.phone ? (
                          <a href={`tel:${contact.phone}`} className="font-mono text-accent underline-offset-2 hover:underline">
                            {contact.phone}
                          </a>
                        ) : null}
                      </div>
                    ) : (
                      <div className="mt-0.5 text-faint">
                        Not found in Clerk · <Mono>{contact.clerk_user_id}</Mono>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="space-y-3" aria-label="Credential override">
            <Eyebrow tone="muted">Credential override</Eyebrow>
            <div className="flex flex-wrap items-center gap-3">
              <input
                type="number"
                inputMode="numeric"
                min={0}
                max={MAX_OVERRIDE}
                step={1}
                value={unlimited ? "" : limitText}
                disabled={unlimited || busy}
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
                  disabled={busy}
                  onChange={(event) => {
                    setUnlimited(event.target.checked);
                    setConfirmBelowUsage(false);
                  }}
                  className="accent-[var(--cf-accent)]"
                />
                Unlimited
              </label>
            </div>
            {!unlimited && limitText.trim() !== "" && !limitOk ? (
              <p className="text-xs text-danger">
                A whole number from 0 to {MAX_OVERRIDE.toLocaleString("en-US")}.
              </p>
            ) : null}

            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-ink">Reason for this override</span>
              <textarea
                value={overrideReason}
                onChange={(event) => {
                  setOverrideReason(event.target.value);
                  setConfirmBelowUsage(false);
                }}
                rows={2}
                maxLength={1000}
                disabled={busy}
                placeholder="Why, for whoever asks in six months."
                className={`${inputClass} disabled:bg-well disabled:text-muted`}
              />
              <span className="mt-1 block text-xs text-faint">
                At least {MIN_REASON_LENGTH} characters. Saved in the change log with your user id.
              </span>
            </label>

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
                className={`${buttonClass("primary", "sm")} gap-2`}
              >
                {saving === "save" ? <Spinner /> : null}
                {saving === "save" ? "Saving…" : confirmBelowUsage ? "Confirm and save" : "Save override"}
              </button>
              {detail.override !== null ? (
                <button
                  type="button"
                  onClick={removeOverride}
                  disabled={busy || !reasonOk}
                  className={`${buttonClass("secondary", "sm")} gap-2`}
                >
                  {saving === "remove" ? <Spinner /> : null}
                  {saving === "remove" ? "Removing…" : "Remove override"}
                </button>
              ) : null}
            </div>
            {overrideError ? <ErrorNote>{overrideError}</ErrorNote> : null}
          </section>

          <section className="space-y-3" aria-label="Plan">
            <Eyebrow tone="muted">Plan</Eyebrow>
            {tiersError ? (
              <p className="text-sm text-danger">Plan catalog unavailable: {tiersError}</p>
            ) : tiers === null ? (
              <Skeleton rows={1} />
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <select
                    value={tier}
                    onChange={(event) => setTier(event.target.value)}
                    aria-label="Plan"
                    className={`${inputClass} max-w-64`}
                  >
                    {options.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => setPlanTarget(tier)}
                    disabled={busy || tier === detail.tier}
                    className={buttonClass("secondary", "sm")}
                  >
                    Change plan
                  </button>
                </div>
                <p className="text-xs text-faint">
                  You confirm the change and give a reason next. No payment is taken.
                </p>
              </>
            )}
          </section>

          <section>
            <Eyebrow tone="muted">History</Eyebrow>
            {detail.history.length === 0 ? (
              <p className="mt-3 text-sm text-faint">
                Changes to plan or override will appear here with who made them and why.
              </p>
            ) : (
              <ol className="mt-3 space-y-3">
                {detail.history.map((change, index) => (
                  <li key={`${change.created_at}-${change.actor}-${index}`} className="border-l-2 border-hair pl-3 text-sm">
                    <div className="text-ink">
                      {describeHistoryEntry(change, tierName)}
                      <span className="text-faint">
                        {" "}· enforced {formatLimit(change.effective_before)} → {formatLimit(change.effective_after)}
                      </span>
                    </div>
                    <div className="mt-0.5 break-words text-muted">{change.reason}</div>
                    <div className="mt-0.5 text-xs text-faint">
                      {new Date(change.created_at).toLocaleString("en-US")} · <Mono>{change.actor}</Mono>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>

          <PlanChangeDialog
            slug={slug}
            orgName={detail.name}
            targetTier={diff?.changed ? planTarget : null}
            diff={diff?.changed ? diff : null}
            onCancel={() => setPlanTarget(null)}
            onDone={(result) => {
              setPlanTarget(null);
              onToast(
                result.changed
                  ? `${result.name} moved from ${tierName(result.previous_tier)} to ${result.tier_name}.` +
                      (result.override_cleared ? " Its credential override was removed." : "")
                  : "The org is already on that plan. Nothing changed.",
              );
              onChanged(result);
              setReloadToken((current) => current + 1);
            }}
          />
        </div>
      ) : null}
    </aside>
  );
}

function Fact({
  label,
  value,
  strong = false,
  title,
}: {
  label: string;
  value: string;
  strong?: boolean;
  title?: string;
}) {
  return (
    <div>
      <dt className="text-faint">{label}</dt>
      <dd title={title} className={`font-mono ${strong ? "font-semibold text-ink" : "text-ink"}`}>
        {value}
      </dd>
    </div>
  );
}
