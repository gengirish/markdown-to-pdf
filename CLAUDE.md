# CLAUDE.md

Guidance for Claude Code (claude.ai/code) and for anyone new to this repository.

Read the freeze contract below before you edit anything under `apps/api/`. It is not
boilerplate — the legacy surface is live and has certificates printed on paper.

## What this is

CertForge issues verifiable credentials. Two products share one codebase and one
FastAPI process:

- **Legacy (live).** An API-first generator for tamper-proof PDF certificates
  (participation, VTU internship, event appreciation) and tax invoices. Certificate
  data lives entirely inside an HMAC-SHA256-signed URL token — no database is needed
  to issue, view, or verify a document. Served at `certs.intelliforge.tech`.
- **CertForge (in progress).** A multi-tenant credentialing product — organizations,
  templates, credential batches, passports, Open Badges, API keys, billing — under
  `/api/v1`, backed by Postgres. Dashboard at `certforge.intelliforge.tech`.

## Layout

```
apps/api/            FastAPI backend. Docker image, deployed to Fly.io as `certforge-api`.
  api/index.py       the legacy surface — ~2900 lines, frozen (see below)
  api/core/          config, auth (Clerk), crypto, envelope, worker, pdf_renderer, email
  api/routes/        the /api/v1 CertForge surface — thin adapters over api/services/
  api/services/      issuance, delivery, rendering — one implementation per concern,
                     shared by the single and bulk paths so they cannot drift
  api/models/        SQLAlchemy 2.0 models
  api/migrations/    Alembic
  tests/             pytest — must stay green
  test_api.py        live-server integration script (not pytest)
apps/legacy-web/     Vite + React 19 SPA. LIVE at certs.intelliforge.tech.
apps/web/            Next.js 16 + Clerk. The CertForge dashboard; a real client of
                     /api/v1 through lib/api.ts — no mock data, no route handlers.
sdk/                 installable Python client for the legacy API (`pdfcert`)
e2e/                 Playwright specs, run from the repo root
examples/            runnable scripts: bulk onboarding, batch verify, webhooks, Zapier
docs/                plans, handover notes, the VTU internship field mapping
```

`apps/web/` has its own `CLAUDE.md` and `AGENTS.md`. Read those before touching it.

## Hosts

Three of them, and picking the wrong one to build a URL from is a correctness bug, not
a style question. The constants live in `apps/api/api/core/config.py`.

| Host | Constant | What it is |
|---|---|---|
| `certs.intelliforge.tech` | `SITE_URL` | The legacy product. **Frozen.** Every certificate ever issued carries a QR code that resolves through it. |
| `certforge.intelliforge.tech` | `CERTFORGE_WEB_URL` | The CertForge dashboard and its public pages — `/verify/{id}`, `/passport/{username}`, `/claim/{id}`. New credentials build verify URLs from this, so it is what ends up inside a CertForge QR code. |
| `api.certforge.intelliforge.tech` | `CERTFORGE_API_URL` | The machine-facing host: `/api/v1`, `badge.json`, the OpenAPI schema. Points straight at Fly rather than through the Vercel rewrite, so customers get an API host that does not depend on the frontend's routing. |

## THE FREEZE CONTRACT

`certs.intelliforge.tech` is a live product. Certificates have been issued, and their
QR codes are printed on paper that nobody can reissue. The following are immutable —
not "prefer not to change", but *cannot* change:

- **The token format**: `base64url(compact_json)` + `"."` + `hmac_sha256_hex`.
- **The single-letter payload keys**: `n` name, `c` course, `d` date, `i` instructor,
  `k` kind, `u` USN, `w` duration, `h` hours, `m` mentor, `s` institution,
  `r` recognition, `e` event, `v` venue, `p` sponsor.
  Never rename, reorder, or repurpose one. New fields are new **optional** keys only.
- **`CERT_SECRET_KEY`** — changing it invalidates every certificate ever issued.
- **`SITE_URL`** — never repoint it. CertForge uses `CERTFORGE_WEB_URL` instead.
- **`_cert_id()`'s hashing rule** (`apps/api/api/index.py`) — that ID is printed on
  the PDF.
