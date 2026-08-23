# CertForge — API-First Plan

Status: Wave 1 shipped (Phases 0–1 done, 3 part-done) · Updated: 2026-08-23 · Scope: whole product

**Decisions taken (2026-08-23):**

- CertForge ships as a **new product on new hosts**, alongside the frozen legacy product.
- Dashboard: `certforge.intelliforge.tech` · API: `api.certforge.intelliforge.tech`
- Dashboard v1 scope: **Full Credential Studio** — templates, CSV bulk issuance, passports, billing, developer console.
- Infrastructure: **one repo, one Fly app, one Neon project.** Only the Vercel project and the DNS records are new. Rationale in §2.

---

## 0. Progress

**Wave 1 merged at `9c3680e` — 72 tests passing, zero merge conflicts.** Five packages landed in parallel worktrees (W0, A1–A5); see [subagent-handover.md](./subagent-handover.md) for the per-package outcome. C3, H3–H9 and M4–M7 that Wave 1 did not cover are tracked there against B1 and later waves.

A follow-up commit closed the CI blind spot that had hidden three separate breakages — CI built one of two frontends through a command that bypassed turbo, and never ran ESLint. It now builds both workspaces, lints, and fails if `.gitignore` hides source.

### Earlier — closed 2026-08-23 (separate session)

Staged in the working tree, verified against the code, not taken on report. **The pytest suite now passes 42/42, and the v1 route table is clean.**

| Item | Was | Now | Evidence |
|---|---|---|---|
| **C1** JWT fallback | `except ImportError` decoded the token body and trusted it; PyJWT unpinned | `PyJWT[crypto]==2.10.1` pinned; `_require_pyjwt()` raises 503 rather than degrade. **The `require_org_role` JWT fast path is gone too** — the DB decides membership, so forged `org_id`/`org_role` claims are inert | `tests/test_security.py::test_forged_token_is_never_trusted`, `::test_missing_pyjwt_rejects_instead_of_decoding_unverified`, `::test_org_role_not_granted_by_jwt_claims_alone` |
| **C2** Razorpay default secret | `RAZORPAY_SECRET` defaulted to the public literal `"rzp_test_secret"` | Reads `RAZORPAY_WEBHOOK_SECRET`; unset → webhook raises 503 rather than returning 200 with an error body | `::test_webhook_rejects_the_old_default_secret`, `::test_webhook_without_a_configured_secret_rejects_everything` |
| **H2** Global rate-limit bucket | `req.client.host` = the proxy IP, no `--proxy-headers` | Dockerfile passes `--proxy-headers --forwarded-allow-ips "*"`; `_client_ip()` takes the **rightmost** `X-Forwarded-For` entry, so a client cannot spoof its own bucket by prepending a header | `::test_client_ip_resolution`, `::test_callers_behind_the_proxy_get_separate_buckets` |
| **§4 gap 3** Double `/api/v1` prefix | `/api/v1/api/v1/orgs`, `…/templates`, `…/verify` | Router prefixes are relative; one `prefix="/api/v1"` at `include_router`; public routes on a separate `verify_public_router` | Route dump is clean; the 8 previously-failing tests pass |
| **§4 gap 4** Verification 404s | `/verify/*`, `/credentials/*` fell through to the SPA | Both added to `vercel.json` rewrites; routes now resolve to `/verify/{id}` and `/credentials/{id}/badge.json` | Route dump |
| **H1** `badge.json` `NameError` | `Organization` undefined | Imported at `verify.py:12`; the `F821` per-file ignore is gone from `ruff.toml` | Suite green |
| **Phase 0** | Suite red, CI never ran it | `pytest.ini` added, `test_developers.py` import fixed, `conftest.py` fixed, `ci.yml` updated, `tests/test_security.py` added | **42 passed** |

Each fix shipped with a regression test naming the original bug. That is the right shape — it is what stops these from coming back.

### Still open after that pass

