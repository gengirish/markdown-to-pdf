# B1 · Single-credential issuance — implementation plan

Companion to [subagent-handover.md](./subagent-handover.md) §WAVE 2 and
[api-first-optimization-plan.md](./api-first-optimization-plan.md) §Phase 2. Those say
*what* B1 is for; this says exactly what to build, in what order, and which decisions
have to be settled before the first line of code.

**Baseline verified against `main` @ `1eef4f7`, tree clean, `cd apps/api && python -m
pytest` → 91 passed.** Every claim below was checked in the code today, not carried
over from the earlier plan.

## Status — 2026-09-01, `main` @ `99a144e`, 379 tests passing

| | Commit | State |
|---|---|---|
| B1.0 | Golden contract test | **landed** — `c05a848` wrote `tests/test_contract_legacy.py`; `5d8df79` added `test_contract_certforge.py` alongside it. B1.5 is no longer blocked |
| B1.1 | `resolve_principal` | **landed** — `d56557b` |
| B1.2 | Service layer + single issuance | **landed** — `a403b68` |
| B1.3 | The rest of the resource | **landed** — PDF route in `fad716b` (see D4/D5 below); list, get and revoke in `a403b68`; the status state machine in `629b454` |
| B1.4 | Batch + usage surface | **part landed** — the meter exists and both paths write it (`consume_quota()`, `4ec4043`, closing H5 for bulk too). `GET /orgs/{slug}/usage` is still not started, so the number is written and never read back out |
| B1.5 | Legacy adapter | not started, and optional by design |

The goal in §1 is now met end to end: an API key issues a credential in one call, the
verify URL resolves, and `pdf_url` in the response is a real document — see D4 and D5,
settled in `fad716b`. D6 (idempotency) landed since; D3 (canonical signing) landed 2026-08-30.

**Landed after B1, against this same surface** — each has its own note in `CLAUDE.md`
and, where it started as a defect, a file in `docs/TODOs/`:

- Canonical credential signing, and every public read path verifying before it renders
  (`bb8c658`).
- Delivery state as a recorded outcome, `not_requested` included (`docs/TODOs/email-delivery-observability.md`).
- Traced templates: an org's own artwork, stored in R2, composed in at render time
  (`016b881`), plus `MIN_HEIGHT_MM_PER_PT` for the box that silently swallowed its text
  (`ec62606`).
- Reading a design with a model — `POST /orgs/{slug}/templates/from-image`, metered by
  `UsageLedger.vision_imports`.
- The template preview now calls `build_render_variables()` instead of maintaining a
  second vocabulary (`99a144e`, `docs/TODOs/template-preview-lied-about-the-render.md`).
- Dashboard: the bulk-CSV card became a four-step issue wizard, and the whole app was
  re-skinned onto one token set with a light/dark toggle (`d6f1c18`, `7d33a43`, `c6f96a4`).

### 2026-08-28 — D4/D5 settled, plus org branding (`fad716b`)

Two parallel sub-agents landed the rest of B1.3 in one commit:

