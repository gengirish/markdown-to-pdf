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

  /** True when the org has run out of monthly credential quota. */
  get isQuotaExceeded(): boolean {
    return this.status === 402;
  }
}

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
  logo_url: string | null;
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
  delivery_status: DeliveryStatus;
}

export interface CredentialPage {
  items: CredentialSummary[];
  total: number;
  limit: number;
  offset: number;
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

type QueryValue = string | number | boolean | undefined | null;

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  json?: unknown;
  form?: FormData;
  query?: Record<string, QueryValue>;
  signal?: AbortSignal;
  /** Skip the Authorization header. Public endpoints must work signed out. */
  anonymous?: boolean;
  /** Endpoint returns a bare body rather than the `{success, data}` envelope. */
  unenveloped?: boolean;
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
      if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
    }

    const headers: Record<string, string> = { Accept: "application/json" };
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
        cache: "no-store",
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
    const headers: Record<string, string> = { Accept: "application/pdf, application/json" };
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
      response = await fetch(new URL(this.baseUrl + path), {
        method: options.method ?? "GET",
        headers,
        body: options.json !== undefined ? JSON.stringify(options.json) : undefined,
        signal: options.signal,
        cache: "no-store",
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
      return await response.blob();
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

  // --- credentials ---
  listOrgCredentials(
    slug: string,
    page: { limit?: number; offset?: number } = {},
    signal?: AbortSignal,
  ): Promise<CredentialPage> {
    return this.request<CredentialPage>(`/api/v1/orgs/${encodeURIComponent(slug)}/credentials`, {
      query: { limit: page.limit, offset: page.offset },
      signal,
    });
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

  // --- passports, claims, verification ---
  getPassport(username: string, signal?: AbortSignal): Promise<PassportView> {
    return this.request<PassportView>(`/api/v1/passports/${encodeURIComponent(username)}`, {
      anonymous: true,
      signal,
    });
  }

  claimCredential(credentialId: string, signal?: AbortSignal): Promise<ClaimResult> {
    return this.request<ClaimResult>(`/api/v1/claims/${encodeURIComponent(credentialId)}`, {
      method: "POST",
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