**C3** (spoofable same-origin bypass — `_is_browser_same_origin` unchanged), **H3** (blocking PDF/email on the event loop), **H4** (`asyncio.create_task` at `studio.py:116`), **H5** (`UsageLedger` still never written), **H6** (raw f-string interpolation still at `verify.py:133-166`, plus a dead `/api/v1/verify/{id}/download` link), **H7** (no Clerk webhook), **H8** (`AuthenticatedUser` still has no `email`; `passports.py:33` reads it), **H9** (templates gated behind mocked billing), **M4** (`worker.py:143` still hardcoded), **M5** (CORS still `*`), **M6**, **M7** — and all of Phase 2.

Two notes on what landed:

- `RATE_LIMIT` is hardcoded to `10` at `index.py:160` and no longer reads `RATE_LIMIT_MAX_REQUESTS`, while `config.py:135` still parses that env var. Now that the limiter binds per real client for the first time, 10/60s is a reasonable ceiling for certificate creation — but the env var is dead, so decide whether to wire it back or delete it.
- `verify.py` now falls back to `SITE_URL`, but `worker.py:143` still hardcodes the legacy domain. That one matters for CertForge: it is what builds the verify URL baked into every new credential's QR code, and it needs `CERTFORGE_WEB_URL` in Phase 3.

---

## 1. Ground truth

Verified against the running deployment, not the docs.

| Piece | Reality |
|---|---|
| `certs.intelliforge.tech` | Vercel project `markdown-to-pdf` (git-linked to `gengirish/markdown-to-pdf`), serving `apps/legacy-web` (Vite SPA) |
| API | Fly.io `certforge-api.fly.dev`. FastAPI, scale-to-zero, one `shared-cpu-1x` / 512 MB machine |
| Routing | `vercel.json` rewrites `/api/*`, `/certificate/*`, `/invoice/*`, `/docs`, `/openapi.json`, `/llms.txt`, `/robots.txt`, `/sitemap.xml`, `/.well-known/*` to Fly. Everything else falls through to the SPA |
| DB | One Neon Postgres, reached through **two independent layers**: raw psycopg2 (`api/db.py`, legacy certs/courses) and SQLAlchemy + Alembic (`api/models/*`, CertForge) |
| Queue | Procrastinate worker embedded in the FastAPI lifespan, on the same single machine |
| `apps/web` | Next.js 16 + Clerk. Home page is the `create-next-app` template; `/passport`, `/claim`, `/org/[slug]/dashboard` render **mock data driven by `setTimeout`** |
| Vercel project `web` | `prj_RpzFnW2ttKLZTBxlYMBWegjNCSCc`. **Publicly deployed** at `web-puce-xi-31.vercel.app` — the mock dashboard is on the open internet. Not git-linked (`link: null`); pushed by CLI |

**Live and load-bearing:** `POST /api/certificate`, `POST /api/invoice`, `GET /certificate/{token}` (+ `/download`, `/verify`), `GET /invoice/{token}/download`, `POST /api/certificates/verify`, `/api/courses`, `/api/info`, `/api/health`, `/api/admin/*`, and the `sdk/pdfcert` client.

**Shipped but reaching nobody:** the entire `/api/v1` CertForge surface. Zero consumers — the only frontend that could call it uses mock data, and the SDK only speaks legacy. That asymmetry is what makes this whole plan safe.

### Do this today, before anything else

The mock dashboard is publicly reachable at `web-puce-xi-31.vercel.app`. Turn on Vercel Deployment Protection (Standard Protection) for project `web` now. A dashboard that fabricates successful batch uploads is not something to leave discoverable while carrying the CertForge name.

---

## 2. Infrastructure: what actually needs to be new

You offered a new repo, Vercel project, Fly app and Neon project. Only one of those earns its keep.

### New Vercel project — yes, but reuse the one you have

Rename `web` to `certforge`, connect it to `gengirish/markdown-to-pdf`, set **Root Directory** to `apps/web`, and add an Ignored Build Step so pushes that do not touch `apps/web` skip the build (`npx turbo-ignore` works with the turbo config already in the repo). Do not create a third project — `web` already has the deployment history and the project ID the repo's `apps/web/.vercel/project.json` points at.

