# B1 · Single-credential issuance — implementation plan

Companion to [subagent-handover.md](./subagent-handover.md) §WAVE 2 and
[api-first-optimization-plan.md](./api-first-optimization-plan.md) §Phase 2. Those say
*what* B1 is for; this says exactly what to build, in what order, and which decisions
have to be settled before the first line of code.

**Baseline verified against `main` @ `1eef4f7`, tree clean, `cd apps/api && python -m
pytest` → 91 passed.** Every claim below was checked in the code today, not carried
over from the earlier plan.

---

## 1. The one-sentence goal

> `curl -X POST https://api.certforge.intelliforge.tech/api/v1/credentials -H
> "Authorization: Bearer cf_test_…" -d '{"org":"acme","recipient_name":"Alice",
> "title":"Python 101"}'` returns a credential with a verify URL that resolves, a PDF
> that downloads, and a usage counter that moved.

Nothing in the product does that today. The only issuance path is
`POST /api/v1/orgs/{slug}/credentials/bulk` — a `multipart/form-data` CSV upload
requiring a Clerk **browser session** JWT (`studio.py:22-118`).

---

## 2. Ground truth — what is actually there

| Piece | State today | Where |
|---|---|---|
| API keys | Minted and hashed; **nothing reads them back**. Prefix is `cf_prod_`, not the `cf_live_` the plan documents. | `developers.py:36` |
| Auth on every v1 write | `Depends(get_current_user)` — Clerk session JWT only | all of `routes/*.py` |
| `Credential` row | Has `public_id`, `hmac_signature`, `pdf_url`, `status`, `claimed_by_user_id` | `models/credential.py:52` |
| `hmac_signature` | `hmac_sign(public_id)` — signs the ID and nothing else | `studio.py:97` |
| `pdf_url` | Never written. The worker deliberately leaves it `None`. | `worker.py:150-154` |
| `UsageLedger` | Read at `studio.py:72`, **written nowhere** (H5) | `models/usage.py` |
| Quota check | `used + n > org.monthly_quota` — wrong for the `scale` tier, whose quota is `-1` (unlimited) and therefore always "exceeded" | `studio.py:74`, `config.py:173` |
| Status values in use | `pending` → `issued` \| `failed` (bulk); `revoked` is set by nothing | `studio.py:107`, `worker.py:184` |
| Viewer gate | `status != "issued"` → 404 | `verify.py:30` |
| `badge.json` gate | `status == "revoked"` → 404, so a **`pending` credential exports a public badge while being invisible in the viewer** | `verify.py:74` |
| Claiming | Sets `claimed_by_user_id` / `claimed_at`, deliberately does **not** touch `status` | `passports.py:101-106` |
| Template rendering | `render_credential_pdf` substitutes `{{key}}`; the worker supplies `name`, `title`, `credential_id`, `qr` — but the seeded templates also declare `date` and `issuer_name`, which therefore render as the literal text `{{date}}` | `worker.py:138-148`, `seed.py:33` |
| Routing | `/api/:path*` already rewrites to Fly, so new `/api/v1/*` routes need **no** `vercel.json` change | `vercel.json` |
| Test auth | `mock_clerk` overrides the `get_current_user` **dependency object** | `tests/conftest.py:104` |

---

## 3. Decisions to settle before writing code

Six. Each is a fork the code cannot straddle; each has a recommendation.

### D1 — Does `POST /api/certificate` really become an adapter over the same function?

The handover says both surfaces become "thin adapters over one issuance function". Held
against the code, the two paths share almost nothing:

| | Legacy `/api/certificate` | CertForge `/api/v1/credentials` |
|---|---|---|
| Identity | none (optional `X-API-Key`) | org, resolved from a key or JWT |
| The credential *is* | a signed URL token | a database row |
| ID rule | `_cert_id()` — **frozen**, printed on paper | `CF-YYYY-XXXXXXXX` |
| Persistence | raw psycopg2, optional, best-effort | SQLAlchemy, required |
| PDF | `_build_cert_pdf` + three frozen HTML templates | `render_credential_pdf` + a DB `Template` |
| Email | three bespoke branded senders | one generic AgentMail body |
| Webhook | fire-and-forget POST to a per-request `callback_url` | registered `WebhookEndpoint` rows, HMAC-signed |

