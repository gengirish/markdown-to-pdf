/**
 * The developer card's webhook-delivery wording and decisions, kept out of the
 * component so `node --test` can pin them (no DOM here).
 *
 * The copy lives here for one reason: the card used to promise "Add one to be
 * told when a credential is issued", and no such event exists — only
 * `batch.completed` is ever sent, from the CSV path. The test fails if that
 * promise comes back.
 */

import type { WebhookDelivery, WebhookDeliveryStatus, WebhookSummary } from "./api.ts";

export const WEBHOOK_COPY = {
  /** What an endpoint is for. Shown whether or not one is registered. */
  purpose: "Get told when a CSV batch finishes.",
  empty: "No webhook endpoints registered.",
  noDeliveries: "No deliveries yet",
  showDeliveries: "Recent deliveries",
  hideDeliveries: "Hide deliveries",
  deliveriesEmpty: "Nothing has been sent to this endpoint yet.",
  redeliver: "Redeliver",
  redelivering: "Redelivering…",
  /** Tooltip on every "next try" hint. Retries are scheduled jobs on a
   *  machine that stops when idle, so a due retry waits for it to wake. */
  lateRetryCaveat:
    "Retries can run late: the API scales to zero when idle, so a due retry waits until it next starts.",
  notRedeliverable:
    "This delivery can no longer be redelivered — it is no longer failed. Refresh to see where it stands.",
} as const;

export type Tone = "ok" | "warn" | "neutral" | "bad";

export const DELIVERY_STATUS: Record<WebhookDeliveryStatus, { label: string; tone: Tone }> = {
  pending: { label: "Pending", tone: "neutral" },
  succeeded: { label: "Delivered", tone: "ok" },
  failed: { label: "Failed", tone: "warn" },
  abandoned: { label: "Abandoned", tone: "bad" },
};

/** Label and tone for a status, including one a newer API might add: shown
 *  as itself, in neutral, rather than guessed at. */
export function deliveryStatusLabel(status: string): { label: string; tone: Tone } {
  return (
    (DELIVERY_STATUS as Record<string, { label: string; tone: Tone }>)[status] ?? {
      label: status,
      tone: "neutral",
    }
  );
}

/** The status tag's text: the label plus the receiver's last response code. */
export function deliveryTagText(delivery: Pick<WebhookDelivery, "status" | "last_status_code">): string {
  const { label } = deliveryStatusLabel(delivery.status);
  return delivery.last_status_code == null ? label : `${label} · ${delivery.last_status_code}`;
}

/** A `pending` row this far past its due time has lost its job (the API has
 *  no sweep), so it may be redelivered. Mirrors the API's threshold. */
export const STRANDED_PENDING_AFTER_MS = 15 * 60 * 1000;

/** Mirrors the API's rule; the API still enforces it with a 409. */
export function isRedeliverable(
  delivery: Pick<WebhookDelivery, "status" | "next_attempt_at">,
  now: number = Date.now(),
): boolean {
  if (delivery.status === "failed" || delivery.status === "abandoned") return true;
  if (delivery.status !== "pending" || !delivery.next_attempt_at) return false;
  const due = Date.parse(delivery.next_attempt_at);
  return Number.isFinite(due) && now - due > STRANDED_PENDING_AFTER_MS;
}

/** An API that predates delivery records omits `last_delivery` entirely;
 *  treat that the same as "never sent". */
export function lastDeliveryOf(webhook: WebhookSummary): WebhookDelivery | null {
  return webhook.last_delivery ?? null;
}

/** "next try ~in 5 min". Null when nothing is scheduled or the date is unreadable. */
export function nextTryHint(nextAttemptAt: string | null, now: number = Date.now()): string | null {
  if (!nextAttemptAt) return null;
  const at = new Date(nextAttemptAt).getTime();
  if (Number.isNaN(at)) return null;
  const seconds = Math.round((at - now) / 1000);
  if (seconds <= 0) return "next try due now";
  if (seconds < 60) return "next try ~in under a minute";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `next try ~in ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `next try ~in ${hours} h`;
  const days = Math.round(hours / 24);
  return `next try ~in ${days} d`;
}

/** Inline error for a refused redeliver; the 409 gets copy that says why. */
export function redeliverErrorMessage(err: { type?: string; message: string }): string {
  return err.type === "delivery_not_redeliverable" ? WEBHOOK_COPY.notRedeliverable : err.message;
}