### New git repo — no

The monorepo boundary is already in the right place: `apps/web` is its own npm workspace with its own `.vercel/project.json`, and Vercel's root-directory setting gives you the deploy isolation a separate repo would. What a split would actually cost you is coordination: the API contract, the shared service layer, the SDK and the contract tests would straddle two repos and need independent versioning and release choreography. That overhead buys nothing at one-engineer scale, and it makes the single most important guarantee in this plan — *the contract test runs against the code it protects, on every PR* — harder to keep true.

### New Fly app — no, but fix the process topology

Two Fly apps means either two deployments of one FastAPI codebase or a fork of it. The Phase 2 service layer is deliberately shared by both surfaces; forking it recreates the exact duplication already rotting between `index.py` and `api/core/`.

What you actually want from a split is blast-radius isolation, and there is a cheaper, more precise way to get it — see the worker topology callout in Phase 4. Today one 512 MB shared vCPU runs the HTTP server *and* the bulk-issuance worker, so a large CSV job and live certificate issuance compete for the same core. That is the real risk, and a second Fly *app* does not fix it; a second Fly *process group* does.

### New Neon project — no

The CertForge tables are already logically separate (Alembic-managed) from the legacy tables (raw `SCHEMA_SQL`). A second Neon project means a second compute that suspends and wakes on its own schedule, a second connection budget, and no ability to ever join across the two — which you will want the first time someone asks "show me everything issued to this recipient." If you later need isolation for a migration or a load test, Neon branching gives it for free and reversibly.

**Net: one CNAME, one Fly certificate, one Vercel project rename.** Everything else stays where it is.

---

## 3. Target topology

| Host | Serves | Backed by |
|---|---|---|
| `certs.intelliforge.tech` | Legacy SPA + legacy certificate/invoice API. **Frozen.** | Vercel `markdown-to-pdf` → `apps/legacy-web`; existing rewrites → Fly |
| `certforge.intelliforge.tech` | Credential Studio (authenticated) and the public human-facing pages: `/verify/{id}`, `/passport/{username}`, `/claim/{id}`, `/orgs/{slug}` | Vercel `certforge` → `apps/web` |
| `api.certforge.intelliforge.tech` | The API: `/api/v1/*`, `/credentials/{id}/badge.json`, `/openapi.json`, `/docs`, `/llms.txt` | Fly `certforge-api` — same app, new certificate |

**The split is human-facing versus machine-facing, not frontend versus backend.** Public credential pages render server-side in Next.js by calling the API, which gets you real SSR, correct OG tags and JSON-LD for free — and, more importantly, removes the new product's dependence on `vercel.json`'s rewrite list entirely. That list is precisely how the Open Badges surface came to 404 in production while working locally.

`certforge.sh` is the only recognizable CertForge apex still available ($22/yr); `.dev`, `.io`, `.tech` and `.app` are all taken. Nothing in this plan assumes a subdomain — the hosts are three environment variables — so buying a standalone apex later is a config change, not a migration.

### DNS and certificates

```
certforge.intelliforge.tech       CNAME  cname.vercel-dns.com     # add domain in Vercel project "certforge"
api.certforge.intelliforge.tech   CNAME  certforge-api.fly.dev    # then: fly certs add api.certforge.intelliforge.tech
```

### Environment variables

`SITE_URL` currently resolves to `https://certs.intelliforge.tech` and is what builds **legacy** certificate links and QR targets. **Do not repoint it.** Every QR code already printed on a PDF resolves through it. Add new keys instead:

```
SITE_URL=https://certs.intelliforge.tech            # unchanged — legacy links and QR targets
CERTFORGE_WEB_URL=https://certforge.intelliforge.tech
CERTFORGE_API_URL=https://api.certforge.intelliforge.tech
```

