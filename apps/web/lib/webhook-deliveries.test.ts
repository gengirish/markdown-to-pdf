import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type { WebhookDeliveryStatus } from "./api.ts";

import {
  DELIVERY_STATUS,
  WEBHOOK_COPY,
  deliveryStatusLabel,
  deliveryTagText,
  isRedeliverable,
  lastDeliveryOf,
  nextTryHint,
  redeliverErrorMessage,
} from "./webhook-deliveries.ts";

test("the card says what webhooks actually do", () => {
  assert.equal(WEBHOOK_COPY.purpose, "Get told when a CSV batch finishes.");
  assert.equal(WEBHOOK_COPY.empty, "No webhook endpoints registered.");
});

const ISSUANCE_PROMISE = /credential is issued|credential\.issued|credential issued/i;

test("no copy promises an event on credential issuance — none is ever sent", () => {
  for (const [key, text] of Object.entries(WEBHOOK_COPY)) {
    assert.doesNotMatch(text, ISSUANCE_PROMISE, key);
  }
});

// The copy object alone is not enough: the old sentence was a literal in the
// component, and it could come back there without touching WEBHOOK_COPY.
test("the developer card neither hardcodes the promise nor drops the real copy", () => {
  const source = readFileSync(
    fileURLToPath(new URL("../components/dashboard/developer-card.tsx", import.meta.url)),
    "utf8",
  );
  assert.doesNotMatch(source, ISSUANCE_PROMISE);
  assert.match(source, /WEBHOOK_COPY\.purpose/);
});

test("every contract status has an exact label and tone", () => {
  assert.deepEqual(DELIVERY_STATUS, {
    pending: { label: "Pending", tone: "neutral" },
    succeeded: { label: "Delivered", tone: "ok" },
    failed: { label: "Failed", tone: "warn" },
    abandoned: { label: "Abandoned", tone: "bad" },
  });
});

test("a status a newer API adds is shown as itself, not guessed", () => {
  assert.deepEqual(deliveryStatusLabel("paused"), { label: "paused", tone: "neutral" });
});

test("the tag carries the response code when there is one", () => {
  assert.equal(deliveryTagText({ status: "failed", last_status_code: 500 }), "Failed · 500");
  assert.equal(deliveryTagText({ status: "succeeded", last_status_code: 204 }), "Delivered · 204");
  assert.equal(deliveryTagText({ status: "failed", last_status_code: null }), "Failed");
});

test("failed, abandoned and stranded-pending deliveries offer Redeliver", () => {
  const now = Date.parse("2026-11-11T12:00:00Z");
  const ago = (min: number) => new Date(now - min * 60_000).toISOString();
  const d = (status: WebhookDeliveryStatus, next_attempt_at: string | null = null) => ({ status, next_attempt_at });
  assert.equal(isRedeliverable(d("failed", ago(-5)), now), true);
  assert.equal(isRedeliverable(d("abandoned"), now), true);
  assert.equal(isRedeliverable(d("succeeded"), now), false);
  // A pending row is only redeliverable once its job is evidently lost.
  assert.equal(isRedeliverable(d("pending", ago(1)), now), false);
  assert.equal(isRedeliverable(d("pending", ago(16)), now), true);
  assert.equal(isRedeliverable(d("pending", null), now), false);
});

test("an old API without last_delivery reads as never sent", () => {
  const base = { id: "w", url: "https://x", events: ["batch.completed"], created_at: "2026-11-11T00:00:00Z" };
  assert.equal(lastDeliveryOf(base), null);
  assert.equal(lastDeliveryOf({ ...base, last_delivery: null }), null);
});

test("next try is a relative, approximate hint", () => {
  const now = Date.parse("2026-11-11T12:00:00Z");
  const at = (s: number) => new Date(now + s * 1000).toISOString();
  assert.equal(nextTryHint(null, now), null);
  assert.equal(nextTryHint("not a date", now), null);
  assert.equal(nextTryHint(at(-30), now), "next try due now");
  assert.equal(nextTryHint(at(20), now), "next try ~in under a minute");
  assert.equal(nextTryHint(at(300), now), "next try ~in 5 min");
  assert.equal(nextTryHint(at(7200), now), "next try ~in 2 h");
  assert.equal(nextTryHint(at(43200 * 2), now), "next try ~in 1 d");
});

test("the late-retry caveat names scale-to-zero", () => {
  assert.equal(
    WEBHOOK_COPY.lateRetryCaveat,
    "Retries can run late: the API scales to zero when idle, so a due retry waits until it next starts.",
  );
});

test("a 409 redeliver gets its own copy; anything else passes through", () => {
  assert.equal(
    redeliverErrorMessage({ type: "delivery_not_redeliverable", message: "x" }),
    WEBHOOK_COPY.notRedeliverable,
  );
  assert.equal(redeliverErrorMessage({ type: "network_error", message: "Network down" }), "Network down");
});
