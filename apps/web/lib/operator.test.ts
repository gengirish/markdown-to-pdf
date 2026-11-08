import { test } from "node:test";
import assert from "node:assert/strict";

import {
  DEFAULT_PARAMS,
  describeHistoryEntry,
  formatRelative,
  nextSort,
  rangeBounds,
  tabDefaults,
  usagePercent,
  usageTone,
  describePlanChange,
  isReasonValid,
  operatorSearch,
  parseOperatorParams,
  planOptions,
  type OperatorTier,
  type OrgPlanState,
} from "./operator.ts";

// The shape `GET /api/v1/operator/tiers` serves today. Scale is unlisted.
const TIERS: OperatorTier[] = [
  { key: "community", name: "Community", listed: true, monthly_quota: 50 },
  { key: "pro", name: "Pro", listed: true, monthly_quota: 1000 },
  { key: "scale", name: "Scale", listed: false, monthly_quota: null },
];

const onScale: OrgPlanState = {
  tier: "scale",
  tier_name: "Scale",
  tier_known: true,
  tier_quota: null,
  override: null,
  effective: null,
};

const proWithOverride: OrgPlanState = {
  tier: "pro",
  tier_name: "Pro",
  tier_known: true,
  tier_quota: 1000,
  override: { limit: 5000 },
  effective: 5000,
};

/** What a `<select value={current.tier}>` shows: the option whose value
 *  matches, or — when none does — the first one. */
function selectedLabel(options: { value: string; label: string }[], value: string): string {
  return (options.find((option) => option.value === value) ?? options[0]).label;
}

test("an org on Scale renders with Scale selected", () => {
  const options = planOptions(TIERS, onScale);
  assert.ok(options.some((option) => option.value === "scale"));
  assert.equal(selectedLabel(options, onScale.tier), "Scale · Unlimited (not sold)");
});

test("the public catalog alone would have shown Community for a Scale org", () => {
  // The regression this file guards: without Scale in the list, the browser
  // falls back to the first option.
  const publicCatalog = TIERS.filter((tier) => tier.listed);
  const options = planOptions(publicCatalog, onScale);
  // planOptions adds the missing tier rather than letting the select fall back.
  assert.equal(options[0].value, "scale");
  assert.notEqual(selectedLabel(options, onScale.tier), "Community · 50/mo");
});

test("an unknown stored tier is still an option, and selected", () => {
  const legacy = { ...onScale, tier: "enterprise", tier_name: "Community", tier_known: false };
  const options = planOptions(TIERS, legacy);
  assert.equal(selectedLabel(options, "enterprise"), "enterprise (unknown)");
});

test("saving the current plan is a no-op", () => {
  const diff = describePlanChange(onScale, "scale", TIERS);
  assert.ok(diff);
  assert.equal(diff.changed, false);
  assert.equal(diff.removesOverride, null);
});

test("the diff reads before → after", () => {
  const diff = describePlanChange(onScale, "pro", TIERS);
  assert.ok(diff);
  assert.equal(diff.changed, true);
  assert.equal(`${diff.before} → ${diff.after}`, "Scale · Unlimited → Pro · 1,000/mo");
  assert.equal(diff.enforcedBefore, null);
  assert.equal(diff.enforcedAfter, 1000);
  assert.equal(diff.removesOverride, null);
});

test("a plan change names the override it will remove", () => {
  const diff = describePlanChange(proWithOverride, "community", TIERS);
  assert.ok(diff);
  assert.deepEqual(diff.removesOverride, { limit: 5000 });
  assert.equal(diff.enforcedBefore, 5000);
  assert.equal(diff.enforcedAfter, 50);
});

test("an unlimited override is reported as one, not as no override", () => {
  const diff = describePlanChange({ ...proWithOverride, override: { limit: null }, effective: null }, "scale", TIERS);
  assert.ok(diff);
  assert.deepEqual(diff.removesOverride, { limit: null });
});

test("a target outside the catalog has no diff", () => {
  assert.equal(describePlanChange(onScale, "enterprise", TIERS), null);
});

test("a reason needs ten characters after trimming", () => {
  assert.equal(isReasonValid("too short"), false);
  assert.equal(isReasonValid("   padded    "), false);
  assert.equal(isReasonValid("ticket #4521"), true);
});

test("history names plans for a plan change and overrides for an override change", () => {
  const name = (key: string) => TIERS.find((tier) => tier.key === key)?.name ?? key;
  assert.equal(
    describeHistoryEntry({ previous_override: null, new_override: null, previous_tier: "scale", new_tier: "pro" }, name),
    "Plan Scale → Pro",
  );
  assert.equal(
    describeHistoryEntry({ previous_override: { limit: 900 }, new_override: null, previous_tier: "pro", new_tier: "community" }, name),
    "Plan Pro → Community, override 900 → none",
  );
  assert.equal(
    describeHistoryEntry({ previous_override: null, new_override: { limit: null } }, name),
    "Override none → Unlimited",
  );
});