New CertForge credentials build their verify URLs from `CERTFORGE_WEB_URL`. Clerk also needs `certforge.intelliforge.tech` in its allowed origins, and the publishable key set on the Vercel project.

---

## 4. Why this is not an API-first product yet

Five structural gaps, each verified in the code.

**There is no way to authenticate as a machine.** `POST /api/v1/orgs/{slug}/api-keys` mints `cf_live_…` keys and stores SHA-256 hashes. Nothing anywhere reads them back — grep for `ApiKey` outside `models/api_key.py` and `routes/developers.py` returns nothing. Every v1 write route depends on `get_current_user`, which requires a Clerk **browser session** JWT. A customer can create an API key and then has no endpoint that accepts it.

**There is no single-credential issuance endpoint.** The only path is `POST /api/v1/orgs/{slug}/credentials/bulk` — a `multipart/form-data` CSV upload.

**Half the v1 surface is unreachable.** `index.py:306-314` mounts routers with `prefix="/api/v1"`, but `orgs.py:12`, `studio.py:18` and `templates.py:13` already declare absolute `/api/v1/…` prefixes. From the live `openapi.json`:

```
/api/v1/api/v1/orgs
/api/v1/api/v1/orgs/{slug}/credentials/bulk
/api/v1/api/v1/templates
/api/v1/api/v1/verify/{credential_id}
```

**The public verification surface 404s in production.** `/verify/{id}` and `/credentials/{id}/badge.json` are absent from the rewrite list, so they serve the SPA shell (`200 text/html`, verified live). Open Badges 3.0 is unreachable, and the badge JSON points `achievement.id` at a route that does not exist.

**There is no contract discipline.** The global handler at `index.py:338` emits `{"error": {…}}` with no `success` field, overriding the `ApiResponse` envelope v1 routes advertise. `billing.py` returns `ApiResponse.fail(code=404)` with **HTTP 200**. No pagination convention, no idempotency on v1, no per-key rate limits, no usage metering.

---

## 5. Defects

**LIVE** marks defects on the running product; the rest are on the unreleased v1 surface. **STUDIO** marks ones that specifically block the Full Credential Studio scope.

### Critical

**C1 — CLOSED 2026-08-23 — Unsigned JWTs accepted when PyJWT is absent.** `core/auth.py:57-68`: if `import jwt` fails, the code base64-decodes the token body and trusts it. `requirements.txt` does not list PyJWT — it is present today only transitively and unpinned, so any rebuild can silently flip this on. With `require_org_role`'s JWT fast path (`auth.py:139`), a forged token carrying `org_id` + `org_role: "owner"` would grant full control of any organization. *Pin `PyJWT[crypto]`, delete the fallback, fail closed.*

**C2 — CLOSED 2026-08-23 — Razorpay webhook accepts a signature made with a known default.** `config.py:37` defaults `RAZORPAY_SECRET` to the literal `"rzp_test_secret"`; `billing.py:39` HMACs against it. Anyone can post `subscription.activated` and upgrade any org's tier and quota. *No default; refuse to register the route when unset.*

**C3 — LIVE — API-key auth is bypassable by a header.** `index.py:220-240` `_is_browser_same_origin` compares client-supplied `Origin`/`Referer` against the site URL. Both are trivially spoofable, so `CERT_API_KEYS` on `POST /api/certificate` and `/api/invoice` is advisory. *Phase 3 makes this obsolete for CertForge — the API gets its own host and a real key check. Legacy still needs a CSRF-cookie gate.*

### High

**H1 — CLOSED 2026-08-23 — `badge.json` raises `NameError`.** `verify.py:68` uses `Organization`; it is never imported. Every call 500s. `ruff.toml` carries an explicit `"apps/api/api/routes/verify.py" = ["F821"]` ignore — the linter that exists to catch undefined names has been told to stay quiet about the one file with a real one.

**H2 — CLOSED 2026-08-23 — LIVE — Rate limiting is effectively global.** `_check_rate_limit` keys on `req.client.host`, and the Dockerfile starts uvicorn without `--proxy-headers`. Behind the Vercel→Fly rewrite every request presents the proxy's IP, so all customers share one 10-per-60s bucket.

