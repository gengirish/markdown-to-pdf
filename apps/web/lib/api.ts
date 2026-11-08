/**
 * Typed client for the CertForge API.
 *
 * The API lives on its own host (`api.certforge.intelliforge.tech`), so every
 * call here is cross-origin and carries a Clerk session JWT explicitly rather
 * than relying on cookies.
 *
 * Two failure shapes have to be tolerated on the wire. Handlers that return
 * `ApiResponse.fail(...)` answer HTTP 200 with `{"success": false, "error": …}`,
 * while handlers that raise `HTTPException` answer a real status code with a
 * bare `{"error": …}` and no `success` field. FastAPI's own request validation
 * adds a third, `{"detail": …}`. All three are normalised into `ApiError` so
 * callers only ever have one failure type to handle.
 */

import type { OperatorTier } from "./operator";

export type { OperatorTier };

export const DEFAULT_API_BASE_URL = "https://api.certforge.intelliforge.tech";

/** Base URL of the CertForge API, without a trailing slash. */
export function resolveApiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_CERTFORGE_API_URL?.trim();
  const base = configured && configured.length > 0 ? configured : DEFAULT_API_BASE_URL;
  return base.replace(/\/+$/, "");
}

/** A failed API call. Thrown by every method on {@link CertForgeClient}. */
export class ApiError extends Error {
  /** HTTP status, or the envelope's `error.code` when the body says 200 but failed. `0` for transport failures. */
  readonly status: number;
  /** Machine-readable category, e.g. `not_found`, `forbidden`, `network_error`. */
  readonly type: string;
  readonly details: unknown;

  constructor(message: string, init: { status: number; type?: string; details?: unknown }) {
    super(message);
    this.name = "ApiError";
    this.status = init.status;
    this.type = init.type ?? "api_error";
    this.details = init.details ?? null;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }

  get isUnauthenticated(): boolean {
    return this.status === 401;
  }

  /** True when the org has run out of monthly credential quota.
   *
   *  Several different refusals answer 402 and they need different copy, so
   *  status alone is not enough to tell them apart. Every other one carries its
   *  own type: `template_limit_reached`, `csv_batch_limit_reached`,
   *  `plan_feature_required`. */
  get isQuotaExceeded(): boolean {
    return this.status === 402 && !PLAN_REFUSAL_TYPES.has(this.type);
  }

  /** True when the org's plan does not include the capability asked for
   *  (artwork upload, API keys, webhooks). `details` carries
   *  `{ tier, tier_name, feature, upgrades }`. */
  get isPlanFeatureRequired(): boolean {
    return this.type === "plan_feature_required";
  }

  /** True when the org has used its plan's CSV uploads for this month.
   *  `details` carries `{ tier, tier_name, limit, used, upgrades }`. */
  get isCsvBatchLimitReached(): boolean {
    return this.type === "csv_batch_limit_reached";
  }

  /** True when the org already holds as many templates as its plan allows.
   *  `details` carries `{ tier, tier_name, limit, used, upgrades }`. */
  get isTemplateLimitReached(): boolean {
    return this.type === "template_limit_reached";
  }
}

/** The 402s that are about the plan rather than the monthly credential quota. */
const PLAN_REFUSAL_TYPES = new Set([
  "template_limit_reached",
  "csv_batch_limit_reached",
  "plan_feature_required",
]);

/** Coerce anything thrown by a request into an `ApiError` for rendering. */
export function toApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;
  if (err instanceof Error) {
    return new ApiError(err.message, { status: 0, type: "network_error" });
  }
  return new ApiError("Unexpected error", { status: 0, type: "unknown_error", details: err });
}

// --- wire types ------------------------------------------------------------

export interface OrgProfile {
  id: string;
  slug: string;
  name: string;
  /** An external URL the org can point at. Rendered by the viewer and by an
   *  Open Badges consumer, both of which fetch it themselves — and never by the
   *  certificate PDF, whose renderer refuses to fetch anything. Uploading is
   *  what puts a logo on a document; see `logo_asset_id`. */
  logo_url: string | null;
  /** An uploaded logo. Set means the certificate prints it and the public
   *  pages show it; this wins over `logo_url` wherever both apply. */
  logo_asset_id: string | null;
  primary_color: string | null;
  accent_color: string | null;
  footer_text: string | null;
  tier: string;
}

/** What `PATCH /orgs/{slug}` accepts. Every field is optional; the server
 *  leaves anything omitted untouched, so a partial save is a partial save. */
export interface OrgBrandingUpdate {
  name?: string;
  logoUrl?: string | null;
  primaryColor?: string | null;
  accentColor?: string | null;
  footerText?: string | null;
}

/** One counter's standing: how many used, and against what limit.
 *  `limit`/`remaining` are `null` for an unlimited tier — never a `-1`
 *  sentinel, which is an API-internal detail. */
export interface UsageMeter {
  used: number;
  limit: number | null;
  remaining: number | null;
}

/** The credential meter also says where its limit came from: the plan, or an
 *  operator's override for this one org. */
export interface CredentialMeter extends UsageMeter {
  source: CredentialQuotaSource;
}

export type CredentialQuotaSource = "tier" | "override";

export interface UsageSummary {
  /** YYYY-MM, the period the counters below are for. */
  period: string;
  /** The raw `organizations.tier` value. Free text — see `tier_known`. */
  tier: string;
  /** The display name of the plan whose limits are actually being enforced.
   *  When `tier_known` is false this is Community's, not a prettified `tier`:
   *  showing a plan name that does not match the limits in force is how a
   *  customer comes to believe they bought something they did not get. */
  tier_name: string;
  /** False when `tier` is a value the API's plan table does not know. */
  tier_known: boolean;
  credentials: CredentialMeter;
  /** Templates the org holds, against its plan's allowance. A stock, not a
   *  monthly flow: deleting a template frees the slot. */
  templates: UsageMeter;
  vision_imports: UsageMeter;
  /** CSV uploads this calendar month, against the plan's allowance. */
  csv_batches: UsageMeter;
  /** The Dodo subscription that governs the tier, or `null` for an org that
   *  has never subscribed — including every org whose tier was set by hand. */
  subscription: SubscriptionSummary | null;
}