A single function covering both is a function with a mode flag, which is two functions
wearing one name — and the mode flag would sit on the frozen surface.

**Recommendation: share the *steps*, not the entry point.** `api/services/issuance.py`
owns the pieces that are genuinely one thing — quota reservation, ID allocation,
canonical signing, PDF dispatch, webhook fan-out, delivery — and exposes
`issue_credential(IssuanceRequest) -> IssuedCredential` for the CertForge path. The
legacy handler keeps its own body and adopts shared steps only where the shared step is
provably identical, one at a time, under the golden test from B1.0. If a step cannot be
adopted without a branch, it does not get adopted.

**If you want it as briefed instead:** land B1.0–B1.4 exactly as below, then do the
legacy port as a separate package with its own review. It must not ride in the same
commit as new endpoints — a byte-difference in `/api/certificate` and a bug in
`/api/v1/credentials` would be indistinguishable in the diff.

### D2 — What are the credential states?

Four surfaces currently disagree (§2). Settle it as:

```
status ∈ { pending, issued, revoked, failed }
```

- **`pending`** — staged by a batch, not yet valid. Invisible everywhere public.
- **`issued`** — valid. The only state the viewer, `badge.json` and the passport show.
- **`revoked`** — permanently invalid. 410, not 404, on the v1 JSON route.
- **`failed`** — batch rendering failed. Invisible; not a credential.

**Claiming is not a status.** It is `claimed_by_user_id` / `claimed_at`, exactly as
`passports.py` already does it. That is what lets A2's claim flow work without
invalidating a printed QR code, and it is the reason `status` can stay a simple gate
everywhere.

**Single issuance never writes `pending`.** The row is `issued` the moment it commits.
The PDF is not the credential — a null `pdf_url` means "not rendered yet", not "not
issued". This is the whole reason a synchronous single-credential endpoint is possible
at all.

Fix required by this decision: `verify.py:74` must gate on `status == "issued"`, not
`status != "revoked"`.

### D3 — What does `hmac_signature` sign?

Today: `hmac_sign(public_id)` — the signature proves the ID was minted here and says
nothing about the name, the title, or the org. Anyone who can write the row can change
the recipient and the signature still verifies.

**Recommendation: sign a canonical payload** — compact JSON of
`{v, id, org, name, title, issued_at}` with sorted keys, the way the legacy encoder
compacts. Store the scheme version in `metadata_["sig_v"]` so it can be rotated later
without guessing. CertForge credentials are not in circulation yet, so this is the last
cheap moment to fix it; after the first real customer it becomes a migration.

### D4 — Where does the PDF live?

Three options: render on demand every time, store bytes in Postgres, or object storage
(R2/S3, deferred by the plan).

**Recommendation: render on demand, cache later.** `GET /api/v1/credentials/{id}/pdf`
renders through `run_in_threadpool` — never inline, since H3 is exactly that mistake on
the legacy surface — and issuance sets

```
pdf_url = f"{CERTFORGE_API_URL}/api/v1/credentials/{public_id}/pdf"
```

That is an honest value: the URL resolves. It also switches on A1's download button,
which is written to appear the moment `pdf_url` is non-null and scheme-safe
(`verify.py:159-166`) — no change needed there.

Object storage then becomes a pure optimisation: fill `pdf_url` with the stored object
instead, and nothing else moves.

### D5 — Which template does a single credential use?

`Credential.template_id` is nullable, but `render_credential_pdf` needs an
`html_source`. Resolution order, first hit wins:

1. `template_id` passed in the request (must belong to the org, or be global);
2. the org's own `is_default` template;
3. the global `is_default` template (`org_id IS NULL`) seeded by `seed.py`;
4. nothing → **422**, not a 500 out of the renderer.

