# CertForge — Sub-Agent Handover Pack

Companion to [api-first-optimization-plan.md](./api-first-optimization-plan.md). That document says *what* and *why*; this one says *who does which files, in what order*.

Baseline: commit `1fa17e9`, tree clean, `pytest` 42/42 green.

---

## The organising principle

Work packages here are partitioned by **file ownership**, not by phase. Two agents editing `index.py` at the same time produce a merge conflict no matter how unrelated their tasks are, so every package below declares an `OWNS` list, and **no two packages in the same wave share a file**. Phases from the plan are spread across waves wherever that keeps ownership clean.

Run every wave's agents with `isolation: "worktree"` so they cannot see each other's half-finished edits. Waves are barriers: all of a wave lands and merges before the next starts.

```
W0 ─┬─ A1  verify.py                     ┐
    ├─ A2  auth.py + passports.py        │ WAVE 1
    ├─ A3  index.py + worker.py          │ (4 parallel)
    └─ A4  apps/web                      ┘
       A5  docs                (no deps, any time)

           ↓ merge

       B1  the spine — api_key_auth + services/issuance + credentials
           SERIAL, single agent, touches every route file

           ↓ merge

    ┌─ C1  webhooks_clerk.py             ┐
    ├─ C2  billing.py                    │ WAVE 3
    ├─ C3  studio.py + worker.py         │ (4 parallel)
    └─ C4  templates.py + seed.py        ┘

           ↓ merge

    ┌─ D1  infra (human-in-the-loop)     ┐ WAVE 4
    └─ D2-D4  Studio frontend surfaces   ┘

       E1  performance · E2  DX/SDK        WAVE 5
```

---

## Shared preamble

**Prepend this verbatim to every sub-agent prompt.** It is the difference between an agent that fixes one thing and an agent that quietly breaks a live product.

````text
## Repository

Monorepo at c:\Users\gengi\Documents\markdown-to-pdf, branch `main`, baseline commit 1fa17e9.

  apps/api/          FastAPI backend. Deployed to Fly.io as `certforge-api`.
                     api/index.py       legacy surface (2810 lines) — frozen, see below
                     api/core/          config, auth, crypto, envelope, worker, pdf, email
                     api/routes/        the /api/v1 CertForge surface
                     api/models/        SQLAlchemy + Alembic
                     tests/             pytest — MUST stay green
  apps/web/          Next.js 16 + Clerk. Future CertForge dashboard. Currently mock data.
  apps/legacy-web/   Vite SPA. LIVE at certs.intelliforge.tech. Do not touch.
  sdk/pdfcert/       Installable Python client for the legacy API.

## Commands

  cd apps/api && python -m pytest          # 42 tests, all must pass before you finish
  ruff check apps/api/api/ sdk/pdfcert/    # must be clean
  npm run build --workspace=web            # only if you touched apps/web

## THE FREEZE CONTRACT — read before editing anything