export interface SubscriptionSummary {
  /** Dodo's own state. `active`, `on_hold` and `past_due` keep the paid
   *  tier (the last two are a grace period while Dodo retries the renewal);
   *  anything else has ended it. */
  status: string | null;
  current_period_end: string | null;
  /** Cancelled, but paid up until `current_period_end`. */
  cancel_at_period_end: boolean;
  /** Whether a billing-portal link can be minted for this org. */
  manageable: boolean;
}

export interface CheckoutSession {
  /** Dodo's hosted checkout. The tier does not change when the browser comes
   *  back from it — only the signed webhook moves it. */
  checkout_url: string;
  session_id: string;
  tier: string;
}

/** One plan, as `GET /api/v1/tiers` serves it. The pricing page renders these
 *  rather than a table kept in TypeScript, so a price on the page and the
 *  quota the API grants cannot drift apart. */
export interface Tier {
  key: string;
  name: string;
  tagline: string;
  /** ISO 4217. `price_paise` is the minor unit of this currency. */
  currency: string;
  /** Paise per month. Integer minor units, never a float. */
  price_paise: number;
  /** `null` means unlimited. */
  monthly_quota: number | null;
  /** `null` means unlimited. */
  template_limit: number | null;
  /** CSV uploads a month. `null` means unlimited. */
  csv_batch_limit: number | null;
  /** Whether the plan may upload its own certificate artwork. */
  custom_artwork: boolean;
  /** Whether the plan may create API keys and webhooks. */
  api_access: boolean;
  features: string[];
}

export interface OrgMember {
  clerk_user_id: string;
  role: string;
  joined_at: string;
}

/** One placed field on a traced template. Coordinates are millimetres from
 *  the top-left of the page, which is what the generated @frame rules use — the
 *  canvas converts to pixels for display and never stores pixels. */
export interface TracedField {
  /** A builtin name, or `custom:<slug>` for a CSV column. The server refuses
   *  anything else: an unknown name would bind to nothing and render blank on
   *  every credential, which looks like a design choice rather than a fault. */
  variable: string;
  label: string;
  x_mm: number;
  y_mm: number;
  w_mm: number;
  h_mm: number;
  font_pt: number;
  color: string;
  align: "left" | "center" | "right";
  bold: boolean;
}

/** A template drawn on uploaded artwork. */
export interface TracedConfig {
  kind: "traced";
  page_width_mm: number;
  page_height_mm: number;
  fields: TracedField[];
}

/** What a design reading reports about itself, alongside the template. */
export interface TemplateFromImageMeta {
  /** The model said it was unsure, or placed nothing. Every box needs checking
   *  regardless; this is when to say so loudly. */
  needs_review: boolean;
  confidence: "high" | "medium" | "low";
  notes: string;
  /** Fields it proposed that were refused — an unknown or repeated binding. */
  dropped_fields: string[];
  imports_remaining: number;
}

/** Uploaded certificate artwork. The bytes are always a JPEG the API
 *  re-encoded — never the file that was uploaded. */
export interface TemplateAsset {
  id: string;
  mime: string;
  width_px: number;
  height_px: number;
  byte_size: number;
  checksum: string;
  aspect_ratio: number;
  created_at: string | null;
}

/** Guided-form settings. Present only while the template is still generated —
 *  editing its HTML by hand detaches it and the server sets this to null. */
export interface TemplateConfig {
  layout: "participation" | "internship" | "appreciation";
  heading: string;
  body: string;
  closing: string;
  signature_name: string;
  signature_title: string;
  show_qr: boolean;
  show_logo: boolean;
  show_footer: boolean;
}

export interface TemplateDetail {
  id: string;
  name: string;
  variables: string[];
  is_default: boolean;
  is_guided: boolean;
  created_at: string | null;
  updated_at: string | null;
  html_source: string;
  config: TemplateConfig | TracedConfig | null;
  /** The artwork this template is drawn on, when it has any. */
  background_asset_id: string | null;
}

export interface TemplateSummary {
  id: string;
  name: string;
  variables: string[];
  is_default: boolean;
  /** Whether the guided form may reopen this one. False means the HTML is
   *  hand-authored and regenerating would discard the author's edit. */
  is_guided: boolean;
  created_at: string | null;
  updated_at: string | null;
  background_asset_id: string | null;
}

/** Whether the recipient was told, kept apart from whether the credential
 *  exists. `not_requested` is the one that matters: it means no send was
 *  attempted, which is a recorded outcome rather than a missing one. */
export type DeliveryStatus = "not_requested" | "pending" | "sent" | "failed" | "unknown";

export interface DeliveryState {
  status: DeliveryStatus;
  delivered_at: string | null;
  error: string | null;
  attempts: number;
  may_retry: boolean;
}

export interface CredentialSummary {
  id: string;
  recipient_name: string;
  recipient_email: string;
  title: string;
  status: string;
  issued_at: string;
  batch_id: string | null;
  template_id: string | null;
  /** Issued with a cf_test_ key: never emailed, and not a real award. */
  is_test: boolean;
  delivery_status: DeliveryStatus;
}

export interface CredentialPage {
  items: CredentialSummary[];
  /** The count matching the filters, not the org's all-time total. */
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
  /** Pass back as `cursor` for the next page; null on the last one. */
  next_cursor: string | null;
}

export interface CredentialListQuery {
  limit?: number;
  offset?: number;
  cursor?: string;
  status?: "issued" | "revoked" | "pending" | "claimed";
  /** Case-insensitive substring of name, email or title. */
  q?: string;
  deliveryStatus?: DeliveryStatus;
  templateId?: string;
  batchId?: string;
  test?: "only" | "exclude";
}

export interface RevokeResult {
  id: string;
  status: "revoked";
  already_revoked: boolean;
  revoked_at?: string;
}

export interface ResendResult {
  id: string;
  /** False when the provider refused it; `delivery.error` says why. */
  sent: boolean;
  delivery: DeliveryState;
}

export interface IssuedCredential {
  id: string;
  org: string;
  recipient_name: string;
  recipient_email: string;
  title: string;
  status: string;
  issued_at: string;
  metadata: Record<string, unknown>;
  verify_url: string;
  badge_url: string;
  pdf_url: string;
  delivery: DeliveryState;
}

export interface BulkUploadResult {
  batch_id: string;
  total: number;
  status: string;
}