test("usage percent mirrors the API: unlimited is null, a 0 limit is 100%", () => {
  assert.equal(usagePercent(40, 50), 80);
  assert.equal(usagePercent(5, null), null);
  assert.equal(usagePercent(0, 0), 100);
  assert.equal(usagePercent(1200, 1000), 120);
});

test("the usage bar is neutral, amber at 80%, red at 100%, absent when unlimited", () => {
  assert.equal(usageTone(null), null);
  assert.equal(usageTone(0), "neutral");
  assert.equal(usageTone(79.9), "neutral");
  assert.equal(usageTone(80), "warn");
  assert.equal(usageTone(99.9), "warn");
  assert.equal(usageTone(100), "bad");
  assert.equal(usageTone(140), "bad");
});

test("relative time", () => {
  const now = new Date("2026-11-08T12:00:00Z");
  assert.equal(formatRelative(null, now), "Never");
  assert.equal(formatRelative("2026-11-08T11:59:30Z", now), "just now");
  assert.equal(formatRelative("2026-11-08T11:15:00Z", now), "45 min ago");
  assert.equal(formatRelative("2026-11-08T07:00:00Z", now), "5 h ago");
  assert.equal(formatRelative("2026-11-07T12:00:00Z", now), "1 day ago");
  assert.equal(formatRelative("2026-11-01T12:00:00Z", now), "7 days ago");
});

test("date range presets", () => {
  const now = new Date("2026-11-08T12:00:00Z");
  assert.deepEqual(rangeBounds("all", null, null, now), { since: null, until: null });
  assert.equal(rangeBounds("24h", null, null, now).since, "2026-11-07T12:00:00.000Z");
  assert.equal(rangeBounds("7d", null, null, now).since, "2026-11-01T12:00:00.000Z");
  assert.equal(rangeBounds("30d", null, null, now).since, "2026-10-09T12:00:00.000Z");
  const custom = rangeBounds("custom", "2026-11-01", "2026-11-03", now);
  assert.ok(custom.since && custom.until && custom.since < custom.until);
  assert.deepEqual(rangeBounds("custom", "bogus", null, now), { since: null, until: null });
});

test("sortable headers: a new column starts descending, the same one flips", () => {
  assert.deepEqual(nextSort("usage", "desc", "name"), { sort: "name", dir: "desc" });
  assert.deepEqual(nextSort("name", "desc", "name"), { sort: "name", dir: "asc" });
  assert.deepEqual(nextSort("name", "asc", "name"), { sort: "name", dir: "desc" });
});

test("URL state round-trips and defaults are omitted", () => {
  const emails = parseOperatorParams(new URLSearchParams("tab=emails&org=acme-1&status=failed"));
  assert.equal(emails.tab, "emails");
  assert.equal(emails.org, "acme-1");
  assert.equal(emails.status, "failed");
  assert.equal(operatorSearch(emails), "?tab=emails&org=acme-1&status=failed");
  assert.equal(operatorSearch(DEFAULT_PARAMS), "");
  assert.equal(operatorSearch(tabDefaults("emails")), "?tab=emails");

  const full = "tab=emails&status=failed&range=custom&from=2026-11-01&to=2026-11-03&sort=attempts&dir=asc&page=3";
  assert.equal(operatorSearch(parseOperatorParams(new URLSearchParams(full))), `?${full}`);

  const plans = "plan=pro%2Cscale&active=1&near=1&override=1&sort=last_activity&dir=asc";
  const parsed = parseOperatorParams(new URLSearchParams(plans));
  assert.deepEqual(parsed.plans, ["pro", "scale"]);
  assert.equal(parsed.orgSort, "last_activity");
  assert.equal(operatorSearch(parsed), `?${plans}`);
});

test("pasted junk in the URL falls back to defaults", () => {
  const state = parseOperatorParams(
    new URLSearchParams("tab=admin&org=<script>&status=everything&sort=drop&page=-4&plan=<x>,PRO"),
  );
  assert.deepEqual(state, DEFAULT_PARAMS);
  const emails = parseOperatorParams(new URLSearchParams("tab=emails&range=custom&from=yesterday&page=2.5"));
  assert.equal(emails.from, null);
  assert.equal(emails.page, 1);
});

test("each tab reads only its own parameters", () => {
  assert.equal(parseOperatorParams(new URLSearchParams("org=acme&status=failed")).status, "attempted");
  assert.deepEqual(parseOperatorParams(new URLSearchParams("tab=emails&plan=pro&near=1")).plans, []);
});