- **D4 (PDF location) and D5 (template resolution) both settled**, exactly per the
  render-on-demand recommendation below, with two deliberate departures — see each
  section for detail: the route lives at the site root (`GET /credentials/{public_id}/pdf`,
  matching `badge.json`'s convention) rather than under `/api/v1`, and it is a plain
  sync FastAPI handler, not `run_in_threadpool`.
- `CredentialCreate.template_id` is now accepted on `POST /orgs/{slug}/credentials`, and
  `_public_urls()` returns a real `pdf_url` alongside `verify_url`/`badge_url`.
- `services/rendering.py` (new) is the one place that builds PDF template variables;
  `worker.py`'s bulk path and the new PDF endpoint both call it, closing the `{{date}}`/
  `{{issuer_name}}` literal-text bug D5 flagged.
- **Beyond B1's original scope**: `organizations` gained `primary_color`, `accent_color`,
  `footer_text` (migration `e5a2c9d14f3b`), wired into the three seeded templates so a
  rendered certificate can carry an org's own colors and footer line instead of always
  looking like stock CertForge. `logo_url` insertion into the seed templates was
  deliberately skipped — none of the three layouts has a slot for it without restructuring,
  and a broken `<img src="">` when an org has no logo is worse than omitting it.
- The dashboard (`apps/web`) got a `SingleIssueCard` next to the existing bulk-CSV card,
  so single issuance is no longer API-only.
- Verified: `cd apps/api && python -m pytest` → 201 passed; `ruff check` clean; CI green
  including `deploy-api`; live health check and `openapi.json` on `certforge-api.fly.dev`
  confirm the route is deployed.

Where the code and this plan disagree, the code is what shipped. The note under each
commit below says which way it went.

### Production smoke test — 2026-08-27

First end-to-end issuance against production. **The bulk CSV path works.**

Input: `examples/sample-participants.csv` (`name,email,title,date,issuer_name`; three
participation rows). Issued under org `certforge-1787635500301081932` ("CertForge HQ").

| Check | Result |
|---|---|
| Bulk upload → batch → worker render | credential `CF-2026-XEHQNMFZ`, `issued_at` `2026-08-27T02:38:18Z` |
| `GET https://certs.intelliforge.tech/verify/CF-2026-XEHQNMFZ` | **200 `text/html`**, viewer renders, status shown as *Issued* |
| `GET https://certs.intelliforge.tech/credentials/CF-2026-XEHQNMFZ/badge.json` | **200**, well-formed OB 3.0; `achievement.name` = `Certificate of Participation`, taken from the CSV `title` column |
| `GET https://certforge.intelliforge.tech/verify/CF-2026-XEHQNMFZ` | **404** — see below |
| Download button in the viewer | **absent.** `.download-btn` CSS is in the page, no anchor uses it, because `pdf_url` is null (D4) |
| `cd apps/api && python -m pytest` | 135 passed |

Two things this run establishes that the code review could not:

- **The CertForge public host does not serve `/verify/{id}`.** Only the legacy host does,
  because `certs.intelliforge.tech` is the Vercel project whose `vercel.json` rewrites
  `/verify/*` through to Fly. `apps/web` has `claim/[credential_id]`, `passport` and
  `org` routes but **no `verify` route**, and `apps/web/vercel.json` declares no
  rewrites at all. Meanwhile `worker.py:145` builds the QR code from
  `CERTFORGE_WEB_URL` — so **every CertForge PDF issued so far carries a QR code that
  resolves to a 404**, on paper, unfixably. The URL above resolves only because it was
  typed against the legacy host by hand. This outranks the rest of the B1 backlog.
- **D4 is confirmed unsettled in production, not just in the source.** The viewer ships
  the download styling and renders no button; the badge is exportable, the document is
  not. Anyone who receives one of these credentials gets a web page, not a certificate.

**Follow-up:** no email arrived. AgentMail is configured and healthy on the deployed
API, and the send branch demonstrably ran, but nothing on the system records whether a
send was attempted or why it failed — see
[TODOs/email-delivery-observability.md](./TODOs/email-delivery-observability.md).


**Next, in order (updated 2026-08-28):** D5/D4 (template resolution + the `/pdf` route)
landed in `fad716b` — see the entry below. D3's signing landed 2026-08-30; see that
section. Remaining, in order: point `studio.py` at the service's quota helper
(B1.4, and it closes a live `-1`-quota bug); then B1.0's golden contract test,
which B1.5 is blocked on.
Check whether the `/verify` 404 on `certforge.intelliforge.tech` noted in the smoke
test below was closed by `c92b8fb` ("Make every CertForge public URL resolve on the
host it names") — this doc was not re-verified against that commit.

---

## 1. The one-sentence goal

> `curl -X POST https://api.certforge.intelliforge.tech/api/v1/credentials -H
> "Authorization: Bearer cf_test_…" -d '{"org":"acme","recipient_name":"Alice",
> "title":"Python 101"}'` returns a credential with a verify URL that resolves, a PDF
> that downloads, and a usage counter that moved.

*(As shipped the path is `/api/v1/orgs/{slug}/credentials` — see B1.2. The `pdf_url` in
that goal is still null.)*

Nothing in the product did that when this was written. The only issuance path was
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

**Settled as recommended.** `services/issuance.py` serves the v1 path; its docstring
says it is meant to serve the bulk path and the legacy adapter later. `/api/certificate`
is untouched.

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

**Settled the other way, and better.** `models/credential.py` now defines the lifecycle
in one place — `PENDING`, `ISSUED`, `CLAIMED`, `REVOKED`, plus `PUBLICLY_VERIFIABLE =
{ISSUED, CLAIMED}` and `CLAIMABLE`. So `claimed` *is* a status after all, and
`passports.py` sets it; what made that impossible before was the whitelist in
`verify.py`, not the status field itself. Same outcome — a printed QR keeps resolving
after a claim — reached without splitting the state across a column and a timestamp.
The `badge.json` blacklist is fixed with it. **One loose end:** `worker.py:185` still
writes `"failed"`, which the lifecycle block does not define.

### D3 — What does `hmac_signature` sign?

Today: `hmac_sign(public_id)` — the signature proves the ID was minted here and says
nothing about the name, the title, or the org. Anyone who can write the row can change
the recipient and the signature still verifies.

**Recommendation: sign a canonical payload** — compact JSON of
`{v, id, org, name, title, issued_at}` with sorted keys, the way the legacy encoder
compacts. Store the scheme version in `metadata_["sig_v"]` so it can be rotated later
without guessing. CertForge credentials are not in circulation yet, so this is the last
cheap moment to fix it; after the first real customer it becomes a migration.

**Settled 2026-08-30, as recommended with two departures.**
`api/core/credential_signature.py` signs a canonical JSON payload of
`{public_id, org_id, recipient_name, recipient_email, title, issued_at, metadata}`,
sorted keys, prefixed with the scheme name and version.

- **The version lives in its own column, `credentials.signature_version`
  (migration `b8f3c15d0a72`), not in `metadata_["sig_v"]`.** `metadata_` is
  signed, and a verifier that has to read the version out of the payload it is
  about to verify has an ordering problem the first time the scheme changes.
  It is also customer-controlled: bulk issuance stores the whole CSV row there.
- **`status` and the delivery columns are deliberately unsigned**, along with
  `claimed_*`, `revoked_at`, `pdf_url`, `batch_id` and `template_id`. The
  signature answers "is this what was issued?"; `status` answers "is it still
  valid?", and the read paths already gate on that. A signature covering a
  field the product mutates in normal use invalidates itself the first time
  someone claims a credential.

Rows written before this carry `signature_version = NULL` and report as
`unverified` — never as valid, and never re-signed, because the only source
for a backfill is the row as it stands today. That is the same rule
`delivery_status = "unknown"` follows.

Verified on every public read path — the viewer, `badge.json`, the PDF and the
v1 JSON verify route all answer **409** with `error.type = "signature_mismatch"`
rather than rendering. `GET /orgs/{slug}/credentials/{id}` deliberately does the
opposite and reports the mismatch in a `signature` object, since the org is who
would investigate it. `tests/test_credential_signature.py`; every guard was
confirmed by reintroducing the defect and watching the right test fail.

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

**Not settled.** There is no `/pdf` route and `issue_credential` leaves `pdf_url` null,
so a credential issued through the API has no document. A1's download button stays
hidden, and the §1 goal is only half met. Confirmed in production on 2026-08-27: the
viewer for `CF-2026-XEHQNMFZ` carries the `.download-btn` CSS and no button.

**Settled as recommended, mostly — 2026-08-28, `fad716b`.** `GET
/credentials/{public_id}/pdf` renders on demand, nothing is stored, and
`_public_urls()` fills `pdf_url` on issuance. `_get_credential_data()` in `verify.py`
now computes the viewer's link from `CERTFORGE_API_URL` instead of reading the
never-populated `Credential.pdf_url` column, so the download button lights up
unconditionally for every DB-backed credential. Two departures from the
recommendation:

- **Path is `/credentials/{public_id}/pdf` at the site root**, not
  `/api/v1/credentials/{id}/pdf` — mounted on `public_router` next to `badge.json`,
  same convention, same no-auth-required posture (the ID is the capability, as the
  legacy download route already works).
- **Not `run_in_threadpool`.** The handler renders inline on the request thread. Under
  load this repeats H3's mistake on the legacy surface, exactly what the recommendation
  warned against — worth fixing before this endpoint sees real traffic.

### D5 — Which template does a single credential use?

`Credential.template_id` is nullable, but `render_credential_pdf` needs an
`html_source`. Resolution order, first hit wins:

1. `template_id` passed in the request (must belong to the org, or be global);
2. the org's own `is_default` template;
3. the global `is_default` template (`org_id IS NULL`) seeded by `seed.py`;
4. nothing → **422**, not a 500 out of the renderer.

While you are here: pass `date` and `issuer_name` into `variables` so the seeded
templates stop rendering `{{date}}` as literal text.

**Not settled.** `IssueRequest.template_id` exists and is stored, but nothing resolves
it and the route never populates it — a credential issued through `POST
/orgs/{slug}/credentials` has `template_id = NULL`. Combined with D4, that is the whole
reason there is still no PDF: no template, nothing to render. This and D4 are the next
piece of work, and they are one piece, not two.

**Settled, resolution order as recommended — 2026-08-28, `fad716b`.**
`resolve_template_id()` in `services/issuance.py` implements exactly the 1→2→3 order
above (explicit `template_id`, scoped to the org or global; then the org's own default;
then the global default), called from `CredentialCreate` and reused by the `/pdf` route
for legacy rows with no `template_id`. `date` and `issuer_name` are now populated by
`services/rendering.py`, so the seeded templates no longer render `{{date}}` literally.
One departure: **step 4 is a 404 at PDF-render time, not a 422 at issue time.** A
credential can still be issued with `template_id = NULL` if an org has no template at
all (a fresh dev DB, mainly) — it just 404s the first time someone requests its PDF,
rather than being rejected up front. Worth revisiting if that gap ever matters in
practice; the DB seed ships two global defaults, so it should not be reachable in
production today.

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

**Half settled.** Quota is now enforced, in the service, with `-1` handled and
`UsageLedger` written for the first time (H5 closed). But `_consume_quota` is
read-then-write — `ledger.credentials_issued = used + count` — so two concurrent issues
in the same period can both read the same `used` and the second overwrites the first.
The quota binds against a sequential caller and leaks under a parallel one. Idempotency
was not implemented at all: there is no `Idempotency-Key` handling and no column for it,
so a retried POST issues a second credential.

---

## 4. Commit sequence

Five commits. Each leaves `pytest` green and the tree deployable.

### B1.0 — Golden contract test for the frozen surface · **LANDED** (`c05a848`) *(no production code)*

> `tests/test_contract_legacy.py` exists. Its load-bearing part is three tokens —
> participation, VTU internship, appreciation — produced by the real encoder against a
> fixed secret and committed as literals; they stand in for every certificate already
> printed. `5d8df79` added `test_contract_certforge.py` beside it, which reads the URLs
> off a real issuance rather than a hand-written list. **B1.5 is unblocked.** See
> `CLAUDE.md` § Tests for the house rule those files are held to: a contract test that
> has never been seen to fail is a comment.

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

### B1.1 — `resolve_principal`: API keys that authenticate · **LANDED** (`d56557b`)

> Shipped as `api/core/principal.py`, not `api_key_auth.py`. Four differences from the
> spec below, all deliberate-looking:
>
> - **No `scopes`, no `mode` string, no migration.** `Principal` carries `is_test`,
>   derived from the presented key's prefix. Nothing needed a scope yet, and the raw
>   key is the only place the prefix lives — which means `GET /api-keys` cannot tell
>   the dashboard whether a key is live or test. That is the cost of skipping the
>   `prefix` column; it will want adding when the dashboard lists keys.
> - **`cf_prod_` is not accepted.** `looks_like_api_key` matches only `cf_live_` /
>   `cf_test_`, so any key minted by the old `developers.py` now falls through to Clerk
>   verification and 401s. Fine if no `cf_prod_` key was ever handed out; a silent
>   breakage if one was. Worth confirming against the live `api_keys` table.
> - **`last_used_at` is stamped inline**, not out of band, so every authenticated
>   request is a write. Cheap per request, but it is what keeps a read-only workload
>   from being read-only, and on Fly-plus-Neon it wakes the compute.
> - **`require_user` was added** and is not in this plan. Routes that only make sense
>   for a person — creating an org, minting a key, claiming onto a passport — refuse an
>   API key with 403 instead of misattributing the act. Good call.
>
> The conftest landmine below was handled: 127 tests pass.

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

### B1.2 — The service layer and `POST /api/v1/credentials` · **LANDED** (`a403b68`)

> Shipped as `services/issuance.py` + `routes/credentials.py`, with
> `tests/test_credentials.py` covering it. What differs from the spec below:
>
> - **The path is `POST /api/v1/orgs/{slug}/credentials`, not `/api/v1/credentials`
>   with `org` in the body.** Consistent with the rest of the v1 surface, at the cost
>   of making an API key holder name the org it is already scoped to. Defensible; just
>   note that §1's one-line `curl` in this document is now wrong.
> - **Steps 1, 2, 3, 5 of the service are there** — validation, quota, collision-safe
>   ID allocation, `status="issued"` on commit. **Step 6 is not** — and step 4,
>   signing, landed later, on 2026-08-30 (D3). At the time of this entry there was
>   no delivery to skip in test mode,
>   because nothing emails or fires a webhook from this path at all. `is_test` reaches
>   the row as `metadata["_test"]`, so the distinction is recorded and will bind the
>   moment delivery exists.
> - **No idempotency** (D6). The `Idempotency-Key` header is still allow-listed in CORS
>   and still read by nothing on v1.
> - `revoke_credential` landed here rather than in B1.3.

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

### B1.3 — The rest of the resource · **PARTLY LANDED**

> **Done** (`a403b68`): list with cursor pagination, `GET /{id}`, `POST /{id}/revoke`
> with `owner`/`admin` and an idempotent repeat, quota headers on both write and read.
>
> **Done** (`629b454`): the D2 state machine in `models/credential.py`, the
> `badge.json` gate, `passports.py` setting `CLAIMED`. The smoke test above exercised
> the `badge.json` gate for real — an `issued` credential exports a valid badge.
>
> **Done — 2026-08-28, `fad716b`:** `GET /credentials/{public_id}/pdf` (D4/D5). Path and
> auth posture differ from the spec below (site root, no `/api/v1` prefix — see D4).
>
> **Two departures worth knowing:**
>
> - **Revoked returns 404, not 410**, on both `GET /{id}` and the public verify route.
>   The list and detail routes do return a revoked credential to its own org, which is
>   the more important half — but a public caller still cannot distinguish "withdrawn"
>   from "never existed".
> - **`offset` was kept alongside `cursor`**, deliberately, because the dashboard ships
>   against it; cursor wins when both arrive. The docstring argues the case. Reasonable,
>   but it means the skipping-rows bug is still reachable by any client that keeps using
>   `offset` — worth a deprecation date rather than an indefinite dual surface.
> - The `status` query filter accepts `claimed`, which is right under the shipped D2 and
>   would have been wrong under the version in this plan. Nothing to fix; noted so the
>   next reader does not "correct" it.

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

### B1.4 — Batch, and an honest quota surface · **PART LANDED**

> The quota half is done. `4ec4043` pointed `studio.py`'s bulk upload at the service's
> meter — now the public `consume_quota()` in `api/services/issuance.py` — so both
> paths reserve against one counter and the `-1` unlimited bug is gone. Bulk had been
> reading the ledger without writing it back, which is to say bulk issuance was
> unmetered while single issuance metered correctly.
>
> **What remains is the surface, not the meter:** `GET /orgs/{slug}/usage`, `tier` and
> `monthly_quota` on `GET /orgs/{slug}`, and the JSON batch endpoint. The number is
> being written and nothing reads it back out, so the dashboard still cannot show a
> quota — see `docs/billing-and-template-quota-plan.md`, which depends on this counter.
>
> Its duplicate `GET /orgs/{slug}/credentials` was removed in favour of the one in
> `routes/credentials.py`, which is what the comment at the foot of `studio.py` records.

**Touches:** `routes/credentials.py`, `routes/orgs.py`, `routes/studio.py`, tests

- `POST /api/v1/credentials/batch` — a **JSON array**, validated whole, then issued
  through the same service function, so CSV becomes a client convenience rather than the
  only door. Quota is reserved once for the whole array; a partial failure returns
  per-row results in `data.results`, never a silent partial success.
- `GET /api/v1/orgs/{slug}/usage` — period, used, limit, remaining. A4 shipped a
  dashboard that cannot show a quota because nothing exposes one.
- Add `monthly_quota` and `tier` to `GET /orgs/{slug}`.
- ~~Point `studio.py`'s bulk upload at the same quota helper, which also fixes the `-1`
  unlimited bug at `studio.py:74`.~~ **Done in `4ec4043`.**

**Accept:** a 60-row batch against a 50-quota org is rejected whole with 402 and writes
nothing; `usage` reflects reality after B1.2 issues.

### B1.5 *(optional, separate review)* — the legacy adapter · **NOT STARTED** *(no longer blocked — B1.0 landed)*

Only under B1.0's golden test, one shared step at a time, per D1. Stop at the first step
that needs a mode flag.

---

## 5. Landmines, collected

1. ~~**`conftest.py`'s `mock_clerk` breaks in B1.1.**~~ Handled in `d56557b`; the suite
   went 91 → 127 without a red intermediate.
2. **`ruff check apps/api/api/ sdk/pdfcert/` is the CI gate** — every new file is inside
   the checked tree.
3. **No `vercel.json` change is needed** (`/api/:path*` covers it), but `_build_llms_txt`
   in `index.py` should learn about `/api/v1/credentials`, since the agent-discovery
   surface exists to describe the machine-facing API. **Still open, checked 2026-08-28:**
   `_build_llms_txt` describes only the frozen legacy surface (`/api/certificate`
   etc.); nothing under `/api/v1` is mentioned, and `fad716b` did not touch it either.
4. **PDF generation fails locally on Windows** (`TTFError`, the font-locking quirk in
   CLAUDE.md). Do not chase it; assert the `/pdf` route's status and content type
   locally and let CI assert the bytes.
9. **`tests/test_db.sqlite` can survive a crashed local pytest run and lock on
   Windows** (`conftest.py`'s `setup_db()` swallows the `OSError` from a failed
   `os.remove`). When that happens, `Base.metadata.create_all()` is a no-op against the
   stale file's existing tables, so a model gains a column in code but the test DB never
   sees it — every test touching that column fails with `OperationalError: no such
   column`, on tests unrelated to whatever you just changed. Observed 2026-08-28
   chasing the branding-column tests: `rm test_db.sqlite` failed with "Device or
   resource busy"; the next `pytest` run passed clean once the lock cleared on its own.
   Same family of issue as #4 — a Windows-only artifact of on-disk state, not a code
   defect. If it recurs, look for a leftover `python.exe`/pytest process rather than
   editing the model.
5. **`session.bulk_save_objects`** (`studio.py:111`) bypasses ORM defaults — do not copy
   that pattern into the batch path.
6. **Two quota sources of truth**: `org.monthly_quota` and `BILLING_TIERS[tier]`. The
   service reads `org.monthly_quota`; billing is what keeps it in sync. Put that in the
   service docstring.
7. **`-1` means unlimited**, and every comparison must special-case it.
8. **`CERTFORGE_WEB_URL` serves none of its public paths.** `/verify/{id}`,
   `/credentials/{id}/badge.json` and `/orgs/{slug}` all 404 live — only `/claim/{id}`
   resolves — yet those are the URLs baked into every QR code and into the Open Badges
   `issuer.id`. Proven live, 2026-08-27. Written up in
   [TODOs/certforge-public-urls-404.md](./TODOs/certforge-public-urls-404.md); it is
   the highest open item, because printed credentials already point at a 404.

---

## 6. Explicitly out of scope

Object storage for PDFs, per-key rate limiting, the Studio frontend, retiring the CSV
upload, and any change to `/api/certificate`'s wire format. B1.5 is the only place the
frozen surface is touched at all, and it is optional.