export interface BatchStatus {
  id: string;
  status: string;
  total: number;
  /** succeeded/failed count RENDERS, not sends. A batch can render every PDF
   *  and email nobody; `delivery` is the only thing that says so. */
  succeeded: number;
  failed: number;
  delivery: BatchDelivery;
  error_report: unknown;
  created_at: string;
  completed_at: string | null;
}

export interface BatchDelivery {
  delivered: number;
  failed: number;
  /** No address on the row, or delivery was never asked for. Stated rather
   *  than left to be inferred from a subtraction. */
  not_requested: number;
}

export interface ApiKeySummary {
  id: string;
  label: string;
  last_used_at: string | null;
  created_at: string;
}

/** The only response that ever carries `raw_key` — it is not retrievable later. */
export interface CreatedApiKey extends ApiKeySummary {
  raw_key: string;
}

export interface WebhookSummary {
  id: string;
  url: string;
  events: string[];
  created_at: string;
}

/** The only response that ever carries `secret`. */
export interface CreatedWebhook extends WebhookSummary {
  secret: string;
}

export interface PassportProfile {
  username: string;
  display_name: string;
  bio: string;
}

export interface PassportCredential {
  id: string;
  title: string;
  recipient_name: string;
  issued_at: string;
  metadata: Record<string, unknown> | null;
  pinned: boolean;
}

export interface PassportView {
  profile: PassportProfile;
  credentials: PassportCredential[];
}

export interface ClaimResult {
  username: string;
  credential_id: string;
}

export interface VerifiedCredential {
  /** "database" for a CertForge credential, "legacy" for one decoded from a
   *  signed URL token. The two carry different fields — see below. */
  source: string;
  id: string;
  name: string;
  title: string;
  issued_at: string;
  metadata: Record<string, unknown> | null;
  /** What the API checked before serving this, in its own words. `unverified`
   *  means the credential predates canonical signing and nothing was checked —
   *  it is NOT a pass, and must never be rendered as one. */
  signature?: {
    status: "valid" | "unverified" | "invalid";
    scheme: string;
    version: number | null;
    covers: string[];
  };
  /** Present for database-backed credentials only; a legacy token carries no
   *  organization. */
  issuer?: {
    name: string | null;
    slug: string | null;
    logo_url: string | null;
    primary_color: string | null;
    accent_color: string | null;
    footer_text: string | null;
  };
  pdf_url?: string;
}

// --- operator (CertForge staff only; the API checks an allowlist) ----------

/** An operator override has three states, so it travels as an object:
 *  `null` is no override, `{ limit: null }` is an unlimited one. */
export interface QuotaOverride {
  limit: number | null;
}

/** One org's credential quota, as `routes/operator.py` `_org_row` serves it.
 *  Every limit is `null` for unlimited. */
export interface OperatorOrg {
  slug: string;
  name: string;
  tier: string;
  tier_name: string;
  tier_known: boolean;
  tier_quota: number | null;
  source: CredentialQuotaSource;
  override: QuotaOverride | null;
  /** What issuance enforces: the override if there is one, else the tier's. */
  effective: number | null;
  /** Credentials issued this calendar month. */
  used: number;
}

/** A row of the operator org list. A write's response is a plain
 *  {@link OperatorOrg}, so merge it over the row rather than replacing it. */
export interface OperatorOrgRow extends OperatorOrg {
  /** This month's usage as a % of the enforced limit; `null` when unlimited. */
  usage_percent: number | null;
  /** The org's most recent credential, ISO 8601; `null` if it never issued. */
  last_activity_at: string | null;
  /** Another org has the same display name (case- and space-insensitive). */
  duplicate_name: boolean;
}

export type OperatorOrgSort = "usage" | "name" | "plan" | "limit" | "used" | "last_activity" | "slug";

export interface OperatorOrgPage {
  orgs: OperatorOrgRow[];
  /** Every org matching the filters, not just this page. */
  total: number;
  /** Pass back as `cursor` for the next page; `null` on the last one. */
  next_cursor: string | null;
}

/** The Plans tab's strip, as `GET /api/v1/operator/kpis` serves it. */
export interface OperatorKpis {
  period: string;
  active_orgs: number;
  credentials_issued: number;
  near_limit_orgs: number;
  near_limit_percent: number;
  failed_emails_7d: number;
}

export interface CredentialQuotaChange {
  previous_override: QuotaOverride | null;
  new_override: QuotaOverride | null;
  effective_before: number | null;
  effective_after: number | null;
  /** The plan either side of a plan change; both null on an override-only change. */
  previous_tier: string | null;
  new_tier: string | null;
  reason: string;
  /** An operator's Clerk user id, or a system actor such as `razorpay-webhook`. */
  actor: string;
  created_at: string;
}

export interface OperatorQuotaDetail extends OperatorOrg {
  usage_percent: number | null;
  created_at: string | null;
  last_activity_at: string | null;
  member_count: number;
  credentials_all_time: number;
  /** Newest first. */
  history: CredentialQuotaChange[];
}

/** One member of an org, with what Clerk holds for them. Read from Clerk on
 *  every request; nothing here is stored by CertForge. */
export interface OperatorContact {
  clerk_user_id: string;
  role: string;
  /** False when Clerk has no user with this id; the fields below are then null. */
  found: boolean;
  name: string | null;
  email: string | null;
  phone: string | null;
}

export interface OperatorQuotaResult extends OperatorOrg {
  /** False when the request asked for what was already in force. */
  changed: boolean;
  /** Set when the override equals the tier's quota, which freezes it there. */
  note?: string;
  /** Set when the new limit is below what the org already issued this month. */
  over_by?: number;
}

export interface OperatorTierResult extends OperatorOrg {
  previous_tier: string;
  changed: boolean;
  /** A real plan change removes any credential override. */
  override_cleared: boolean;
}

/** One credential email, across every org, as `routes/operator.py`
 *  `list_deliveries` serves it. */
export interface OperatorDelivery {
  id: string;
  org_slug: string;
  org_name: string;
  recipient_name: string;
  /** `null` when the credential was issued with no address. */
  recipient_email: string | null;
  title: string;
  status: string;
  is_test: boolean;
  issued_at: string;
  delivery_status: DeliveryStatus;
  delivered_at: string | null;
  delivery_attempts: number;
  delivery_error: string | null;
  /** The operator resend rule allows a resend now (failed, or pending/unknown over an hour). */
  resendable: boolean;
  /** Why it is not resendable, in words; `null` when it is. */
  resend_refusal: string | null;
  /** Data-quality flags, read-only. */
  title_looks_like_email: boolean;
  /** Same org, same recipient name or email, within 7 days. */
  possible_duplicate: boolean;
}