- **The request/response shape and status codes** of the legacy endpoints: `POST
  /api/certificate`, `POST /api/invoice`, `GET /certificate/{token}` (and
  `/download`, `/verify`), `GET /invoice/{token}/download`, `POST
  /api/certificates/verify`, `/api/courses`, `/api/info`, `/api/health`,
  `/api/admin/*`. That includes their bare error envelope,
  `{"error": {"code": …, "message": …, "type": …}}` — **not** the `/api/v1`
  `ApiResponse` envelope. `sdk/pdfcert` and the live SPA parse these verbatim.

Everything under `/api/v1`, all of `apps/web/`, and `apps/api/api/core/*` is free to
change.

## Commands

Verified against this repo. Prerequisites: `npm install` at the root, and
`pip install -r apps/api/requirements.txt`.

```bash
# Backend dev server (from apps/api — `api.index` must be importable)
cd apps/api && python -m uvicorn api.index:app --reload --port 8000

# Legacy SPA dev server; its vite proxy forwards /api, /certificate, /invoice to :8000
cd apps/legacy-web && npm run dev            # http://localhost:5173

# CertForge dashboard
cd apps/web && npm run dev                   # http://localhost:3000

# Build the legacy SPA — the same command Vercel and CI run
npm run build:web                            # -> apps/legacy-web/dist

# Python lint (the CI gate)
ruff check apps/api/api/ sdk/pdfcert/
```

### Tests

```bash
# Unit suite — SQLite-backed, no live server needed. Run this before you finish.
cd apps/api && python -m pytest

# Legacy integration script. Needs the API on http://localhost:8000 — the URL is
# hardcoded in the file, there is no env override.
cd apps/api && python test_api.py

# SDK suite, from the repo root, after `pip install -e ./sdk`.
# PDFCERT_URL overrides the base URL; it defaults to http://localhost:8000.
python sdk/test_sdk.py

# Playwright. Starts uvicorn (apps/api) and vite (apps/legacy-web) itself.
npm run test:e2e
npx playwright test --ui                     # interactive picker
E2E_BASE_URL=https://… npm run test:e2e      # run against a deployed URL
```

Two files in `apps/api/tests/` are **contract** tests and are the reason
`index.py` is safe to touch at all:

- `test_contract_legacy.py` pins the freeze contract. Its load-bearing part is
  three tokens — participation, VTU internship, appreciation — produced by the
  real encoder against a fixed secret and committed as literals. They stand in
  for every certificate already printed. Rename a payload key, reorder the JSON,
  change the separators or alter the signing input and they stop decoding.
  Nothing else in the suite would notice, because everything else generates its
  tokens with the same code it is testing.
- `test_contract_certforge.py` asserts that every URL a credential carries is
  served by the API **and**, when it names `CERTFORGE_WEB_URL`, carried there by
  a rewrite in `apps/web/vercel.json`. It reads those URLs off a real issuance
  rather than a hand-written list, so a newly emitted URL is covered the day it
  appears. It cannot check DNS — that is what the smoke script is for.

**House rule: a contract test that has never been seen to fail is a comment.**
Every guard in those files was verified by reintroducing the bug on purpose and
watching it fail. Keep doing that — two smoke assertions written for the
`/verify` 404 passed against a demonstrably broken host before they were checked
this way, because a `404` is also what Next.js returns for an unrouted path and
`application/json` is also what FastAPI's default 404 returns.

`test_api.py` and `sdk/test_sdk.py` are plain scripts, not pytest — there is no
per-test selector. Comment out entries in `run_all()` / `__main__` to narrow a run.
The real suite is `apps/api/tests/`, configured by `apps/api/pytest.ini`; its
`testpaths = tests` is what stops a bare `pytest` from walking into those two scripts.

CI (`.github/workflows/ci.yml`) runs seven jobs: `lint` (ruff), `test-unit`
(pytest), `test-api`, `test-sdk`, `build-frontend` (`npm run build:web`),
`test-e2e`, and `deploy-api` — the last only on `main`, which is what ships the
Fly release and runs Alembic through `release_command`.

`scripts/smoke_test.sh` is **not** a CI job. It is read-only and safe against
production (every check is a GET); run it after any deploy that touches hosts.
It takes an optional base URL, plus `SMOKE_CERTFORGE_WEB` and
`SMOKE_CERTFORGE_API` to point the two CertForge host sections elsewhere.

### One known pothole

The root turbo scripts used to be listed here as broken. They work now — the
`packageManager` field turbo was asking for is in the root `package.json`
(`npm@10.9.3`), and `npm run lint` resolves the workspace and runs both. The
per-app commands above are still the faster loop when you are working in one app.

