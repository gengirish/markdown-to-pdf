/**
 * The operator console's decisions, kept out of the components so they can be
 * tested with `node --test` (no DOM here). Every limit is `null` for
 * unlimited, as on the wire.
 */

/** Mirrors `services/plans.py`; the API enforces both, these only save a round trip. */
export const MIN_REASON_LENGTH = 10;
export const MAX_OVERRIDE = 1_000_000;

/** One plan as `GET /api/v1/operator/tiers` serves it — unlike the public
 *  catalog, this includes hand-sold tiers such as Scale. */
export interface OperatorTier {
  key: string;
  name: string;
  /** False for a tier the pricing page does not sell. Still a real tier. */
  listed: boolean;
  monthly_quota: number | null;
}

export interface QuotaOverrideValue {
  limit: number | null;
}

/** The fields of an org these helpers read; `OperatorOrg` satisfies it. */
export interface OrgPlanState {
  tier: string;
  tier_name: string;
  tier_known: boolean;
  tier_quota: number | null;
  override: QuotaOverrideValue | null;
  effective: number | null;
}

export function formatLimit(limit: number | null): string {
  return limit === null ? "Unlimited" : limit.toLocaleString("en-US");
}

/** "Pro · 1,000/mo", "Scale · Unlimited". */
export function planLabel(name: string, quota: number | null): string {
  return quota === null ? `${name} · Unlimited` : `${name} · ${formatLimit(quota)}/mo`;
}

export function isReasonValid(reason: string): boolean {
  return reason.trim().length >= MIN_REASON_LENGTH;
}

export interface PlanOption {
  value: string;
  label: string;
}

/**
 * The plan control's options: every tier the operator catalog knows, in its
 * order, plus the org's own tier if the catalog does not know it. The org's
 * current tier is therefore always an option, so the `<select>` can always
 * show it as selected — when it was missing (Scale, from the public catalog),
 * the browser fell back to the first option and showed Community instead.
 */
export function planOptions(tiers: OperatorTier[], current: OrgPlanState): PlanOption[] {
  const options = tiers.map((tier) => ({
    value: tier.key,
    label: planLabel(tier.name, tier.monthly_quota) + (tier.listed ? "" : " (not sold)"),
  }));
  if (!tiers.some((tier) => tier.key === current.tier)) {
    options.unshift({ value: current.tier, label: `${current.tier} (unknown)` });
  }
  return options;
}

export interface PlanChangeDiff {
  /** False when the target is the plan the org is already on: nothing to send. */
  changed: boolean;
  /** "Scale · Unlimited" */
  before: string;
  /** "Pro · 1,000/mo" */
  after: string;
  /** The enforced limit either side. */
  enforcedBefore: number | null;
  enforcedAfter: number | null;
  /** The override the change will remove, or null if there is none. */
  removesOverride: QuotaOverrideValue | null;
}

/**
 * What a plan change will do, for the confirmation dialog. Mirrors
 * `change_tier()`: a real change always clears the override, and the
 * enforced limit becomes the new tier's quota. Returns null when the target
 * tier is not in the catalog.
 */
export function describePlanChange(
  org: OrgPlanState,
  targetKey: string,
  tiers: OperatorTier[],
): PlanChangeDiff | null {
  const target = tiers.find((tier) => tier.key === targetKey);
  if (!target) return null;
  const before = planLabel(org.tier_known ? org.tier_name : org.tier, org.tier_quota);
  const after = planLabel(target.name, target.monthly_quota);
  if (targetKey === org.tier) {
    return {
      changed: false,
      before,
      after,
      enforcedBefore: org.effective,
      enforcedAfter: org.effective,
      removesOverride: null,
    };
  }
  return {
    changed: true,
    before,
    after,
    enforcedBefore: org.effective,
    enforcedAfter: target.monthly_quota,
    removesOverride: org.override,
  };
}

/** One change-log row, as `_change()` in `routes/operator.py` serves it. */
export interface HistoryEntry {
  previous_override: QuotaOverrideValue | null;
  new_override: QuotaOverrideValue | null;
  previous_tier?: string | null;
  new_tier?: string | null;
}

function formatOverride(override: QuotaOverrideValue | null): string {
  return override === null ? "none" : formatLimit(override.limit);
}

/** The headline of one History row. A plan change names the plans; an
 *  override change names the overrides; one that did both says both. */