**H3 — LIVE — Blocking work on the event loop.** `download_certificate` (`index.py:2255`) is `async def` and calls `_build_cert_pdf` — xhtml2pdf, synchronous, CPU-heavy — inline. `generate_certificate` calls `_run_with_timeout(_send_email, 20.0)` at `index.py:1812`, also inline. One shared vCPU, `soft_limit = 20`: a single slow AgentMail call stalls the machine for up to twenty seconds.

**H4 — STUDIO — Bulk dispatch is fire-and-forget.** `studio.py:114` calls `asyncio.create_task(…)` without holding the reference: the task may be garbage-collected before running, and exceptions are swallowed. It also reads `batch.id/.total/.status` after the session closed. Batches can 200 and never process.

**H5 — STUDIO — Quota enforcement is inert.** `studio.py:70` reads `UsageLedger`; **nothing ever writes to it**. `used` is always 0, `monthly_quota` never binds, and the billing tiers in `config.py` are decoration.

**H6 — XSS in the credential viewer.** `verify.py:95-175` interpolates `recipient_name`, `title` and `metadata` into an HTML f-string with no escaping. Names arrive from customer-uploaded CSVs.

**H7 — STUDIO — There is no Clerk webhook handler.** `CLERK_WEBHOOK_SECRET` is configured and `orgs.py` documents itself as "usually called by Clerk webhooks", but no such route exists in the app. Organizations created in Clerk never reach your database, and `OrgMember` rows appear only if someone calls `POST /api/v1/orgs` by hand. Studio onboarding has no working path.

**H8 — STUDIO — Claiming a credential crashes.** `passports.py:33` reads `user.email`, but `AuthenticatedUser` (`core/auth.py:26`) defines only `clerk_user_id`, `clerk_org_id`, `clerk_org_role`. First claim raises `AttributeError`. The same mismatch makes `tests/conftest.py`'s fixture (`session_id=`, `email=`) a `TypeError`, which is part of why the suite is red.

**H9 — STUDIO — Custom templates are unreachable end to end.** `templates.py:71` rejects `tier == "community"`, and the only route out of community tier is `billing.py`'s **mocked** checkout, which returns a fake `rzp.io/i/mock_…` URL. No customer can reach the feature.

### Medium

- **M1 — CLOSED 2026-08-23** — Suite is red and CI does not run it. `tests/test_developers.py` fails to import (`No module named 'api.tests'`); of the rest **8 fail, 12 pass**. `ci.yml` runs ruff, `test_api.py`, `test_sdk.py`, a Vite build and Playwright — never pytest.
- **M2** — `VIEWER_INTERNSHIP_HTML.format(…)` at `verify.py:110` omits `meta_description` → `KeyError` on every legacy internship view through that path.
- **M3** — `procrastinate`, `sqlalchemy`, `alembic`, `psycopg[binary]` unpinned; `razorpay` and `PyJWT` absent. Builds are not reproducible.
- **M4** — `https://certs.intelliforge.tech` hardcoded in `worker.py:143`, `verify.py:79/87/108`, `index.py:726`.
- **M5** — `CORSMiddleware(allow_origins=["*"], allow_methods=["*"])` on an API about to carry bearer tokens across origins.
- **M6** — `apps/web` reads `params.credential_id` synchronously; in Next.js 16 `params` is a Promise. Every dynamic route is broken as written.
- **M7** — `CLAUDE.md` still describes the pre-monorepo layout. Every path in it is stale.

---

## 6. The freeze contract

**Frozen permanently — breaking any of these invalidates certificates already in circulation:**

- Token format: `base64url(compact_json) + "." + hmac_sha256_hex`
- Single-letter payload keys `n c d i k u w h m s r e v p` — never rename, reorder, or repurpose. New fields are new optional keys only.
- `CERT_SECRET_KEY`. Rotation only via `CERT_ROTATED_SECRET_KEYS`.
- `_cert_id()`'s hashing rule — it is the ID printed on the PDF.
- `SITE_URL = https://certs.intelliforge.tech`. Every QR already in the world resolves through it.