- **PDF generation fails locally on Windows.** The certificate templates load
  `apps/api/api/fonts/EBGaramond-SemiBold.ttf` through `@font-face`; xhtml2pdf copies
  it to a `NamedTemporaryFile` that reportlab then cannot reopen, and
  `/certificate/{token}/download` answers 500 with a `TTFError`. It is a Windows file
  locking quirk, not a code defect — the same request works in CI and in the Docker
  image. Three of `test_api.py`'s cases fail for this reason on Windows.

## Architecture

### Stateless signed tokens (the legacy core idea)

`apps/api/api/index.py`, `_encode_cert` / `_decode_cert`: the payload is compact JSON
→ urlsafe base64 → `payload.hmac_sha256_hex`. Verification recomputes the HMAC with
`CERT_SECRET_KEY`; any mutation invalidates the token.

- **`k` selects the document kind**: absent or `participation`, `i` internship,
  `a` appreciation. `_certificate_kind_from_payload` is the dispatch point, and nearly
  every render path branches on it.
- Invoices use the same scheme with their own compaction helpers
  (`compact_invoice_token_payload` / `expand_invoice_token_payload` in
  `apps/api/api/invoice_utils.py`).
- `apps/api/api/core/legacy_tokens.py` decodes the same tokens for the `/api/v1`
  verification path. It and `index.py` must sign identically — they now both import
  `CERT_SECRET` from `api/core/config.py` rather than reading the env separately,
  because when each read it independently they picked different dev fallbacks and a
  token minted by one could never be verified by the other.

CertForge credentials are the opposite: DB rows with short public IDs.
`api/core/crypto.py` `is_legacy_cert_id` / `is_certforge_id` is how a verification
request is routed to the right one.

### Two database layers coexist

- **Raw psycopg2** — `apps/api/api/db.py`. Legacy certificates and courses. Schema is
  a `CREATE TABLE IF NOT EXISTS` block applied by `init_schema()`.
- **SQLAlchemy 2.0 + Alembic** — `apps/api/api/models/` (organizations, templates,
  credentials, passports, API keys, usage) with migrations in
  `apps/api/api/migrations/`.

They are not being merged right now. New CertForge work goes in the SQLAlchemy layer;
do not port legacy tables into it without a migration plan for live data.

### The database is optional for the legacy surface

`api/db.py` loads only when `DATABASE_URL` is set (`DB_AVAILABLE` /
`_ensure_db_ready()`). Without it: courses fall back to the hardcoded
`COURSES_FALLBACK` list in `index.py`, admin endpoints 503, revocation is a no-op, and
the Procrastinate worker stays off (`WORKER_ENABLED` in `api/core/worker.py`).
Verification of a legacy token never touches the DB. **Any new feature on the legacy
surface must degrade gracefully when the DB is absent.** `/api/v1` may require it.

### Rendering: three surfaces per document kind

Each document kind is rendered three separate times. Change a layout and you change
all three, or they drift:

1. **PDF** — HTML string templates in `apps/api/api/certificate_templates.py`
   (`CERTIFICATE_PARTICIPATION_HTML`, `CERTIFICATE_INTERNSHIP_VTU_HTML`,
   `CERTIFICATE_APPRECIATION_HTML`) and `apps/api/api/invoice_templates.py`, rendered
   by xhtml2pdf via `_build_cert_pdf` / `build_invoice_pdf`. **xhtml2pdf supports only
   a narrow CSS subset** — tables and inline styles, no flex, no grid; images must be
   base64 data URIs (see `_generate_qr_data_uri`, `_generate_signature_data_uri`,
   `apps/api/api/appreciation_assets.py`).
2. **Public viewer HTML** — `VIEWER_HTML` in `index.py`, `VIEWER_INTERNSHIP_HTML` /
   `VIEWER_APPRECIATION_HTML` in `certificate_templates.py`.
3. **Live React preview** — `CertificatePreviewCard` / `InvoicePreviewCard` in
   `apps/legacy-web/src/App.jsx`, which duplicate the layout in real CSS.

Shared logic all three depend on exists twice, once in each language:
`_norm_signatory` / `_unique_signatory_roles` / `resolve_appreciation_host_name` in
Python have `normSignatory` / `uniqueSignatoryRoles` / `resolveAppreciationHostName`
as JS twins in `App.jsx`. Change both.

