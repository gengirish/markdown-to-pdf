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

export interface TemplateSummary {
  id: string;
  name: string;
  variables: string[];
  is_default: boolean;
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
  source: string;
  id: string;
  name: string;
  title: string;
  issued_at: string;
  metadata: Record<string, unknown> | null;
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
}

/** Client for endpoints that never need a session. */
export const publicApi = new CertForgeClient();