While you are here: pass `date` and `issuer_name` into `variables` so the seeded
templates stop rendering `{{date}}` as literal text.

### D6 — Idempotency and quota concurrency

The legacy in-memory idempotency cache (`index.py:236`) is per-instance and dies when
Fly stops the machine. Do not reuse it for v1.

**Recommendation:** honour an `Idempotency-Key` header — already allow-listed in CORS
(`index.py:363`) — backed by a nullable `idempotency_key` column on `credentials` with a
unique index on `(org_id, idempotency_key)`. A replay returns the original credential
with `200` and an `Idempotency-Replayed: true` header.

For quota, an atomic `UPDATE usage_ledger SET credentials_issued = credentials_issued +
:n WHERE org_id = … AND period = …` with an insert-on-miss, inside the issuance
transaction. **Not** read-then-write — that is the race that makes a quota advisory.
Note the test suite is SQLite: `ON CONFLICT DO UPDATE` is spelled differently per
dialect, so put the upsert behind one helper and cover both.

---

## 4. Commit sequence

Five commits. Each leaves `pytest` green and the tree deployable.

### B1.0 — Golden contract test for the frozen surface *(no production code)*

Phase 0 item 4 of the optimization plan — "a contract test pinning the exact JSON shape
of every frozen endpoint" — **was never written**. `tests/` has no
`test_contract_legacy.py`. B1's acceptance criterion is "byte-identical output, proven
by a golden-file test", so the golden file has to exist before anything moves.

**New:** `apps/api/tests/test_contract_legacy.py`, `apps/api/tests/golden/*.json`

- Freeze the response body of `POST /api/certificate` for all three kinds
  (participation, internship, appreciation), `POST /api/invoice`,
  `GET /certificate/{token}/verify`, `POST /api/certificates/verify`, `/api/courses`,
  `/api/info`, `/api/health`, and the bare legacy error envelope on a 404 and a 400.
- Volatile fields (`request_id`, timestamps) get normalised, not dropped — assert they
  are present and well-formed, then blank them before comparing.
- Pin a handful of pre-existing tokens and assert they still decode to the same
  `certificate_id`. That is the freeze contract in executable form.

**Accept:** the new file passes on `main` unchanged. If it does not, you have found a
bug before B1 started; fix that first, separately.

### B1.1 — `resolve_principal`: API keys that authenticate

**New:** `apps/api/api/core/api_key_auth.py`, `apps/api/tests/test_api_key_auth.py`
**Touches:** every `routes/*.py` (dependency swap only), `routes/developers.py`,
`tests/conftest.py`, one Alembic migration

```python
@dataclass(frozen=True)
class Principal:
    org_id: uuid.UUID | None      # None for a JWT with no org context yet
    kind: str                     # "api_key" | "user"
    mode: str                     # "live" | "test"
    scopes: tuple[str, ...]
    clerk_user_id: str | None
    email: str | None
    api_key_id: uuid.UUID | None
```

- `Authorization: Bearer cf_…` → SHA-256 the whole key, look up `api_keys.key_hash`,
  `hmac.compare_digest` the hash, require `revoked_at IS NULL`. Anything else falls
  through to the existing Clerk verification, so `get_current_user` keeps working
  unchanged underneath.
- **Accept the existing `cf_prod_` prefix.** The stored hash covers the whole key, so
  lookup does not care about the prefix; only mode detection does. Mint `cf_live_` /
  `cf_test_` going forward, treat `cf_test_` as test mode and everything else as live.
- Migration adds to `api_keys`: `mode` (`live`/`test`), `prefix` (first 12 chars, so the
  dashboard can show `cf_live_a1b2…` without storing the secret), `scopes` (JSON,
  default `["credentials:write","credentials:read"]`).
- `last_used_at` is bumped **out of band** — a background task, or only when it is older
  than a minute. A write on every authenticated request turns every read endpoint into a
  write endpoint and wakes the Neon compute.