`/api/v1` credentials render through `api/core/pdf_renderer.py` instead.

### Branding flows from env → `/api/info` → frontend

Branding is env-driven (`CERT_*`, `FOUNDER_*`, `INVOICE_*`; see the README table).
`certificate_branding()` in `index.py` and `invoice_brand_colors()` in
`api/invoice_brand.py` serialize it, `/api/info` exposes it, and the `useBranding` /
`useInvoiceBrand` hooks in `apps/legacy-web/src/App.jsx` consume it. **Never hardcode
a brand string or color in a template** — add an env-backed key instead. Env reads go
through `_sanitize_env` (in both `index.py` and `core/config.py`), which strips the
literal `\r\n` that copy-pasted dashboard values pick up.

### Deploy topology

The API is a Docker container on Fly.io (`apps/api/Dockerfile`, `apps/api/fly.toml`,
app `certforge-api`, region `iad`). It is **not** a Vercel Function any more. Vercel
builds and serves the legacy SPA and rewrites a fixed list of paths through to Fly.

Things that follow from that, all of them load-bearing:

- **New backend routes must be added to `vercel.json`'s rewrite list, or they 404 in
  production while working perfectly in local dev.** This is not hypothetical:
  `/verify/*` and `/credentials/*` were missing and served the SPA shell in production
  until commit `3b52e72`. The catch-all `/((?!assets/|branding/).*)` swallows anything
  not listed.
- `request.base_url` is the Fly hostname, not the public domain. `_resolve_site_url`
  and `_is_browser_same_origin` accept either, which is why `SITE_URL` is set in
  `fly.toml` rather than inferred.
- `TRUSTED_PROXY_HOPS` defaults to `2` because the chain is browser → Vercel edge →
  Fly proxy; the real client is the second entry from the right of `X-Forwarded-For`.
- `ENV=production` is set in `fly.toml` because `IS_PROD` keys off `VERCEL_ENV` or
  `ENV`, and nothing sets `VERCEL_ENV` off Vercel. Without it the API considers itself
  non-production and quietly falls back to dev secrets instead of refusing to boot.
- The machine scales to zero (`auto_stop_machines = "stop"`, `min_machines_running =
  0`). DDL therefore belongs in the once-per-deploy `release_command`
  (`python -m api.release`: Alembic upgrade + Procrastinate schema), never on a boot
  path. There is deliberately no periodic health check — it would hold the machine,
  and its Neon connection, awake.

### Cross-cutting request behavior (legacy surface)

Applied inside the `POST /api/certificate` and `/api/invoice` handlers, not as
middleware: in-memory rate limiting (`_check_rate_limit`, `RATE_LIMIT_MAX_REQUESTS`
per `RATE_LIMIT_WINDOW_SECONDS`, default 10/60s per client IP), in-memory idempotency
cache (`_check_idempotency`, 1h TTL), `X-API-Key` auth bypassed for same-origin
browser requests (`_is_browser_same_origin`), fire-and-forget webhooks
(`_fire_webhook`), and optional AgentMail delivery. **Both in-memory caches are
per-instance** and do not survive a machine stop — treat them as best-effort.

Legacy admin endpoints require `X-Admin-Key` via `_require_admin` plus `_require_db`.
`/api/v1` authenticates Clerk RS256 session tokens in `api/core/auth.py`, which
**fails closed**: if PyJWT is missing or the JWKS URL cannot be resolved it answers
503 rather than reading unverified claims.

### The `/api/v1` surface

Routers in `apps/api/api/routes/`, all mounted under `/api/v1` in `index.py`:
`orgs`, `studio`, `templates`, `verify`, `passports`, `claims`, `billing`, `webhooks`,
`developers`, `credentials`. Every one returns the `ApiResponse` envelope from
`api/core/envelope.py` (`{success, data, error, meta}`) — unlike the legacy surface.

`routes/credentials.py` is the single-credential resource: `POST`/`GET
/orgs/{slug}/credentials`, `GET`/`POST .../{public_id}` (`/revoke`). Issuance goes
through the one shared function, `api/services/issuance.py`'s `issue_credential()` —
the bulk CSV path (`studio.py`) calls it too, so they cannot drift apart. It resolves
which `Template` a credential renders with (`resolve_template_id`), and every issuance
response carries `verify_url`, `badge_url`, and `pdf_url`.

