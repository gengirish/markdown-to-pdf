"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
  toApiError,
  type SubscriptionSummary,
  type Tier,
  type UsageMeter,
  type UsageSummary,
} from "@/lib/api";
import { useCertForge } from "@/lib/use-api";
import { buttonClass, ErrorNote, Eyebrow, formatDate, Skeleton } from "./ui";

/** The subscription states that keep a paid tier — mirrors `GRANTING` in
 *  `api/services/billing.py`. `on_hold` and `past_due` are Dodo's retry
 *  window after a failed renewal: still paid-for, but about to not be. */
const GRANTING = new Set(["active", "on_hold", "past_due"]);

/** How long to wait for the webhook after Dodo sends the browser back.
 *  Usually seconds; past this the card says so instead of spinning forever. */
const CONFIRM_POLL_MS = 3000;
const CONFIRM_POLL_TRIES = 20;

const INR = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

/** Where a return from Dodo's hosted checkout stands. The return itself
 *  proves nothing — only the signed webhook moves the tier — so a successful
 *  return starts `waiting`, and only a subscription the API reports as live
 *  turns it into `confirmed`. */
type CheckoutReturn = "none" | "waiting" | "confirmed" | "timeout" | "failed";

export function PlanCard({ slug }: { slug: string }) {
  const api = useCertForge();
  const searchParams = useSearchParams();
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tiers, setTiers] = useState<Tier[] | null>(null);
  const [busy, setBusy] = useState<"checkout" | "portal" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  // Dodo appends `status=success|failed` to the return URL we gave it.
  const [checkoutReturn, setCheckoutReturn] = useState<CheckoutReturn>(() =>
    searchParams.get("checkout") !== "complete"
      ? "none"
      : searchParams.get("status") === "failed"
        ? "failed"
        : "waiting",
  );

  const load = useCallback(
    (signal?: AbortSignal) =>
      api
        .getUsage(slug, signal)
        .then((result) => {
          setUsage(result);
          setError(null);
          return result;
        })
        .catch((err) => {
          if (signal?.aborted) return null;
          setError(toApiError(err).message);
          return null;
        }),
    [api, slug],
  );

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    // The price on the button comes from the same catalog the API sells
    // from, never a literal here. A failed catalog load hides the offer
    // rather than inventing a price.
    api
      .listTiers(controller.signal)
      .then(setTiers)
      .catch(() => {
        if (!controller.signal.aborted) setTiers([]);
      });
    return () => controller.abort();
  }, [api, load]);

  // Back from checkout: poll until the webhook has landed, or give up and
  // say so. Polling stops the moment the subscription reads as live.
  useEffect(() => {
    if (checkoutReturn !== "waiting") return;
    const controller = new AbortController();
    let tries = 0;
    const timer = window.setInterval(async () => {
      tries += 1;
      const result = await load(controller.signal);
      if (isLive(result?.subscription ?? null)) {
        setCheckoutReturn("confirmed");
      } else if (tries >= CONFIRM_POLL_TRIES) {
        setCheckoutReturn("timeout");
      }
    }, CONFIRM_POLL_MS);
    return () => {
      window.clearInterval(timer);
      controller.abort();
    };
  }, [checkoutReturn, load]);

  // A settled return drops Dodo's parameters, so a reload does not replay it.
  // `timeout` keeps them: reloading then should wait again, which is right.
  useEffect(() => {
    if (checkoutReturn !== "confirmed" && checkoutReturn !== "failed") return;
    const next = new URLSearchParams(window.location.search);
    for (const key of ["checkout", "status", "session_id", "subscription_id", "payment_id"]) {
      next.delete(key);
    }
    // The dashboard opens this tab *because* `checkout` is present; without
    // pinning it, dropping the parameter would switch tabs under the
    // confirmation the viewer is reading.
    if (!next.has("tab")) next.set("tab", "plan");
    window.history.replaceState(null, "", `?${next.toString()}`);
  }, [checkoutReturn]);

  async function upgrade(tier: Tier) {
    setBusy("checkout");
    setActionError(null);
    try {
      const session = await api.startCheckout(slug, tier.key);
      // Leaving the page: `busy` stays set so the button cannot be pressed
      // twice while the browser navigates.
      window.location.assign(session.checkout_url);
    } catch (err) {
      setBusy(null);
      const apiError = toApiError(err);
      setActionError(actionMessage(apiError.status, apiError.type, apiError.message));
      if (apiError.type === "already_subscribed") load();
    }
  }

  async function manageBilling() {
    setBusy("portal");
    setActionError(null);
    try {
      const { portal_url } = await api.openBillingPortal(slug);
      window.location.assign(portal_url);
    } catch (err) {
      setBusy(null);
      const apiError = toApiError(err);
      setActionError(actionMessage(apiError.status, apiError.type, apiError.message));
    }
  }

  const subscription = usage?.subscription ?? null;
  const currentPrice = tiers?.find((tier) => tier.name === usage?.tier_name)?.price_paise ?? 0;
  // Checkout is refused (409) while a live subscription that is not winding
  // down exists, so the offer is withheld in exactly that case.
  const canCheckout = !(isLive(subscription) && !subscription?.cancel_at_period_end);
  const offers = canCheckout ? (tiers ?? []).filter((tier) => tier.price_paise > currentPrice) : [];

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
          {subscription ? <SubscriptionLine subscription={subscription} tierName={usage?.tier_name} /> : null}
        </div>

        <CheckoutReturnNote state={checkoutReturn} tierName={usage?.tier_name} />

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
            <MeterRow label="CSV uploads this month" meter={usage.csv_batches} />
            <MeterRow label="Design readings this month" meter={usage.vision_imports} />
          </div>
        ) : null}

        {usage && checkoutReturn !== "waiting" ? (
          <div className="space-y-3 border-t border-hair pt-5">
            {offers.map((tier) => (
              <div key={tier.key} className="space-y-2">
                <button
                  type="button"
                  onClick={() => upgrade(tier)}
                  disabled={busy !== null}
                  className={`w-full ${buttonClass("primary")}`}
                >
                  {busy === "checkout"
                    ? "Opening checkout…"
                    : `Upgrade to ${tier.name} — ${INR.format(tier.price_paise / 100)}/month`}
                </button>
                <p className="text-xs leading-relaxed text-faint">
                  {tier.tagline} Paid through Dodo Payments; GST is added at checkout. Your plan
                  changes as soon as the payment is confirmed.
                </p>
              </div>
            ))}

            {subscription?.manageable ? (
              <button
                type="button"
                onClick={manageBilling}
                disabled={busy !== null}
                className={`w-full ${buttonClass("secondary")}`}
              >
                {busy === "portal" ? "Opening billing…" : "Manage billing"}
              </button>
            ) : null}

            {actionError ? <ErrorNote>{actionError}</ErrorNote> : null}

            <p className="text-sm leading-relaxed text-muted">
              <Link href="/pricing" className="text-accent no-underline hover:underline">
                Compare the plans
              </Link>
              {subscription?.manageable
                ? ". Card, invoices and cancellation are in billing."
                : "."}
            </p>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function isLive(subscription: SubscriptionSummary | null): boolean {
  return Boolean(subscription?.status && GRANTING.has(subscription.status));
}

/** The API's own messages are written for people; these are the refusals
 *  that need the viewer's situation spelled out instead. */
function actionMessage(status: number, type: string, message: string): string {
  if (status === 403) return "Only the organization's owner can change its plan or billing.";
  if (type === "already_subscribed") {
    return "This organization already has an active subscription. Use Manage billing to change it.";
  }
  if (type === "no_billing_account") return "There is no billing account yet — subscribe to a plan first.";
  return message;
}

function SubscriptionLine({
  subscription,
  tierName,
}: {
  subscription: SubscriptionSummary;
  tierName: string | undefined;
}) {
  const until = subscription.current_period_end ? formatDate(subscription.current_period_end) : null;

  if (!isLive(subscription)) {
    return (
      <p className="mt-2 text-sm leading-relaxed text-muted">
        Your last subscription has ended{subscription.status ? ` (${subscription.status})` : ""}.
      </p>
    );
  }
  if (subscription.status === "on_hold" || subscription.status === "past_due") {
    return (
      <p className="mt-3 rounded-lg border border-warn-line bg-warn-wash px-4 py-3 text-sm leading-relaxed text-warn-ink">
        The last renewal payment did not go through. Dodo is retrying it; update your card in
        billing to keep {tierName ?? "your plan"}.
      </p>
    );
  }
  if (subscription.cancel_at_period_end) {
    return (
      <p className="mt-2 text-sm leading-relaxed text-muted">
        Cancelled. {tierName ?? "Your plan"} stays active{until ? ` until ${until}` : ""}.
      </p>
    );
  }
  return until ? <p className="mt-2 text-sm text-muted">Renews on {until}.</p> : null;
}

function CheckoutReturnNote({
  state,
  tierName,
}: {
  state: CheckoutReturn;
  tierName: string | undefined;
}) {
  if (state === "none") return null;
  if (state === "failed") {
    return <ErrorNote>The payment did not go through, so nothing was charged and your plan is unchanged.</ErrorNote>;
  }
  const copy = {
    waiting: "Checkout finished. Waiting for Dodo to confirm the subscription — this usually takes a few seconds.",
    confirmed: `Confirmed — you are on ${tierName ?? "your new plan"}. Thank you.`,
    timeout:
      "Dodo has not confirmed the subscription yet. Your plan changes the moment it does — refresh in a minute. If you were charged and nothing has changed within the hour, email support@intelliforge.tech.",
  }[state];
  const skin =
    state === "timeout"
      ? "border-warn-line bg-warn-wash text-warn-ink"
      : "border-accent-line bg-accent-wash text-accent";
  return (
    <p role="status" className={`rounded-lg border px-4 py-3 text-sm leading-relaxed ${skin}`}>
      {copy}
    </p>
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