**Frozen for the duration of this plan:** request/response shapes and status codes for `POST /api/certificate`, `POST /api/invoice`, `GET /certificate/{token}` (+ `/download`, `/verify`), `GET /invoice/{token}/download`, `POST /api/certificates/verify`, `/api/courses`, `/api/info`, `/api/health`, `/api/admin/*` — including the legacy `{"error": {…}}` envelope. `sdk/pdfcert` and the live SPA depend on them verbatim.

**Free to change:** everything under `/api/v1`, all of `apps/web`, `apps/legacy-web` internals, `api/core/*`, the Alembic-managed tables.

**Enforcement, added in Phase 0:** a contract test pinning the exact JSON shape of every frozen endpoint plus a fixture of pre-existing tokens asserted to keep verifying, in CI on every PR. That test, not discipline, keeps this promise.

---

## 7. Phases

### Phase 0 — Safety net · ~~0.5 day~~ **DONE 2026-08-23**

1. Fix `tests/test_developers.py:6` (`from api.tests.conftest` → `from tests.conftest`); add `apps/api/pytest.ini` with `testpaths = tests`.
2. Fix `conftest.py`'s `AuthenticatedUser(session_id=…, email=…)` fixture to match the real dataclass — or fix the dataclass, per H8.
3. Add a `test-api-unit` job to `ci.yml` running `pytest apps/api/tests`. Expect it red.
4. Add `tests/test_contract_legacy.py`: golden-file assertions on every frozen endpoint plus historical tokens that must still verify.
5. Drop the `verify.py = ["F821"]` ignore from `ruff.toml`; widen `select` to `["E9","F"]` for `api/core/` and `api/routes/`.

**Exit — met, and then some.** The suite is not red but green: 42 passed. The double-prefix failures were fixed in the same pass.

### Phase 1 — Close the holes · ~~1 day~~ **~0.5 day left**

**Done:** C1, C2, H1, H2, M3. **Remaining:** H6, H8, M4, M5 — plus the `RATE_LIMIT` env-var decision noted in §0.

- Add `email` to `AuthenticatedUser` and populate it from the Clerk claim (H8) — `passports.py:33` reads it today and raises `AttributeError` on first claim.
- Escape every interpolation in `verify.py:133-166`, or move the viewer to a Jinja template with autoescaping (H6). Fix the dead `/api/v1/verify/{id}/download` link while you are in there.
- Replace `worker.py:143`'s hardcoded domain with the resolver (M4).
- Allow-list CORS origins; drop `*` (M5). Can be folded into Phase 3, where the origins are known.

**Exit:** suite still green, and the credential viewer survives a recipient named `<script>alert(1)</script>`.

### Phase 2 — API-first core · 3 days

**2a. Extract a service layer.** `api/services/issuance.py` holds the one true "issue a credential" function: validate, generate ID, sign, persist, enqueue PDF and email, fire webhooks. Plain dataclass in, plain dataclass out; it knows nothing about FastAPI, Clerk, or CSV.

`POST /api/certificate` (legacy, byte-identical) and `POST /api/v1/credentials` both become **thin adapters over that one function**. This is the mechanism by which the legacy surface stays frozen while the product moves: one implementation, two vocabularies. Do it before adding endpoints, or you maintain the logic twice — exactly what `index.py` and `api/core/` already do.

**2b. Make API keys work.** `api/core/api_key_auth.py`:

- `resolve_principal(request)` → `Principal(org_id, kind, scopes)`, accepting **either** `Authorization: Bearer cf_live_…` (SHA-256 lookup, constant-time compare, `revoked_at IS NULL`, `last_used_at` bumped async) **or** a verified Clerk JWT.
- Every v1 route swaps `Depends(get_current_user)` → `Depends(resolve_principal)`. A key is scoped to one org, so cross-org access collapses to an equality check.
- Issue `cf_test_…` alongside `cf_live_…`. Test keys write to the DB but never email and never bill. Cheap now, painful to retrofit.