- `require_org_role(principal, org_id, roles)`: for `kind == "api_key"` this collapses to
  `principal.org_id == org_id`, because a key belongs to exactly one org. For
  `kind == "user"` it keeps hitting `org_members`. **Do not add a claims-based fast
  path** — `3b52e72` removed one deliberately.
- Test keys persist, verify and issue, but never send email and never bill. Thread `mode`
  into the service layer in B1.2 rather than checking it at each call site.

**The landmine:** `tests/conftest.py:104` overrides the `get_current_user` *dependency
object*. `resolve_principal` calls the Clerk path as a plain function, so the override
stops applying and every `mock_clerk` test 401s — that is roughly 40 of the 91. Update
the fixture to override `resolve_principal` and add a sibling `mock_api_key` fixture in
the same commit.

**Accept:** a `cf_test_` key issues against its own org and gets 403 against another; a
revoked key gets 401; all 91 existing tests still pass.

### B1.2 — The service layer and `POST /api/v1/credentials`

**New:** `apps/api/api/services/__init__.py`, `apps/api/api/services/issuance.py`,
`apps/api/api/routes/credentials.py`, `apps/api/tests/test_credentials_issue.py`
**Touches:** `api/index.py` (one `include_router`), one Alembic migration
(`credentials.idempotency_key` + unique index)

`services/issuance.py` — plain dataclasses in and out, no FastAPI, no Clerk, no CSV:

```python
issue_credential(session, IssuanceRequest) -> IssuedCredential
```

doing, in order, inside one transaction:

1. validate (name, title, template resolution per D5);
2. reserve quota atomically (D6), raising `QuotaExceeded` → 402;
3. mint `public_id`, retrying on the unique-constraint collision the docstring at
   `crypto.py:26` already warns about;
4. sign the canonical payload (D3);
5. persist the row as `issued` with `pdf_url` set (D4);
6. enqueue delivery — email and webhooks — **skipped entirely in test mode**.

`routes/credentials.py` is the adapter: parse, call, envelope, headers. Mounted
`app.include_router(credentials_router, prefix="/api/v1")` with `prefix="/credentials"`
declared inside the router — never an absolute path, or you get `/api/v1/api/v1/…`
again.

**Request**

```json
{
  "org": "acme",
  "recipient_name": "Alice Example",
  "recipient_email": "alice@example.com",
  "title": "Python 101",
  "issued_on": "2026-08-26",
  "template_id": null,
  "metadata": {"cohort": "spring-2026"},
  "send_email": true
}
```

`org` is required for a Clerk principal and optional for an API key, which already knows
its org; if both are given and disagree, 403.

**Response — `201`, `ApiResponse` envelope**

```json
{"success": true, "data": {
  "id": "CF-2026-K7M2P9QX",
  "status": "issued",
  "recipient_name": "Alice Example",
  "title": "Python 101",
  "issued_at": "2026-08-26T10:12:00+00:00",
  "verify_url": "https://certforge.intelliforge.tech/verify/CF-2026-K7M2P9QX",
  "pdf_url": "https://api.certforge.intelliforge.tech/api/v1/credentials/CF-2026-K7M2P9QX/pdf",
  "badge_url": "https://certforge.intelliforge.tech/credentials/CF-2026-K7M2P9QX/badge.json",
  "mode": "test"
}, "error": null, "meta": {"quota": {"limit": 500, "used": 12, "remaining": 488}}}
```

Headers: `X-Quota-Limit`, `X-Quota-Remaining` (`unlimited` when the tier quota is `-1`),
plus `Idempotency-Replayed: true` on a replay.

**Host discipline:** `verify_url` and `badge_url` come from `CERTFORGE_WEB_URL` — they
are pages a human opens. `pdf_url` comes from `CERTFORGE_API_URL`. `SITE_URL` appears
nowhere in this file.

**Accept:** issuing writes exactly one `UsageLedger` row and increments it on the second
call; the 51st credential on a community org returns 402; the same `Idempotency-Key`
twice returns the same `public_id`; a test-mode key sends no email.