export type OperatorDeliverySort =
  | "issued_at"
  | "delivered_at"
  | "attempts"
  | "status"
  | "org"
  | "recipient"
  | "title";

export interface OperatorDeliveryQuery {
  org?: string | null;
  q?: string;
  deliveryStatus?: OperatorDeliveryFilter;
  /** ISO 8601, inclusive. */
  since?: string | null;
  until?: string | null;
  sort?: OperatorDeliverySort;
  dir?: "asc" | "desc";
}

export interface OperatorResendResult {
  id: string;
  sent: boolean;
  delivery: { status: DeliveryStatus; delivered_at: string | null; error: string | null; attempts: number };
  /** True when this answer is the first request's, replayed for a repeated key. */
  replayed: boolean;
}

/** `attempted` is everything except `not_requested`. */
export type OperatorDeliveryFilter = DeliveryStatus | "attempted" | "all";

export interface OperatorDeliveryPage {
  deliveries: OperatorDelivery[];
  total: number;
  /** Rows per status under every filter except status, plus `attempted` and `all`. */
  counts: Partial<Record<OperatorDeliveryFilter, number>>;
  next_cursor: string | null;
}

export interface HealthStatus {
  status: string;
  service: string;
  version: string;
  dependencies: Record<string, string>;
}

// --- request plumbing ------------------------------------------------------

export type TokenGetter = () => Promise<string | null | undefined>;

export interface CertForgeClientOptions {
  baseUrl?: string;
  /** Supplies the Clerk session JWT. Omit for an anonymous client. */
  getToken?: TokenGetter;
}

type QueryValue = string | number | boolean | undefined | null | readonly string[];

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  /** Extra request headers, e.g. `Idempotency-Key`. Must be in the API's CORS allow-list. */
  headers?: Record<string, string>;
  json?: unknown;
  form?: FormData;
  query?: Record<string, QueryValue>;
  signal?: AbortSignal;
  /** Skip the Authorization header. Public endpoints must work signed out. */
  anonymous?: boolean;
  /** Endpoint returns a bare body rather than the `{success, data}` envelope. */
  unenveloped?: boolean;
  /** Let Next cache this response for N seconds on the server.
   *
   *  The default everywhere else is `no-store`, and it stays that way: almost
   *  every endpoint here is scoped to the caller's session, and a cached
   *  response is one another visitor can be served. Only pass this for a
   *  response that is identical for everyone — the plan catalog is the one
   *  such endpoint today. Ignored in the browser. */
  revalidateSeconds?: number;
}