export function describeHistoryEntry(entry: HistoryEntry, tierName: (key: string) => string): string {
  const parts: string[] = [];
  if (entry.previous_tier && entry.new_tier) {
    parts.push(`Plan ${tierName(entry.previous_tier)} → ${tierName(entry.new_tier)}`);
  }
  const overrideChanged =
    formatOverride(entry.previous_override) !== formatOverride(entry.new_override);
  if (overrideChanged || parts.length === 0) {
    parts.push(
      `${parts.length ? "override" : "Override"} ${formatOverride(entry.previous_override)} → ${formatOverride(entry.new_override)}`,
    );
  }
  return parts.join(", ");
}

// --- usage -------------------------------------------------------------------

/** Amber from here, as the API's `NEAR_LIMIT_PERCENT`. */
export const NEAR_LIMIT_PERCENT = 80;

/** `usage_percent()` in `services/operator_console.py`, for a row a write
 *  just returned (which carries `used` and `effective` but no percentage).
 *  `null` for unlimited; a limit of 0 is 100% — stopped, not idle. */
export function usagePercent(used: number, limit: number | null): number | null {
  if (limit === null) return null;
  if (limit === 0) return 100;
  return (used * 100) / limit;
}

export type UsageTone = "neutral" | "warn" | "bad";

/** The bar's colour: neutral, amber at ≥ 80%, red at ≥ 100%. */
export function usageTone(percent: number | null): UsageTone | null {
  if (percent === null) return null;
  if (percent >= 100) return "bad";
  if (percent >= NEAR_LIMIT_PERCENT) return "warn";
  return "neutral";
}