certs.intelliforge.tech is a live product with certificates already issued and QR codes
already printed on paper. These are immutable:

  - The token format: base64url(compact_json) + "." + hmac_sha256_hex
  - The single-letter payload keys: n c d i k u w h m s r e v p
    Never rename, reorder, or repurpose one. New fields are new OPTIONAL keys only.
  - CERT_SECRET_KEY — changing it invalidates every certificate ever issued.
  - SITE_URL (= https://certs.intelliforge.tech) — every printed QR resolves through it.
    CertForge uses the separate CERTFORGE_WEB_URL. Never repoint SITE_URL.
  - _cert_id()'s hashing rule — it is the ID printed on the PDF.
  - The request/response shape AND status codes of: POST /api/certificate,
    POST /api/invoice, GET /certificate/{token} (+ /download, /verify),
    GET /invoice/{token}/download, POST /api/certificates/verify, /api/courses,
    /api/info, /api/health, /api/admin/* — including their bare {"error": {...}}
    error envelope. sdk/pdfcert and the live SPA depend on these verbatim.

Everything under /api/v1, all of apps/web, and api/core/* is free to change.

## Rules

1. Edit ONLY the files in your OWNS list. If the task seems to require a file you do
   not own, STOP and report it — another agent owns that file right now.
2. Ship a regression test named after the bug you fixed. The repo convention is
   descriptive names that state the original defect, e.g.
   test_callers_behind_the_proxy_get_separate_buckets. Follow it.
3. Comments explain WHY, not what. Match the density and voice of the surrounding
   code — see api/core/worker.py and apps/api/fly.toml for the house style.
4. Commit in your worktree; do not push, do not merge, do not rebase onto main.
   Commit message: imperative sentence-case summary, body explaining the why.
   End with: Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
5. Report back: what changed, which tests you added, anything you found but did not
   fix because it was outside your OWNS list.
````

---

## W0 — Config contract seed

**Serial. Blocks A1 and A3. ~20 minutes.** Small enough to do by hand rather than dispatch.

**OWNS:** `apps/api/api/core/config.py`

Two later packages need the CertForge host names, and neither should own the config file. Seed the contract first so both can import it without touching it.

```python
CERTFORGE_WEB_URL = _env("CERTFORGE_WEB_URL", "https://certforge.intelliforge.tech")
CERTFORGE_API_URL = _env("CERTFORGE_API_URL", "https://api.certforge.intelliforge.tech")
```

`SITE_URL` stays exactly as it is. Add a short comment saying why the two coexist: `SITE_URL` addresses the frozen legacy host that printed QR codes resolve through; `CERTFORGE_WEB_URL` addresses the new product.

**Accept:** 42 tests green, ruff clean, no other file touched.

---

## WAVE 1 — four agents in parallel

### A1 · Credential viewer hardening

**OWNS:** `apps/api/api/routes/verify.py`, `apps/api/tests/test_verify_viewer.py` (new)
**DEPENDS:** W0

1. **H6 — stored XSS.** `verify_page` builds its HTML with an f-string that interpolates `data['name']`, `data['title']`, `data['issued_at']` and `data['id']` with no escaping (`verify.py:133-166`). Recipient names arrive from customer-uploaded CSVs, so this is attacker-controlled. Escape every interpolation with `html.escape`, or convert the viewer to a Jinja2 template with autoescaping on — the latter is better if you are going to extend this page later.
2. **Dead link.** The Download PDF button points at `/api/v1/verify/{id}/download`, which does not exist and 404s. Point it at a real route or remove the button; do not invent a new endpoint (that is B1's job).
3. **Badge URLs.** `get_open_badge_json` hardcodes `https://certs.intelliforge.tech` for the issuer id and achievement id (`verify.py:79`, `:87`). Those are CertForge credentials, not legacy ones — build them from `CERTFORGE_WEB_URL`. Note `verify.py:24` already resolves through `SITE_URL`; work out which of the two each URL actually belongs to and say so in a comment.

**Accept:** a credential titled `<script>alert(1)</script>` renders escaped; `badge.json` returns 200 with CertForge-host URLs; 42 + your new tests green.
**Do not touch:** the legacy `/certificate/{token}` viewer in `index.py` — different surface, frozen.

### A2 · Identity claims and credential claiming

**OWNS:** `apps/api/api/core/auth.py`, `apps/api/api/routes/passports.py`, `apps/api/tests/test_passports.py` (new)
**DEPENDS:** none

1. **H8 — `AuthenticatedUser` has no `email`.** `passports.py:33` reads `user.email` to derive a passport username; the dataclass (`auth.py:29-33`) defines only `clerk_user_id`, `clerk_org_id`, `clerk_org_role`. The first person to claim a credential gets an `AttributeError`. Add the field, populated from the Clerk claim. **Be careful:** Clerk session tokens do not carry an email claim by default. Verify what your token actually contains rather than assuming; if it is absent, either add it to the Clerk JWT template or derive the username from `clerk_user_id` — but do not let a missing email crash the claim.
2. `POST /api/v1/claims/{id}` and `GET /api/v1/passports/{username}` must work end to end.
3. Both return `ApiResponse.fail(code=404)` with **HTTP 200**, which tells the caller the request succeeded. Raise `HTTPException` instead.

**Accept:** claiming creates a passport, links the credential, and is idempotent on repeat; a second user claiming the same credential gets 403 not 200.

### A3 · Origins, error envelope, URL resolution

**OWNS:** `apps/api/api/index.py`, `apps/api/api/core/worker.py`, `apps/api/tests/test_envelope_split.py` (new)
**DEPENDS:** W0

The highest-risk package in Wave 1 — it edits the file that serves the live product. The freeze contract is what you are protecting.

1. **M5 — CORS.** `index.py:316` is `allow_origins=["*"]` on an API about to carry bearer tokens cross-origin. Replace with an explicit allow-list: `CERTFORGE_WEB_URL`, `SITE_URL`, localhost dev ports, plus an `allow_origin_regex` for Vercel preview deployments.
2. **Error envelope split.** The global handler (`index.py:~348`) emits `{"error": {...}}` for every route, silently overriding the `ApiResponse` envelope that v1 routes declare in their `response_model`. Branch on `request.url.path.startswith("/api/v1")`: v1 gets `{"success": false, "data": null, "error": {...}}`, everything else keeps the bare legacy shape **byte for byte**.
3. **M4 — hardcoded domain.** `worker.py:143` builds `https://certs.intelliforge.tech/verify/{public_id}` and bakes it into every new credential's QR code. Use `CERTFORGE_WEB_URL`.
4. **RATE_LIMIT.** `index.py:160` hardcodes `RATE_LIMIT = 10` while `config.py:135` still parses `RATE_LIMIT_MAX_REQUESTS`, so the env var is dead. Import from config so there is one source of truth.

**Accept:** a test pinning the legacy 404 body exactly as it is today, a test asserting the v1 404 body carries `success: false`, a preflight test showing `CERTFORGE_WEB_URL` allowed and an unknown origin refused.
**Do not touch:** any handler body in `index.py`. Your edits are the middleware, the exception handler, the two constants — nothing else.

### A4 · Frontend de-mocking

**OWNS:** `apps/web/**`
**DEPENDS:** none

`apps/web` is a `create-next-app` template with three fictions bolted on. Strip it back to something honest.

1. Replace the template home page (`app/page.tsx` — still the Next.js logo and "edit page.tsx").
2. Delete `MOCK_DATA` in `app/passport/[username]/page.tsx` and the `setTimeout` fake-success paths in `app/claim/[credential_id]/page.tsx` and `app/org/[slug]/dashboard/page.tsx`.
3. **M6 — Next.js 16 `params` is a Promise.** Every dynamic route reads `params.credential_id` / `params.username` / `params.slug` synchronously and is broken as written. Await it. Read `node_modules/next/dist/docs/` before assuming any other Next 16 API — this version has breaking changes relative to training data.
4. Build `lib/api.ts`: a typed client with base URL from `NEXT_PUBLIC_CERTFORGE_API_URL`, attaching the Clerk token via `getToken()`.

**Important:** most issuance endpoints do not exist until B1 lands. Where a page has no endpoint yet, render a real empty or unavailable state. **Do not fake success.** The whole point of this package is that a dashboard which lies is worse than one that says "not yet".

**Accept:** `npm run build --workspace=web` passes; no `MOCK_DATA` and no `setTimeout`-to-simulate-work anywhere in `apps/web`.

### A5 · Docs truth pass

**OWNS:** `CLAUDE.md`, `README.md`, `apps/web/CLAUDE.md`
**DEPENDS:** none — dispatch any time

**M7.** `CLAUDE.md` still documents the pre-monorepo layout: a root `api/index.py`, a Vercel Python function, `npm run dev` at the root. Every path in it is wrong, and it is the file every future agent reads first. Rewrite for the real structure, the Fly deploy, `cd apps/api && python -m pytest`, the current route layout, and the freeze contract. Verify each claim against the code rather than editing prose in place.

---

## WAVE 2 — B1 · The spine

**Serial. One agent. Two commits. Blocks Wave 3.** This is the package that makes the product API-first; everything else is around it.

**OWNS:** new `apps/api/api/core/api_key_auth.py`, new `apps/api/api/services/issuance.py`, new `apps/api/api/routes/credentials.py`, all of `apps/api/api/routes/*.py` (dependency swap only), `apps/api/api/index.py`, tests
**DEPENDS:** Wave 1 merged

### Commit 1 — API keys that actually authenticate

Today `POST /api/v1/orgs/{slug}/api-keys` mints `cf_live_…` keys and stores SHA-256 hashes, and **nothing anywhere reads them back**. Every v1 write route requires a Clerk browser session JWT, so a customer can create an API key and then has no endpoint that accepts it.

- `resolve_principal(request) -> Principal(org_id, kind, scopes)` accepting **either** `Authorization: Bearer cf_live_…` (SHA-256 lookup against `api_keys`, `hmac.compare_digest`, `revoked_at IS NULL`, `last_used_at` bumped out of band) **or** a verified Clerk JWT.
- Swap `Depends(get_current_user)` → `Depends(resolve_principal)` across every v1 route.
- `require_org_role` takes the principal. An API key is scoped to exactly one org, so cross-org access collapses to an equality check. **Do not reintroduce a claims-based fast path** — commit `3b52e72` deliberately removed one because forged claims could assert membership. The database decides.
- Mint `cf_test_…` alongside `cf_live_…`. Test keys persist but never send email and never bill.

### Commit 2 — Service layer and the credentials resource

- `api/services/issuance.py` holds the single "issue a credential" function: validate, generate ID, sign, persist, enqueue PDF and email, fire webhooks. Plain dataclass in, plain dataclass out — no FastAPI, no Clerk, no CSV.
- `POST /api/certificate` (legacy) and `POST /api/v1/credentials` (new) both become **thin adapters over that one function**. This is the mechanism that lets the frozen surface stay frozen while the product moves: one implementation, two vocabularies.
- New routes: `POST /api/v1/credentials`, `POST /api/v1/credentials/batch` (JSON array — CSV becomes a client convenience, not the only door), `GET /api/v1/credentials` with cursor pagination, `GET /{id}`, `POST /{id}/revoke`, `GET /{id}/pdf`.
- Write `UsageLedger` on issuance (**H5** — it is read at `studio.py:72` and written nowhere, so quota never binds). Return `X-Quota-Limit` and `X-Quota-Remaining`.

**Accept:** `curl -H "Authorization: Bearer cf_test_…" -d '{...}' /api/v1/credentials` issues a credential end to end. `POST /api/certificate` returns **byte-identical** output to `1fa17e9` — prove it with a golden-file test, not by inspection.

---

## WAVE 3 — four agents in parallel

### C1 · Clerk webhooks
**OWNS:** new `apps/api/api/routes/webhooks_clerk.py`, one registration line in `apps/api/api/index.py`, tests

**H7.** `CLERK_WEBHOOK_SECRET` is configured and `orgs.py` documents itself as "usually called by Clerk webhooks" — but **no such route exists**. Organisations created in Clerk never reach the database, so Studio has no working onboarding path at all. Build it: Svix signature verification, handling `organization.created/updated`, `organizationMembership.created/deleted`, `user.created`. Fail closed when the secret is unset, matching what `billing.py` now does for Razorpay.

### C2 · Real Razorpay
**OWNS:** `apps/api/api/routes/billing.py`, tests

Checkout is mocked — it returns a fabricated `https://rzp.io/i/mock_{org.id}_{tier}` URL. Replace with real order/subscription creation and real tier and quota transitions on the verified webhook. **H9 depends on this:** `templates.py:71` rejects `tier == "community"`, and this mocked checkout is the only route out of community tier, so custom templates are currently unreachable by any customer. The signature verification here already fails closed (commit `3b52e72`) — keep that.

### C3 · Batch pipeline and quota
**OWNS:** `apps/api/api/routes/studio.py`, `apps/api/api/core/worker.py`, tests

- **H4.** `studio.py:116` fires `asyncio.create_task(process_batch.defer_async(...))` without holding the reference — the task can be garbage-collected before it runs, and exceptions vanish. It also reads `batch.id/.total/.status` after the `with get_db()` block closed the session. Await the defer **inside the transaction that creates the batch**, so a batch row cannot exist without a queued job.
- Enforce the quota that B1 made real, and emit batch progress the UI can poll.
- Webhook delivery (`worker.py:~220`) posts once with a 5s timeout and logs failures, so a customer whose endpoint blips loses the event silently. Add retries with backoff.

### C4 · Templates
**OWNS:** `apps/api/api/routes/templates.py`, `apps/api/api/seed.py`, tests

Complete the CRUD, seed the global default templates (`seed.py` exists for this), and make the tier gate satisfiable now that C2 provides a real upgrade path.

---

## WAVE 4 — infrastructure and Studio UI

### D1 · Infrastructure — **human-in-the-loop, not a sub-agent**

DNS records, Vercel dashboard settings and Fly certificates are account actions with real-world effect. Do them yourself:

```
certforge.intelliforge.tech       CNAME  cname.vercel-dns.com
api.certforge.intelliforge.tech   CNAME  certforge-api.fly.dev
fly certs add api.certforge.intelliforge.tech
```

Rename Vercel project `web` → `certforge`, git-link it to `gengirish/markdown-to-pdf`, Root Directory `apps/web`, `npx turbo-ignore` as the Ignored Build Step. Add `certforge.intelliforge.tech` to Clerk's allowed origins.

**Also decide the worker topology here.** One 512 MB shared vCPU currently runs the HTTP server *and* the Procrastinate worker, with `auto_stop_machines = "stop"`. Under Studio volume a batch deferred near idle-stop dies, and nothing wakes a stopped machine to drain the queue. Recommended: split `fly.toml` into `[processes]` — `app` (scale-to-zero as today) and `worker` (`min_machines_running = 1`), accepting that Neon stops autosuspending. The trade-off is spelled out in the plan doc; pick before D2–D4 build UI on top of it.

### D2–D4 · Studio frontend

Split by surface so ownership stays disjoint. Each owns its own route directory plus shared components it creates:

- **D2** — org onboarding, credential list, single issue
- **D3** — templates gallery and editor, CSV bulk upload with live batch progress
- **D4** — developer console (API keys, webhooks, usage vs quota), billing and plan

Public server-rendered pages (`/verify/{id}` with JSON-LD and OG tags, `/passport/{username}`, `/claim/{id}`, `/orgs/{slug}`) fold into D2.

---

## WAVE 5

### E1 · Performance
**OWNS:** `apps/api/api/index.py`, `apps/api/fly.toml`

- **The single highest-leverage change in the whole plan:** a given token always renders the same bytes, so `Cache-Control: public, max-age=31536000, immutable` on `/certificate/{token}` and its `/download` moves nearly all read traffic to Vercel's edge — p95 to near zero, and the Fly machine stays asleep, cutting both Fly and Neon spend. Revocation is the wrinkle: purge on revoke, or cap the TTL near five minutes to bound staleness.
- **H3.** `download_certificate` (`index.py:2285`) is `async def` and calls `_build_cert_pdf` — xhtml2pdf, synchronous, CPU-heavy — inline. `generate_certificate` calls `_run_with_timeout(_send_email, 20.0)` inline too. On one shared vCPU with `soft_limit = 20`, one slow AgentMail call stalls the machine for twenty seconds. Convert to `def` so FastAPI threadpools them; move email into the queue.

### E2 · Developer experience
**OWNS:** `sdk/**`, `docs/**`, `_build_llms_txt` / `_build_sitemap_xml`

Generate the SDK from the now-accurate OpenAPI schema; keep `sdk/pdfcert`'s legacy methods as a deprecated shim so existing installs keep working. Publish a quickstart that is `curl` plus an API key and nothing else — if a developer cannot issue their first credential without opening a browser, the product is not API-first regardless of what the endpoints look like.

---

## Still unassigned

**C3 — the same-origin bypass.** `_is_browser_same_origin` (`index.py:245`) compares client-supplied `Origin`/`Referer` against the site URL, so any non-browser client can spoof it and skip the `CERT_API_KEYS` check on `POST /api/certificate` and `/api/invoice`.

Deliberately unassigned, because it is the one open defect with no clean fix that respects the freeze contract: the live SPA depends on being able to call those endpoints without an API key, and the honest fix (a CSRF cookie, or a short-lived token minted by the SPA's origin) changes how the live frontend authenticates. B1 makes it moot for CertForge — the new API gets its own host and real key auth. Decide separately whether the legacy surface is worth the migration, or whether the exposure is acceptable given what those endpoints do.