`routes/verify.py` also exports a `public_router` mounted at the site root, for the
URLs that go inside QR codes: `GET /verify/{credential_id}` (HTML),
`GET /credentials/{public_id}/badge.json` (Open Badges 3.0), and
`GET /credentials/{public_id}/pdf` (renders the certificate on demand — nothing is
stored, unlike `badge.json` which was always computed fresh). Both are readable by ID
with no auth, same posture as the legacy download route: the ID is the capability.
`api/services/rendering.py`'s `build_render_variables()` is the one place PDF template
variables are built, shared by this route and the bulk worker
(`api/core/worker.py`) so single and bulk issuance can't render differently. An org's
`primary_color`, `accent_color`, `footer_text`, and `logo_url` flow into it — the
seeded default templates use the first three; `logo_url` is passed through but none of
them has a layout slot for it yet.

### Delivery state, and why it exists

`api/services/delivery.py` is the only credential-email sender; both the bulk
worker and single issuance call it. Every path through it writes a terminal
state onto the credential — `delivery_status` is one of `not_requested`,
`pending`, `sent`, `failed`, `unknown` — plus `delivered_at`, `delivery_error`
and `delivery_attempts`.

`not_requested` is the state that earns its keep. Delivery used to leave no
trace: a rejected send wrote one `logger.warning`, and a credential with no
`recipient_email` took a silent `if` and wrote nothing at all. Minutes later the
two were identical rows and the log had rolled off, which is how the first
production batch became unexplainable. **Not sending is a recorded outcome here,
not an absence.**

Two rules that are easy to break by accident:

- `unknown` is the backfill for rows predating these columns. It is excluded
  from `DELIVERY_RETRYABLE`, because retrying them would mail people who may
  have been served months ago. Never guess a value for one.
- `CredentialBatch.succeeded` / `failed` count **renders**, not sends.
  `delivered` / `delivery_failed` are separate for exactly that reason — a batch
  that rendered thirty PDFs and emailed none of them used to report "30
  succeeded" and nothing else.

Quota works the same way: `api/services/issuance.py`'s `consume_quota()` is the
one meter, called by both paths. Bulk used to read the ledger without writing it
back, so bulk issuance went unmetered while single issuance metered correctly.

Bulk issuance runs on Procrastinate (`api/core/worker.py`), embedded in the FastAPI
lifespan so it scales with the web process.

## Agent-discovery surface

`/llms.txt`, `/robots.txt`, `/sitemap.xml`, `/.well-known/ai-plugin.json`, and the
JSON-LD injected into viewer pages are generated in `apps/api/api/index.py`
(`_build_llms_txt`, `_build_sitemap_xml`, `_participation_json_ld`,
`_internship_json_ld`). Adding a public endpoint means updating `_build_llms_txt` and
`_build_sitemap_xml` too — and `vercel.json`.

## Where the work is going

- `docs/api-first-optimization-plan.md` — the current direction: what is being
  changed and why.
- `docs/subagent-handover.md` — how that plan is partitioned into work packages by
  file ownership, and in what order they land.
- `docs/certificate-internship-vtu.md` — internship field ↔ token-key mapping and the
  college workflow.
- `docs/TODOs/` — live defects, one file each, in a consistent shape: the finding
  with reproducible evidence, why it matters, what it does *not* affect, the fix
  options with their tradeoffs, and a section on why the existing tests missed it.
  Closed ones keep their `Status` line and stay in place, because the reasoning is
  the point. Read `certforge-public-urls-404.md` first if you are new here — it is
  the clearest example of the failure mode this codebase keeps producing.

### The failure mode worth knowing before you start

Four production incidents have shared one structure: **two halves that were each
correct in isolation, with nothing testing the join.** The API served `/verify/{id}`
and `apps/web` was deployed at that host, but no rewrite connected them. Rewrites
forwarded to Fly and Clerk protected only `/org`, but middleware runs first. A send
branch ran and the credential issued, but a skipped send and a failed send both
wrote nothing. A path was served and a URL was well-formed, but the hostname had no
DNS record.

Every one passed review, and most passed a test suite that exercised one side.

So when you add anything spanning a boundary — a host, a deploy, a config file, a
provider — ask what happens if **one side alone** is correct, and write the
assertion that fails in that state. Then check that it does fail, by breaking the
thing on purpose. An assertion that cannot distinguish the outcome it exists to
detect is worse than none, because it reports success.