/** "just now", "5 min ago", "3 h ago", "4 days ago", then a date. */
export function formatRelative(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "Never";
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "—";
  const seconds = Math.round((now.getTime() - then.getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} day${days === 1 ? "" : "s"} ago`;
  return then.toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" });
}

export function formatAbsolute(iso: string | null): string {
  if (!iso) return "";
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime()) ? iso : parsed.toLocaleString("en-US");
}

// --- date ranges ---------------------------------------------------------------

export const DATE_RANGES = ["all", "24h", "7d", "30d", "custom"] as const;
export type DateRange = (typeof DATE_RANGES)[number];

const DAY_MS = 86_400_000;
const DAY = /^\d{4}-\d{2}-\d{2}$/;

/** The `since` / `until` an email date range asks the API for. Custom days
 *  are whole days in the operator's own timezone, `to` included. */
export function rangeBounds(
  range: DateRange,
  from: string | null,
  to: string | null,
  now: Date = new Date(),
): { since: string | null; until: string | null } {
  const back = (ms: number) => new Date(now.getTime() - ms).toISOString();
  switch (range) {
    case "24h":
      return { since: back(DAY_MS), until: null };
    case "7d":
      return { since: back(7 * DAY_MS), until: null };
    case "30d":
      return { since: back(30 * DAY_MS), until: null };
    case "custom": {
      const since = from && DAY.test(from) ? new Date(`${from}T00:00:00`).toISOString() : null;
      const until = to && DAY.test(to) ? new Date(`${to}T23:59:59.999`).toISOString() : null;
      return { since, until };
    }
    default:
      return { since: null, until: null };
  }
}

// --- URL state ---------------------------------------------------------------

export type OperatorTab = "plans" | "emails";

export const DELIVERY_FILTERS = [
  "attempted",
  "sent",
  "failed",
  "deferred",
  "pending",
  "unknown",
  "not_requested",
  "all",
] as const;
export type DeliveryFilterValue = (typeof DELIVERY_FILTERS)[number];

export const ORG_SORTS = ["usage", "name", "plan", "limit", "used", "last_activity"] as const;
export type OrgSortValue = (typeof ORG_SORTS)[number];
export const DELIVERY_SORTS = ["issued_at", "delivered_at", "attempts", "status", "org", "recipient", "title"] as const;
export type DeliverySortValue = (typeof DELIVERY_SORTS)[number];
export type SortDir = "asc" | "desc";

export interface OperatorParams {
  tab: OperatorTab;
  /** On the Plans tab, the org whose drawer is open. On the Emails tab, the
   *  org the list is narrowed to. Never carried from one tab to the other —
   *  that is what made a Plans selection silently empty the Emails tab —
   *  except by an explicit "View this org's emails". */
  org: string | null;

  // Plans tab
  plans: string[];
  active: boolean;
  near: boolean;
  override: boolean;
  orgSort: OrgSortValue;
  orgDir: SortDir;

  // Emails tab
  status: DeliveryFilterValue;
  range: DateRange;
  from: string | null;
  to: string | null;
  mailSort: DeliverySortValue;
  mailDir: SortDir;
  /** 1-based. */
  page: number;
}

export const DEFAULT_PARAMS: OperatorParams = {
  tab: "plans",
  org: null,
  plans: [],
  active: false,
  near: false,
  override: false,
  orgSort: "usage",
  orgDir: "desc",
  status: "attempted",
  range: "all",
  from: null,
  to: null,
  mailSort: "issued_at",
  mailDir: "desc",
  page: 1,
};

/** The default state of one tab — what a tab switch lands on. */
export function tabDefaults(tab: OperatorTab): OperatorParams {
  return { ...DEFAULT_PARAMS, tab };
}

const SLUG = /^[a-z0-9][a-z0-9-]{0,99}$/;
const TIER_KEY = /^[a-z][a-z0-9_-]{0,49}$/;

function oneOf<T extends string>(values: readonly T[], raw: string | null, fallback: T): T {
  return (values as readonly string[]).includes(raw ?? "") ? (raw as T) : fallback;
}

/** Reads `?tab=emails&org=acme&status=failed` and the rest. Anything
 *  unrecognised falls back to its default rather than being trusted: these
 *  come from a pasted URL. Each tab reads only its own parameters. */
export function parseOperatorParams(params: { get(name: string): string | null }): OperatorParams {
  const tab: OperatorTab = params.get("tab") === "emails" ? "emails" : "plans";
  const rawOrg = params.get("org");
  const org = rawOrg && SLUG.test(rawOrg) ? rawOrg : null;
  const state = { ...tabDefaults(tab), org };
  const dir = oneOf(["asc", "desc"] as const, params.get("dir"), "desc");

  if (tab === "plans") {
    state.plans = (params.get("plan") ?? "")
      .split(",")
      .filter((key) => TIER_KEY.test(key))
      .slice(0, 10);
    state.active = params.get("active") === "1";
    state.near = params.get("near") === "1";
    state.override = params.get("override") === "1";
    state.orgSort = oneOf(ORG_SORTS, params.get("sort"), "usage");
    state.orgDir = dir;
    return state;
  }

  state.status = oneOf(DELIVERY_FILTERS, params.get("status"), "attempted");
  state.range = oneOf(DATE_RANGES, params.get("range"), "all");
  if (state.range === "custom") {
    const from = params.get("from");
    const to = params.get("to");
    state.from = from && DAY.test(from) ? from : null;
    state.to = to && DAY.test(to) ? to : null;
  }
  state.mailSort = oneOf(DELIVERY_SORTS, params.get("sort"), "issued_at");
  state.mailDir = dir;
  const page = Number(params.get("page"));
  state.page = Number.isInteger(page) && page > 1 && page < 100_000 ? page : 1;
  return state;
}

/** The query string for a state, defaults omitted. Starts with `?`, or is
 *  empty for the default view. Only the active tab's parameters are written. */
export function operatorSearch(state: OperatorParams): string {
  const params = new URLSearchParams();
  if (state.tab === "emails") params.set("tab", "emails");
  if (state.org) params.set("org", state.org);
  if (state.tab === "plans") {
    if (state.plans.length) params.set("plan", state.plans.join(","));
    if (state.active) params.set("active", "1");
    if (state.near) params.set("near", "1");
    if (state.override) params.set("override", "1");
    if (state.orgSort !== "usage") params.set("sort", state.orgSort);
    if (state.orgDir !== "desc") params.set("dir", state.orgDir);
  } else {
    if (state.status !== "attempted") params.set("status", state.status);
    if (state.range !== "all") params.set("range", state.range);
    if (state.range === "custom") {
      if (state.from) params.set("from", state.from);
      if (state.to) params.set("to", state.to);
    }
    if (state.mailSort !== "issued_at") params.set("sort", state.mailSort);
    if (state.mailDir !== "desc") params.set("dir", state.mailDir);
    if (state.page > 1) params.set("page", String(state.page));
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

/** Clicking a sortable header: a new column starts descending; the same
 *  column flips direction. */
export function nextSort<T extends string>(current: T, dir: SortDir, clicked: T): { sort: T; dir: SortDir } {
  if (clicked !== current) return { sort: clicked, dir: "desc" };
  return { sort: clicked, dir: dir === "desc" ? "asc" : "desc" };
}

/** One key per confirmation dialog: a double-click on Confirm reuses it, so
 *  the API answers the second click from the first instead of sending twice. */
export function newIdempotencyKey(): string {
  return `op-${crypto.randomUUID()}`;
}