/** `no-store` unless the caller opted this response into Next's cache. */
function cachePolicy(options: RequestOptions): RequestInit {
  if (options.revalidateSeconds === undefined) return { cache: "no-store" };
  return { next: { revalidate: options.revalidateSeconds } } as RequestInit;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Pull a human-readable message out of any of the three error shapes. */
function errorFromBody(status: number, body: unknown): ApiError | null {
  if (!isRecord(body)) return null;

  const raw = body.error;
  if (isRecord(raw)) {
    const code = typeof raw.code === "number" ? raw.code : status;
    return new ApiError(typeof raw.message === "string" ? raw.message : "Request failed", {
      // A `fail()` envelope answers 200, so the envelope's own code is the
      // truthful status; for a raised HTTPException the two already agree.
      status: status === 200 ? code : status,
      type: typeof raw.type === "string" ? raw.type : undefined,
      details: raw.details,
    });
  }
  if (typeof raw === "string") {
    return new ApiError(raw, { status });
  }

  const detail = body.detail;
  if (typeof detail === "string") {
    return new ApiError(detail, { status });
  }
  if (Array.isArray(detail)) {
    const first = detail.find(isRecord);
    const message = first && typeof first.msg === "string" ? first.msg : "Validation failed";
    return new ApiError(message, { status, type: "validation_error", details: detail });
  }

  if (body.success === false) {
    return new ApiError("Request failed", { status });
  }
  return null;
}

function deliveryQuery(query: OperatorDeliveryQuery): Record<string, QueryValue> {
  return {
    org: query.org || undefined,
    q: query.q || undefined,
    delivery_status: query.deliveryStatus,
    since: query.since || undefined,
    until: query.until || undefined,
    sort: query.sort,
    dir: query.dir,
  };
}

export class CertForgeClient {
  readonly baseUrl: string;
  private readonly getToken?: TokenGetter;

  constructor(options: CertForgeClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? resolveApiBaseUrl()).replace(/\/+$/, "");
    this.getToken = options.getToken;
  }

  private async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const url = new URL(this.baseUrl + path);
    for (const [key, value] of Object.entries(options.query ?? {})) {
      // An array is a repeated parameter (`?tier=pro&tier=scale`).
      if (Array.isArray(value)) value.forEach((item) => url.searchParams.append(key, String(item)));
      else if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
    }

    const headers: Record<string, string> = { Accept: "application/json", ...options.headers };
    if (options.json !== undefined) headers["Content-Type"] = "application/json";

    if (!options.anonymous && this.getToken) {
      const token = await this.getToken();
      if (!token) {
        throw new ApiError("You need to be signed in to do that.", {
          status: 401,
          type: "authentication_error",
        });
      }
      headers.Authorization = `Bearer ${token}`;
    }

    let response: Response;
    try {
      response = await fetch(url, {
        method: options.method ?? "GET",
        headers,
        // FormData sets its own multipart boundary; never stringify it.
        body: options.form ?? (options.json !== undefined ? JSON.stringify(options.json) : undefined),
        signal: options.signal,
        ...cachePolicy(options),
      });
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") throw err;
      throw new ApiError("Could not reach the CertForge API.", {
        status: 0,
        type: "network_error",
        details: err,
      });
    }

    const text = await response.text();
    let body: unknown = null;
    if (text.length > 0) {
      try {
        body = JSON.parse(text);
      } catch {
        if (!response.ok) {
          throw new ApiError(`API returned ${response.status}`, { status: response.status });
        }
        throw new ApiError("API returned a malformed response.", {
          status: response.status,
          type: "invalid_response",
        });
      }
    }

    const failure = errorFromBody(response.status, body);
    if (failure) throw failure;
    if (!response.ok) {
      throw new ApiError(`API returned ${response.status}`, { status: response.status });
    }

    if (options.unenveloped) return body as T;
    return (isRecord(body) ? (body.data as T) : (body as T));
  }

  /** Fetch an endpoint that answers with a file rather than the envelope.
   *
   *  Kept separate from request(): that one reads the body as text and parses
   *  it as JSON, which would corrupt a PDF. Failures still arrive as JSON, so
   *  the content type decides which of the two this response is. */
  private async requestBlob(path: string, options: RequestOptions = {}): Promise<Blob> {
    return (await this.requestFile(path, options)).blob;
  }

  /** {@link requestBlob}, plus the response headers (a download's file name). */
  private async requestFile(
    path: string,
    options: RequestOptions = {},
  ): Promise<{ blob: Blob; headers: Headers }> {
    const url = new URL(this.baseUrl + path);
    for (const [key, value] of Object.entries(options.query ?? {})) {
      if (Array.isArray(value)) value.forEach((item) => url.searchParams.append(key, String(item)));
      else if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
    }
    const headers: Record<string, string> = {
      Accept: "application/pdf, text/csv, application/json",
      ...options.headers,
    };
    if (options.json !== undefined) headers["Content-Type"] = "application/json";

    if (!options.anonymous && this.getToken) {
      const token = await this.getToken();
      if (!token) {
        throw new ApiError("You need to be signed in to do that.", {
          status: 401,
          type: "authentication_error",
        });
      }
      headers.Authorization = `Bearer ${token}`;
    }

    let response: Response;
    try {
      response = await fetch(url, {
        method: options.method ?? "GET",
        headers,
        body: options.json !== undefined ? JSON.stringify(options.json) : undefined,
        signal: options.signal,
        ...cachePolicy(options),
      });
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") throw err;
      throw new ApiError("Could not reach the CertForge API.", {
        status: 0,
        type: "network_error",
        details: err,
      });
    }

    if (!response.headers.get("content-type")?.includes("application/json")) {
      if (!response.ok) {
        throw new ApiError(`API returned ${response.status}`, { status: response.status });
      }
      return { blob: await response.blob(), headers: response.headers };
    }

    const body = await response.json().catch(() => null);
    const failure = errorFromBody(response.status, body);
    if (failure) throw failure;
    throw new ApiError(`API returned ${response.status}`, { status: response.status });
  }

  // --- system ---
  health(signal?: AbortSignal): Promise<HealthStatus> {
    return this.request<HealthStatus>("/api/health", {
      anonymous: true,
      unenveloped: true,
      signal,
    });
  }

  // --- organizations ---
  getOrg(slug: string, signal?: AbortSignal): Promise<OrgProfile> {
    return this.request<OrgProfile>(`/api/v1/orgs/${encodeURIComponent(slug)}`, {
      anonymous: true,
      signal,
    });
  }

  /** Partial update. Only the keys present are sent, so clearing a field is an
   *  explicit `null` rather than an omission — the server distinguishes them. */
  updateOrg(
    slug: string,
    input: OrgBrandingUpdate,
    signal?: AbortSignal,
  ): Promise<OrgProfile> {
    const json: Record<string, unknown> = {};
    if (input.name !== undefined) json.name = input.name;
    if (input.logoUrl !== undefined) json.logo_url = input.logoUrl;
    if (input.primaryColor !== undefined) json.primary_color = input.primaryColor;
    if (input.accentColor !== undefined) json.accent_color = input.accentColor;
    if (input.footerText !== undefined) json.footer_text = input.footerText;

    return this.request<OrgProfile>(`/api/v1/orgs/${encodeURIComponent(slug)}`, {
      method: "PATCH",
      json,
      signal,
    });
  }

  listOrgMembers(slug: string, signal?: AbortSignal): Promise<OrgMember[]> {
    return this.request<OrgMember[]>(`/api/v1/orgs/${encodeURIComponent(slug)}/members`, { signal });
  }

  getUsage(slug: string, signal?: AbortSignal): Promise<UsageSummary> {
    return this.request<UsageSummary>(`/api/v1/orgs/${encodeURIComponent(slug)}/usage`, { signal });
  }

  /** Every plan on sale, in display order. Needs no session.
   *
   *  Cached on the server: the catalog is the same for every visitor, and the
   *  pricing page should not wake a scaled-to-zero API machine per view. */
  listTiers(signal?: AbortSignal, revalidateSeconds = 300): Promise<Tier[]> {
    return this.request<Tier[]>("/api/v1/tiers", { signal, revalidateSeconds });
  }

  /** Owner only. Rejects 409 `already_subscribed` for an org that holds a
   *  live subscription — a second checkout would bill a second one. */
  startCheckout(slug: string, tier: string, signal?: AbortSignal): Promise<CheckoutSession> {
    return this.request<CheckoutSession>(`/api/v1/orgs/${encodeURIComponent(slug)}/checkout`, {
      method: "POST",
      json: { tier },
      signal,
    });
  }

  /** Owner only. The link expires after 24 hours, so mint one per click. */
  openBillingPortal(slug: string, signal?: AbortSignal): Promise<{ portal_url: string }> {
    return this.request<{ portal_url: string }>(
      `/api/v1/orgs/${encodeURIComponent(slug)}/billing/portal`,
      { method: "POST", signal },
    );
  }

  // --- credentials ---
  listOrgCredentials(
    slug: string,
    page: CredentialListQuery = {},
    signal?: AbortSignal,
  ): Promise<CredentialPage> {
    return this.request<CredentialPage>(`/api/v1/orgs/${encodeURIComponent(slug)}/credentials`, {
      query: {
        limit: page.limit,
        offset: page.offset,
        cursor: page.cursor,
        status: page.status,
        q: page.q || undefined,
        delivery_status: page.deliveryStatus,
        template_id: page.templateId,
        batch_id: page.batchId,
        test: page.test,
      },
      signal,
    });
  }

  /** Owner or admin only; an issuer gets a 403. Terminal — there is no un-revoke. */
  revokeCredential(slug: string, credentialId: string, signal?: AbortSignal): Promise<RevokeResult> {
    return this.request<RevokeResult>(
      `/api/v1/orgs/${encodeURIComponent(slug)}/credentials/${encodeURIComponent(credentialId)}/revoke`,
      { method: "POST", signal },
    );
  }

  /** Emails the credential again, inline. Refused (409) for a revoked or test
   *  credential, one with no address, or one already emailed the maximum
   *  number of times. */
  resendCredential(slug: string, credentialId: string, signal?: AbortSignal): Promise<ResendResult> {
    return this.request<ResendResult>(
      `/api/v1/orgs/${encodeURIComponent(slug)}/credentials/${encodeURIComponent(credentialId)}/resend`,
      { method: "POST", signal },
    );
  }

  bulkIssueFromCsv(
    slug: string,
    input: { templateId: string; file: File },
    signal?: AbortSignal,
  ): Promise<BulkUploadResult> {
    const form = new FormData();
    form.append("template_id", input.templateId);
    form.append("file", input.file);
    return this.request<BulkUploadResult>(
      `/api/v1/orgs/${encodeURIComponent(slug)}/credentials/bulk`,
      { method: "POST", form, signal },
    );
  }

  issueCredential(
    slug: string,
    input: { recipientName: string; title: string; recipientEmail?: string; templateId?: string; sendEmail?: boolean },
    signal?: AbortSignal,
  ): Promise<IssuedCredential> {
    return this.request<IssuedCredential>(`/api/v1/orgs/${encodeURIComponent(slug)}/credentials`, {
      method: "POST",
      json: {
        recipient_name: input.recipientName,
        title: input.title,
        recipient_email: input.recipientEmail || "",
        template_id: input.templateId || undefined,
        send_email: input.sendEmail ?? false,
      },
      signal,
    });
  }

  getBatch(slug: string, batchId: string, signal?: AbortSignal): Promise<BatchStatus> {
    return this.request<BatchStatus>(
      `/api/v1/orgs/${encodeURIComponent(slug)}/batches/${encodeURIComponent(batchId)}`,
      { signal },
    );
  }

  // --- templates ---
  listGlobalTemplates(signal?: AbortSignal): Promise<TemplateSummary[]> {
    return this.request<TemplateSummary[]>("/api/v1/templates", { anonymous: true, signal });
  }

  listOrgTemplates(slug: string, signal?: AbortSignal): Promise<TemplateSummary[]> {
    return this.request<TemplateSummary[]>(`/api/v1/orgs/${encodeURIComponent(slug)}/templates`, {
      signal,
    });
  }

  // --- developer settings ---
  getOrgTemplate(slug: string, id: string, signal?: AbortSignal): Promise<TemplateDetail> {
    return this.request<TemplateDetail>(
      `/api/v1/orgs/${encodeURIComponent(slug)}/templates/${encodeURIComponent(id)}`,
      { signal },
    );
  }

  /** Exactly one of htmlSource or config — the server refuses both, because a
   *  request carrying each has no non-arbitrary answer for which one wins. */
  createTemplate(
    slug: string,
    input: {
      name: string;
      htmlSource?: string;
      config?: Partial<TemplateConfig> | TracedConfig;
      backgroundAssetId?: string | null;
    },
    signal?: AbortSignal,
  ): Promise<TemplateDetail> {
    return this.request<TemplateDetail>(`/api/v1/orgs/${encodeURIComponent(slug)}/templates`, {
      method: "POST",
      json: {
        name: input.name,
        html_source: input.htmlSource,
        config: input.config,
        background_asset_id: input.backgroundAssetId,
      },
      signal,
    });
  }

  updateTemplate(
    slug: string,
    id: string,
    input: {
      name?: string;
      htmlSource?: string;
      config?: Partial<TemplateConfig> | TracedConfig;
      /** "" unbinds the artwork; omitting the key leaves it alone. The two are
       *  different on purpose — a rename must not silently drop a background. */
      backgroundAssetId?: string | null;
    },
    signal?: AbortSignal,
  ): Promise<TemplateDetail> {
    const json: Record<string, unknown> = {};
    if (input.name !== undefined) json.name = input.name;
    if (input.htmlSource !== undefined) json.html_source = input.htmlSource;
    if (input.config !== undefined) json.config = input.config;
    if (input.backgroundAssetId !== undefined) {
      json.background_asset_id = input.backgroundAssetId;
    }

    return this.request<TemplateDetail>(
      `/api/v1/orgs/${encodeURIComponent(slug)}/templates/${encodeURIComponent(id)}`,
      { method: "PATCH", json, signal },
    );
  }

  deleteTemplate(slug: string, id: string, signal?: AbortSignal): Promise<{ deleted: boolean }> {
    return this.request<{ deleted: boolean }>(
      `/api/v1/orgs/${encodeURIComponent(slug)}/templates/${encodeURIComponent(id)}`,
      { method: "DELETE", signal },
    );
  }

  setDefaultTemplate(slug: string, id: string, signal?: AbortSignal): Promise<TemplateSummary> {
    return this.request<TemplateSummary>(
      `/api/v1/orgs/${encodeURIComponent(slug)}/templates/${encodeURIComponent(id)}/default`,
      { method: "POST", signal },
    );
  }

  /** Copy a global template into this org as an editable starting point. */
  importTemplate(slug: string, globalId: string, signal?: AbortSignal): Promise<TemplateDetail> {
    return this.request<TemplateDetail>(
      `/api/v1/orgs/${encodeURIComponent(slug)}/templates/import/${encodeURIComponent(globalId)}`,
      { method: "POST", signal },
    );
  }

  /** Render sample data and return the PDF. Nothing is saved, so this works
   *  before a template exists. A PDF rather than HTML on purpose: the dashboard
   *  must never inject customer-authored markup into its own document. */
  previewTemplate(
    slug: string,
    input: {
      htmlSource?: string;
      config?: Partial<TemplateConfig> | TracedConfig;
      backgroundAssetId?: string | null;
    },
    signal?: AbortSignal,
  ): Promise<Blob> {
    return this.requestBlob(`/api/v1/orgs/${encodeURIComponent(slug)}/templates/preview`, {
      method: "POST",
      json: {
        html_source: input.htmlSource,
        config: input.config,
        background_asset_id: input.backgroundAssetId,
      },
      signal,
    });
  }

  /** Upload the artwork a template is drawn on.
   *
   *  Multipart, like the bulk CSV upload — the server re-encodes whatever
   *  arrives, so what comes back describes a JPEG it produced rather than the
   *  file that was sent. Uploading the same image twice returns the same asset. */
  uploadTemplateAsset(slug: string, file: File, signal?: AbortSignal): Promise<TemplateAsset> {
    const form = new FormData();
    form.append("file", file);

    return this.request<TemplateAsset>(
      `/api/v1/orgs/${encodeURIComponent(slug)}/template-assets`,
      { method: "POST", form, signal },
    );
  }

  /** Upload the logo printed on this organization's certificates.
   *
   *  A separate endpoint from `uploadTemplateAsset`, not a flag on it: a logo
   *  is encoded differently — transparency survives, because flattening a
   *  transparent PNG prints a black box on every certificate — and it belongs
   *  to the organization rather than to one template. */
  uploadOrgLogo(slug: string, file: File, signal?: AbortSignal): Promise<TemplateAsset> {
    const form = new FormData();
    form.append("file", file);

    return this.request<TemplateAsset>(
      `/api/v1/orgs/${encodeURIComponent(slug)}/logo`,
      { method: "POST", form, signal },
    );
  }

  /** Stop printing a logo. The image itself is kept — deleting bytes a
   *  template may also be drawn on is a separate, destructive decision. */
  removeOrgLogo(slug: string, signal?: AbortSignal): Promise<{ removed: boolean }> {
    return this.request<{ removed: boolean }>(
      `/api/v1/orgs/${encodeURIComponent(slug)}/logo`,
      { method: "DELETE", signal },
    );
  }

  /** The public URL of an uploaded logo — no auth, so it can go straight in an
   *  `<img src>`. Unlike `templateAssetImage`, which must be fetched as a Blob
   *  because that route is authenticated. */
  orgLogoUrl(slug: string): string {
    return `${this.baseUrl}/orgs/${encodeURIComponent(slug)}/logo`;
  }

  listTemplateAssets(slug: string, signal?: AbortSignal): Promise<TemplateAsset[]> {
    return this.request<TemplateAsset[]>(
      `/api/v1/orgs/${encodeURIComponent(slug)}/template-assets`,
      { signal },
    );
  }

  /** The stored image itself, for the canvas to place fields on.
   *
   *  A Blob rather than a URL the browser fetches directly: the route is
   *  authenticated, and an <img src> carries no Authorization header. The
   *  caller owns the object URL and must revoke it on unmount. */
  templateAssetImage(slug: string, id: string, signal?: AbortSignal): Promise<Blob> {
    return this.requestBlob(
      `/api/v1/orgs/${encodeURIComponent(slug)}/template-assets/${encodeURIComponent(id)}/image`,
      { signal },
    );
  }

  /** Ask the model where this design's fields belong, and create a template
   *  with them placed.
   *
   *  Slow — tens of seconds — and metered per organization, because every call
   *  is a paid request. `needs_review` means the model said it was guessing;
   *  the boxes still need checking either way, which is what the canvas is. */
  createTemplateFromImage(
    slug: string,
    input: { assetId: string; name: string },
    signal?: AbortSignal,
  ): Promise<TemplateDetail & TemplateFromImageMeta> {
    return this.request<TemplateDetail & TemplateFromImageMeta>(
      `/api/v1/orgs/${encodeURIComponent(slug)}/templates/from-image`,
      { method: "POST", json: { asset_id: input.assetId, name: input.name }, signal },
    );
  }

  deleteTemplateAsset(
    slug: string,
    id: string,
    signal?: AbortSignal,
  ): Promise<{ deleted: boolean }> {
    return this.request<{ deleted: boolean }>(
      `/api/v1/orgs/${encodeURIComponent(slug)}/template-assets/${encodeURIComponent(id)}`,
      { method: "DELETE", signal },
    );
  }

  listApiKeys(slug: string, signal?: AbortSignal): Promise<ApiKeySummary[]> {
    return this.request<ApiKeySummary[]>(`/api/v1/orgs/${encodeURIComponent(slug)}/api-keys`, {
      signal,
    });
  }

  createApiKey(slug: string, label: string, signal?: AbortSignal): Promise<CreatedApiKey> {
    return this.request<CreatedApiKey>(`/api/v1/orgs/${encodeURIComponent(slug)}/api-keys`, {
      method: "POST",
      json: { label },
      signal,
    });
  }

  revokeApiKey(slug: string, keyId: string, signal?: AbortSignal): Promise<{ status: string }> {
    return this.request<{ status: string }>(
      `/api/v1/orgs/${encodeURIComponent(slug)}/api-keys/${encodeURIComponent(keyId)}`,
      { method: "DELETE", signal },
    );
  }

  listWebhooks(slug: string, signal?: AbortSignal): Promise<WebhookSummary[]> {
    return this.request<WebhookSummary[]>(`/api/v1/orgs/${encodeURIComponent(slug)}/webhooks`, {
      signal,
    });
  }

  createWebhook(
    slug: string,
    input: { url: string; events?: string[] },
    signal?: AbortSignal,
  ): Promise<CreatedWebhook> {
    return this.request<CreatedWebhook>(`/api/v1/orgs/${encodeURIComponent(slug)}/webhooks`, {
      method: "POST",
      json: { url: input.url, events: input.events },
      signal,
    });
  }

  deleteWebhook(slug: string, webhookId: string, signal?: AbortSignal): Promise<{ status: string }> {
    return this.request<{ status: string }>(
      `/api/v1/orgs/${encodeURIComponent(slug)}/webhooks/${encodeURIComponent(webhookId)}`,
      { method: "DELETE", signal },
    );
  }

  // --- operator ---
  // 403 for anyone not on CERTFORGE_OPERATOR_USER_IDS, API keys included.

  /** Every plan, hand-sold ones included. The plan control must use this,
   *  not {@link listTiers}: the public catalog hides Scale. */
  listOperatorTiers(signal?: AbortSignal): Promise<OperatorTier[]> {
    return this.request<{ tiers: OperatorTier[] }>("/api/v1/operator/tiers", { signal }).then(
      (data) => data.tiers,
    );
  }

  listOperatorOrgs(
    query: {
      q?: string;
      tiers?: readonly string[];
      active?: boolean;
      nearLimit?: boolean;
      hasOverride?: boolean;
      sort?: OperatorOrgSort;
      dir?: "asc" | "desc";
      limit?: number;
      offset?: number;
      cursor?: string | null;
    } = {},
    signal?: AbortSignal,
  ): Promise<OperatorOrgPage> {
    return this.request<OperatorOrgPage>("/api/v1/operator/orgs", {
      query: {
        q: query.q || undefined,
        tier: query.tiers && query.tiers.length ? query.tiers : undefined,
        active: query.active || undefined,
        near_limit: query.nearLimit || undefined,
        has_override: query.hasOverride || undefined,
        sort: query.sort,
        dir: query.dir,
        limit: query.limit,
        offset: query.offset || undefined,
        cursor: query.cursor,
      },
      signal,
    });
  }

  getOperatorKpis(signal?: AbortSignal): Promise<OperatorKpis> {
    return this.request<OperatorKpis>("/api/v1/operator/kpis", { signal });
  }

  getCredentialQuota(slug: string, signal?: AbortSignal): Promise<OperatorQuotaDetail> {
    return this.request<OperatorQuotaDetail>(
      `/api/v1/operator/orgs/${encodeURIComponent(slug)}/credential-quota`,
      { signal },
    );
  }

  /** Owners first. Rejects 503 `contacts_unavailable` when Clerk cannot be
   *  asked; the quota calls do not depend on this one. */
  getOrgContacts(slug: string, signal?: AbortSignal): Promise<OperatorContact[]> {
    return this.request<{ contacts: OperatorContact[] }>(
      `/api/v1/operator/orgs/${encodeURIComponent(slug)}/contacts`,
      { signal },
    ).then((data) => data.contacts);
  }

  /** `limit: null` is an unlimited override, not "remove" — that is
   *  {@link clearCredentialQuota}. */
  setCredentialQuota(
    slug: string,
    input: { limit: number | null; reason: string },
    signal?: AbortSignal,
  ): Promise<OperatorQuotaResult> {
    return this.request<OperatorQuotaResult>(
      `/api/v1/operator/orgs/${encodeURIComponent(slug)}/credential-quota`,
      { method: "PUT", json: { limit: input.limit, reason: input.reason }, signal },
    );
  }

  clearCredentialQuota(slug: string, reason: string, signal?: AbortSignal): Promise<OperatorQuotaResult> {
    return this.request<OperatorQuotaResult>(
      `/api/v1/operator/orgs/${encodeURIComponent(slug)}/credential-quota`,
      { method: "DELETE", json: { reason }, signal },
    );
  }

  /** Move an org to another plan without payment. Clears any override. */
  setOrgTier(
    slug: string,
    input: { tier: string; reason: string },
    signal?: AbortSignal,
  ): Promise<OperatorTierResult> {
    return this.request<OperatorTierResult>(
      `/api/v1/operator/orgs/${encodeURIComponent(slug)}/tier`,
      { method: "PUT", json: { tier: input.tier, reason: input.reason }, signal },
    );
  }

  /** Every org's credential emails, newest first. `org` narrows to one slug. */
  listOperatorDeliveries(
    query: OperatorDeliveryQuery & { limit?: number; offset?: number; cursor?: string | null } = {},
    signal?: AbortSignal,
  ): Promise<OperatorDeliveryPage> {
    return this.request<OperatorDeliveryPage>("/api/v1/operator/deliveries", {
      query: {
        ...deliveryQuery(query),
        limit: query.limit,
        offset: query.offset || undefined,
        cursor: query.cursor,
      },
      signal,
    });
  }

  /** The filtered view as CSV (at most 10,000 rows; `truncated` says if cut). */
  async exportOperatorDeliveries(
    query: OperatorDeliveryQuery = {},
    signal?: AbortSignal,
  ): Promise<{ blob: Blob; filename: string; total: number; truncated: boolean }> {
    const { blob, headers } = await this.requestFile("/api/v1/operator/deliveries/export", {
      query: deliveryQuery(query),
      signal,
    });
    const disposition = headers.get("content-disposition") ?? "";
    const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? "certforge-deliveries.csv";
    return {
      blob,
      filename,
      total: Number(headers.get("x-export-total") ?? 0),
      truncated: headers.get("x-export-truncated") === "true",
    };
  }

  /** Resend one credential's email. `idempotencyKey` is one per confirmation:
   *  a repeat is answered from the first request (`replayed: true`), never resent. */
  resendOperatorDelivery(
    publicId: string,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<OperatorResendResult> {
    return this.request<OperatorResendResult>(
      `/api/v1/operator/deliveries/${encodeURIComponent(publicId)}/resend`,
      { method: "POST", headers: { "Idempotency-Key": idempotencyKey }, signal },
    );
  }

  // --- passports, claims, verification ---
  getPassport(username: string, signal?: AbortSignal): Promise<PassportView> {
    return this.request<PassportView>(`/api/v1/passports/${encodeURIComponent(username)}`, {
      anonymous: true,
      signal,
    });
  }

  /** `token` is the `?t=` of the claim link in the delivery email. The holder
   *  of an already-claimed credential may omit it. */
  claimCredential(
    credentialId: string,
    token?: string | null,
    signal?: AbortSignal,
  ): Promise<ClaimResult> {
    return this.request<ClaimResult>(`/api/v1/claims/${encodeURIComponent(credentialId)}`, {
      method: "POST",
      json: { token: token || null },
      signal,
    });
  }

  verifyCredential(credentialId: string, signal?: AbortSignal): Promise<VerifiedCredential> {
    return this.request<VerifiedCredential>(`/api/v1/verify/${encodeURIComponent(credentialId)}`, {
      anonymous: true,
      signal,
    });
  }

  /** Public, human-readable verification page. Served by the API host, not this app. */
  verificationPageUrl(credentialId: string): string {
    return `${this.baseUrl}/verify/${encodeURIComponent(credentialId)}`;
  }

  /** The Open Badges 3.0 document for a credential — the machine-readable half
   *  of the same claim the verification page makes in prose. Public and
   *  unauthenticated, like the page: the ID is the capability. */
  badgeUrl(credentialId: string): string {
    return `${this.baseUrl}/credentials/${encodeURIComponent(credentialId)}/badge.json`;
  }

  /** The certificate itself, rendered on demand. Nothing is stored, so this URL
   *  is always current with the credential and its template. */
  certificatePdfUrl(credentialId: string): string {
    return `${this.baseUrl}/credentials/${encodeURIComponent(credentialId)}/pdf`;
  }
}

/** Client for endpoints that never need a session. */
export const publicApi = new CertForgeClient();