**2c. Resource surface.** `POST /api/v1/credentials` (single, sync, returns credential + URLs), `POST /api/v1/credentials/batch` (JSON array — CSV becomes a client-side convenience, not the only door), `GET /api/v1/credentials` with cursor pagination, `GET /{id}`, `POST /{id}/revoke`, `GET /{id}/pdf`. Wire usage metering into the service layer so `UsageLedger` is finally written (H5); return `X-Quota-Limit` / `X-Quota-Remaining`.

**Exit:** a bare `curl` with a `cf_test_…` key issues a credential end to end, and `POST /api/certificate` returns bytes identical to today.

### Phase 3 — Split the hosts · ~~1.5 days~~ **~1 day left**

**Done:** the prefix strip and the `vercel.json` rewrites for `/verify/*` and `/credentials/*`.

- `fly certs add api.certforge.intelliforge.tech`; add the CNAME.
- Rename Vercel `web` → `certforge`, git-link it, root directory `apps/web`, `turbo-ignore` as the ignored build step, add the domain.
- Add `CERTFORGE_WEB_URL` / `CERTFORGE_API_URL`; leave `SITE_URL` alone.
- CORS allow-list: `CERTFORGE_WEB_URL` plus Vercel preview origins. Drop `*`.
- One envelope: the global handler emits `{"success": false, "error": {…}}` for `/api/v1/*` and keeps the bare `{"error": {…}}` for legacy. Branch on path; pin both in the contract test.
- Fix `billing.py` to raise `HTTPException` so status codes match bodies.
- `badge.json` builds URLs from `CERTFORGE_WEB_URL`; `achievement.id` points at a route that exists.

### Phase 4 — Studio backend · 4 days

The pieces Full Credential Studio needs that are missing or broken.

- **Clerk webhook handler (H7)** — new `routes/webhooks_clerk.py`, Svix signature verification, handling `organization.created/updated`, `organizationMembership.created/deleted`, `user.created`. Without this there is no onboarding path at all.
- **Real Razorpay (C2, H9)** — actual order/subscription creation, verified webhook, tier and quota transitions. Until this exists, custom templates are unreachable by any customer.
- **Templates** — complete CRUD, seed the global defaults (`api/seed.py` already exists for this), tier gating that a customer can actually satisfy.
- **Batch pipeline (H4, H5)** — awaited `defer_async` inside the transaction that creates the batch, so a batch row cannot exist without a queued job; quota writes on issuance; batch progress events for the UI.
- **Passports** — `GET /passports/{username}`, `POST /claims/{id}` working end to end after the H8 fix; pin/reorder endpoints for the profile UI.

> **Worker topology — decide here.** Today one 512 MB shared vCPU runs the HTTP server *and* the Procrastinate worker, with `auto_stop_machines = "stop"` and `min_machines_running = 0`. That was deliberate: closing the worker's `LISTEN` connection is what lets Neon autosuspend. Under Studio volume it breaks in three ways — a batch deferred just before idle-stop dies when the lifespan cancels the worker; after the machine stops nothing wakes it, so a pending batch waits for the next unrelated HTTP request; and bulk PDF rendering competes with live issuance for one core.
>
> **Recommended:** split `fly.toml` into `[processes]` — `app` (HTTP, scale-to-zero exactly as today) and `worker` (`min_machines_running = 1`). Cost is roughly $2–4/mo of Fly plus Neon compute no longer autosuspending. **The cheaper alternative**, if that Neon bill matters more than batch latency: render batches of ≤50 rows synchronously in a threadpool and queue only larger ones, keeping the machine awake via Fly's Machines API until the queue drains. More code, lower running cost. Pick one before building the Studio UI on top of it.

### Phase 5 — Studio frontend · 5 days

Delete every mock. `apps/web` today is `create-next-app` plus three `setTimeout` fictions.