### B1.3 — The rest of the resource

**Touches:** `routes/credentials.py`, `routes/verify.py` (the `badge.json` gate from
D2), tests

- `GET /api/v1/credentials?org=…&cursor=…&limit=…&status=…` — **cursor** pagination, not
  offset: `(issued_at, id)` encoded opaquely, `meta.next_cursor` null at the end. Offset
  pagination over an append-heavy table skips rows under concurrent issuance, which is
  exactly what a bulk batch is.
- `GET /api/v1/credentials/{id}` — full record. `404` when unknown, **`410`** when
  revoked, so a client can tell "never existed" from "withdrawn".
- `POST /api/v1/credentials/{id}/revoke` — sets `status` and `revoked_at`, requires
  `owner`/`admin`, idempotent on repeat. Does **not** refund quota; say so in the
  docstring, because someone will ask.
- `GET /api/v1/credentials/{id}/pdf` — `run_in_threadpool(render_credential_pdf, …)`,
  `Content-Disposition: attachment`, 404/410 matching the JSON route. Readable by ID
  without auth, like the legacy download route — the ID is the capability.
- Fix `verify.py:74` to gate on `status == "issued"` (D2), with a regression test that a
  `pending` credential exports no badge.

**Accept:** listing 120 credentials in pages of 50 returns each exactly once while a
batch is inserting; the viewer's download button appears for a credential issued through
B1.2, and its PDF opens.

### B1.4 — Batch, and an honest quota surface

**Touches:** `routes/credentials.py`, `routes/orgs.py`, `routes/studio.py`, tests

- `POST /api/v1/credentials/batch` — a **JSON array**, validated whole, then issued
  through the same service function, so CSV becomes a client convenience rather than the
  only door. Quota is reserved once for the whole array; a partial failure returns
  per-row results in `data.results`, never a silent partial success.
- `GET /api/v1/orgs/{slug}/usage` — period, used, limit, remaining. A4 shipped a
  dashboard that cannot show a quota because nothing exposes one.
- Add `monthly_quota` and `tier` to `GET /orgs/{slug}`.
- Point `studio.py`'s bulk upload at the same quota helper, which also fixes the `-1`
  unlimited bug at `studio.py:74`.

**Accept:** a 60-row batch against a 50-quota org is rejected whole with 402 and writes
nothing; `usage` reflects reality after B1.2 issues.

### B1.5 *(optional, separate review)* — the legacy adapter

Only under B1.0's golden test, one shared step at a time, per D1. Stop at the first step
that needs a mode flag.

---

## 5. Landmines, collected

1. **`conftest.py`'s `mock_clerk` breaks in B1.1.** ~40 tests turn red at once if the
   dependency swap lands without the fixture change.
2. **`ruff check apps/api/api/ sdk/pdfcert/` is the CI gate** — every new file is inside
   the checked tree.
3. **No `vercel.json` change is needed** (`/api/:path*` covers it), but `_build_llms_txt`
   in `index.py` should learn about `/api/v1/credentials`, since the agent-discovery
   surface exists to describe the machine-facing API.
4. **PDF generation fails locally on Windows** (`TTFError`, the font-locking quirk in
   CLAUDE.md). Do not chase it; assert the `/pdf` route's status and content type
   locally and let CI assert the bytes.
5. **`session.bulk_save_objects`** (`studio.py:111`) bypasses ORM defaults — do not copy
   that pattern into the batch path.
6. **Two quota sources of truth**: `org.monthly_quota` and `BILLING_TIERS[tier]`. The
   service reads `org.monthly_quota`; billing is what keeps it in sync. Put that in the
   service docstring.
7. **`-1` means unlimited**, and every comparison must special-case it.

---

## 6. Explicitly out of scope

Object storage for PDFs, per-key rate limiting, the Studio frontend, retiring the CSV
upload, and any change to `/api/certificate`'s wire format. B1.5 is the only place the
frozen surface is touched at all, and it is optional.