- Fix Next.js 16 async `params` across all dynamic routes (M6).
- A real API client with Clerk token attachment, typed against the OpenAPI schema.
- **Authenticated:** onboarding and org creation, credential list + single issue, template gallery and editor, CSV bulk upload with live batch progress, developer console (API keys, webhooks, usage against quota), billing and plan.
- **Public, server-rendered:** `/verify/{id}` with JSON-LD and OG tags, `/passport/{username}`, `/claim/{id}`, `/orgs/{slug}`.

### Phase 6 — Performance and cost · 2 days

- **Cache certificate views at the CDN.** A given token always renders the same bytes. `Cache-Control: public, max-age=31536000, immutable` on `/certificate/{token}` and its `/download` moves nearly all read traffic to the edge. Highest-leverage single change here: p95 view latency to near zero, and the Fly machine stays asleep, cutting both Fly and Neon spend. Revocation is the wrinkle — serve revoked certs from a short-TTL path and purge on revoke, or cap the TTL near five minutes to bound staleness.
- **H3** — convert `download_certificate` / `download_invoice` to `def` so FastAPI threadpools them; move email into the queue so `POST /api/certificate` returns as soon as the token is signed.
- Measure cold start before reaching for `min_machines_running` on the `app` process.

### Phase 7 — Developer experience · 2 days

- **OpenAPI becomes the source of truth.** After Phase 3 it is accurate. Generate SDKs from it; keep `sdk/pdfcert`'s legacy methods as a thin deprecated shim over the generated v1 client so existing installs keep working.
- Rewrite `_build_llms_txt` / `_build_sitemap_xml` for the v1 surface on the API host.
- A quickstart that is `curl` plus an API key and nothing else. If a developer cannot issue their first credential without opening a browser, the product is not API-first regardless of what the endpoints look like.
- Webhook delivery gets retries with backoff and a `GET /api/v1/webhook-deliveries` log. Today `worker.py:220` posts once with a 5s timeout and logs failures — a customer whose endpoint blips loses the event silently.

### Phase 8 — Retire the legacy surface · later

Only once CertForge covers the participation, VTU internship and appreciation kinds. Then `certs.intelliforge.tech` becomes a redirect, and `/certificate/{token}` stays forever as a resolver for tokens already in the world. **That route never dies** — printed QR codes have no expiry.

---

## 8. Sequencing and risk

| Phase | Effort | Touches live? | Risk |
|---|---|---|---|
| 0 — Safety net | ~~0.5d~~ done | no | — |
| 1 — Security | ~0.5d left | CORS | low — the live-touching parts already shipped |
| 2 — API-first core | 3d | new code paths only | medium — service extraction, guarded by contract test |
| 3 — Split the hosts | ~1d left | DNS, Vercel project | low — new hosts, nothing repointed |
| 4 — Studio backend | 4d | Fly process topology | medium — worker split changes the cost profile |
| 5 — Studio frontend | 5d | no | low — new surface, no legacy dependency |
| 6 — Performance | 2d | yes — caching, threading | medium — cache TTL against revocation |
| 7 — Developer experience | 2d | no | low |
| 8 — Retire legacy | later | yes | high — do only when coverage is proven |

**Total to a shipped Full Credential Studio: ~17.5 working days remaining** (down from ~19 — Phase 0 is done and Phases 1 and 3 are part-done).

**Ordering constraints.** 0 before everything. 2 before 3 — fixing the paths first would make the double-prefixed routes look production-ready while they still lack API-key auth. 4 before 5 — do not build UI against endpoints that are still mocked. 6 after 2 — do not optimize code you are about to move.

**Rules for every phase.**

- One phase per PR; contract test green before merge.
- Fly deploys are immutable and instant to roll back — `fly releases`, then `fly deploy --image <previous>`. Verify `/api/health` and one real certificate URL after each deploy.
- Never touch `CERT_SECRET_KEY` or `SITE_URL`. Every token and every printed QR depends on them.
