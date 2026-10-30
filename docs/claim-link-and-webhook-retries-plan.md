# Plan: the claim link in the delivery email, and webhook delivery retries

Status: **planned 2026-10-30, not started.** These are the two items the
landing page's status section (`apps/web/app/page.tsx`, `STATUS`) lists as not
live: "Claim link in the delivery email" (In build) and "Webhook delivery
retries" (Not yet). Each part ships separately and can be rolled back
separately. Part A goes first because it closes a security gap, not only a
feature gap.

---

## Part A: a claim link in the delivery email

### What is true today

Read from `api/routes/passports.py`, `api/services/delivery.py`,
`api/models/credential.py`, `api/core/auth.py`, `apps/web/app/claim/[credential_id]/page.tsx`.

| # | Finding | Why it matters here |
|---|---|---|
| A1 | `POST /api/v1/claims/{credential_id}` needs only **a signed-in user and the public ID**. The first person to claim a credential owns it, and every later claimant gets a 403. | The public ID is not a secret. It is printed in the certificate's QR code, shown on `/verify/{id}`, and is part of every badge URL. Anyone who sees a certificate can claim it into their own passport first, and the real recipient is then locked out. Putting a claim link in the email without fixing this tells recipients that claiming is theirs to do when it isn't. |
| A2 | Clerk's default session token has no email claim (`auth.py`, `_EMAIL_CLAIMS`). `principal.email` is usually `None`. | "Claim only if your sign-in email matches `recipient_email`" can't be checked from the token. It would need a Clerk Backend lookup on every claim, and people often sign in with a different address than the one an issuer has on file. |
| A3 | `build_credential_email` rebuilds the whole message from the credential row alone, so `retry_delivery` can resend it. | A claim link must be computable from the row (plus a server secret) at any time. It can't depend on request state or on a one-time value that was never stored. |
| A4 | The email has two links: "View Your Credential" (`/verify/{id}`) and "Download PDF". | The claim link is a third link, and it shouldn't replace either: verifying needs no account, and that stays the main action. |
| A5 | `apps/web/app/claim/[credential_id]/page.tsx` already shows the credential, signs the visitor in, and calls the claim API. Its only callers are `lib/api.ts` and the API tests (`test_passports.py`, `test_principal.py`); the SDK and `examples/` don't call it. | Requiring proof on a claim changes the API for one web page and two test files, and for no external client. |
| A6 | `POST /orgs/{slug}/credentials/{id}/resend` already exists. | Recipients of credentials issued before this change can get a link by having the issuer resend the email. No backfill is needed. |

### Decision A1: a claim needs a token that only the email carries

The claim token is an HMAC of the credential's public ID:

```python
def claim_token_for(public_id: str) -> str:
    return hmac.new(CLAIM_SECRET, f"claim:{public_id}".encode(), sha256).hexdigest()[:32]
```

- **Stateless**, like the rest of this codebase's signed URLs. Nothing is
  stored, so a retry or a resend rebuilds the same link (A3).
- **Its own secret:** `CERTFORGE_CLAIM_SECRET`, required in production (fail
  closed, the way `CERT_SECRET_KEY` already does) and never shared with
  `CERT_SECRET_KEY`. Rotating it invalidates unclaimed links only, and a
  resend fixes those (A6). Rotating `CERT_SECRET_KEY` would also invalidate
  every legacy certificate.
- **128 bits** (32 hex characters). That's enough that it can't be guessed,
  and short enough for a link that doesn't wrap in a mail client.
- The `claim:` prefix scopes the HMAC, so a token can never double as some
  other signature made with the same key.

`POST /claims/{credential_id}` takes `{"token": "..."}` and compares it with
`hmac.compare_digest`:

| Request | Answer |
|---|---|
| No token or wrong token, credential not yet claimed | **403** `claim_token_invalid` |
| Correct token, not yet claimed | Claims it (as today) |
| Already claimed by this user, with or without a token | 200, idempotent (as today). The holder doesn't need the email again. |
| Already claimed by someone else | 403 (as today) |
| Revoked or unknown | 404 (as today) |

**Alternative considered: match the signed-in email against `recipient_email`.**
It needs a Clerk Backend call per claim (A2), and it fails for anyone signed
in under a different address than the one the issuer used. This is a
reasonable *fallback* to add later for recipients who lost the email. It's
not the primary check, and it isn't in this plan.

**Credentials that were already claimed by the wrong person** before this
ships can't be told apart from legitimate claims in the data. That's out of
scope; if it is ever reported, the fix is an operator "release claim" action.

### Decision A2: the email gets a third link

- The HTML email gets a secondary link under the PDF link, "Add it to your
  CertForge passport". The text email gets a matching line.
- URL: `{CERTFORGE_WEB_URL}/claim/{public_id}?t={token}`. It uses
  `CERTFORGE_WEB_URL`, never `SITE_URL`, for the same reason `verify_url_for`
  does.
- **Test-mode credentials send no email at all**, so they get no link.

### Decision A3: the claim page passes the token through

`/claim/[credential_id]` reads `t` from the URL and sends it with the claim.

- **No `t` and not yet claimed:** the page says the link is incomplete and to
  use the link from the email, or ask the issuer to resend it. It doesn't
  show a claim button that's bound to fail.
- **The token must survive sign-in:** carry `?t=` through Clerk's
  `redirect_url` so it isn't dropped between the click and the claim.
- **Never log the token:** keep `t` out of client error reporting, and out of
  any analytics if analytics is ever added.

### Work packages

1. **A-API** (`services/claims.py` new, `routes/passports.py`, `core/config.py`):
   the token helper, the secret with its production guard, and enforcement
   on the claim endpoint. Before deploying, run
   `fly secrets set CERTFORGE_CLAIM_SECRET=$(openssl rand -hex 32)`.
2. **A-email** (`services/delivery.py`): the link in both bodies.
3. **A-web** (`app/claim/[credential_id]/page.tsx`, `lib/api.ts`): pass `t`
   through, keep it across sign-in, and handle a missing token.
4. **A-status:** move "Claim link in the delivery email" to Live in
   `app/page.tsx`. This ships with A-web, not before it.

A-API and A-web have to deploy together. Between them, the live page would
claim with no token and get a 403. Ship the API with enforcement behind
`CLAIM_TOKEN_REQUIRED` (default off), deploy the web page, then turn it on.

### Tests

Each guard below must fail against the bug it names before it counts.

| Guard | Bug to reintroduce to see it fail |
|---|---|
| Claiming an unclaimed credential with no token, a wrong token, or another credential's token returns 403 and leaves `claimed_by_user_id` NULL. | Drop the token check. |
| The correct token claims it, and the same user re-claiming without a token returns 200. | Require the token on an idempotent re-claim. |
| The token comes from `CERTFORGE_CLAIM_SECRET`: changing that secret changes the token, and changing `CERT_SECRET_KEY` doesn't. | Derive it from `CERT_SECRET_KEY`. |
| Production boot fails without `CERTFORGE_CLAIM_SECRET`. | Add a dev-default fallback. |
| The delivery email, both HTML and text, contains `/claim/{id}?t={valid token}` on `CERTFORGE_WEB_URL`, and a rebuilt retry email contains the same link. | Build the URL from `SITE_URL`, or from request state. |
| The comparison uses `hmac.compare_digest`. | Use `==`. (Check this in review; a test can't reliably catch it.) |

---

## Part B: webhook delivery retries

### What is true today

Read from `api/core/worker.py` (`_process_batch_sync`), `api/routes/developers.py`,
`api/models/api_key.py`, `apps/web/components/dashboard/developer-card.tsx`.

| # | Finding | Why it matters here |
|---|---|---|
| B1 | `batch.completed` is POSTed **once**, synchronously inside `_process_batch_sync`, with a 5s timeout per endpoint. | One blip on the customer's side and the event is gone. A slow endpoint also delays the batch job it is sent from. |
| B2 | **A non-2xx response counts as success.** `httpx` doesn't raise on 4xx or 5xx, so a 500 from the receiver is logged "Webhook dispatched". | Retries can't be built on top of this. Today even the log line is wrong. |
| B3 | Nothing records a delivery. | Neither a customer nor support can answer "did you send it?" |
| B4 | The payload has no event id, and the signature is `HMAC(secret, body)` with no timestamp. | Once retries exist, a receiver can't tell a retry from a new event, and a captured request can be replayed forever. |
| B5 | Only the bulk path sends a webhook, and only `batch.completed`. Single issuance sends none. Meanwhile the developer card says "Add one to be told when a credential is issued". | The dashboard promises an event that never fires. Fix the copy in this part; a `credential.issued` event is a separate feature. |
| B6 | The worker is Procrastinate inside the Fly machine, which scales to zero. Jobs persist in Postgres, but nothing runs them while the machine is stopped. | A retry scheduled for "in 5 minutes" runs at the next wake, which may be hours later. Inbound HTTP is the only thing that wakes the machine. |

### Decision B1: a delivery is a row, and each attempt is a job

Add a new table, `webhook_deliveries`:

| column | |
|---|---|
| `id` | UUID PK. Also the **event id** sent to the receiver; it stays the same across attempts. |
| `endpoint_id` | FK → webhook_endpoints, `ondelete=CASCADE` |
| `org_id` | FK → organizations, for listing |
| `event` | `batch.completed` |
| `payload` | JSON, the exact body, so every attempt sends the same bytes |
| `status` | `pending` · `succeeded` · `failed` (attempts left) · `abandoned` (out of attempts) |
| `attempts` | int |
| `next_attempt_at` | timestamptz, null once final |
| `last_status_code`, `last_error` | what the receiver said, with the error truncated like `delivery_error` |
| `created_at`, `delivered_at` | |

- **Batches write rows, not requests.** `_process_batch_sync` inserts one row
  per subscribed endpoint, in the batch's own transaction. After commit it
  defers `deliver_webhook(delivery_id)`, the same way
  `process_batch` defers `retry_delivery`. No HTTP call is made inside the
  batch any more (B1).
- **One attempt:** POST with a 10s timeout. **Only a 2xx counts as success**
  (fixes B2). Each attempt updates its row.
- **Retry schedule:** 1 min, 5 min, 30 min, 2 h, 6 h, 12 h, then `abandoned`.
  That's 7 attempts over about 21 hours. Retry on network errors, timeouts,
  and any non-2xx, honouring `Retry-After` when it is longer than the next
  step. Schedule each retry with Procrastinate's `schedule_in`.
- **Scale-to-zero is accepted, not fought (B6).** A due retry runs at the next
  wake. No keep-alive, no external cron to wake the machine, and no
  `recover_batches`-style sweep with a short interval that would touch Neon:
  any of those would keep Fly and Neon awake around the clock to save a few
  minutes on a retry. The delivery log shows `next_attempt_at`, so the delay
  is visible rather than silent. The webhook docs say that a retry can run
  late.
- **Retention:** delete deliveries older than 30 days when a new one is
  inserted for the same endpoint (`DELETE … WHERE endpoint_id = ? AND
  created_at < now() - 30d`). This happens on the write path, so it needs
  no timer.

### Decision B2: an event id, a timestamp, and a signature receivers can check for replays

New headers on every attempt:

```
X-CertForge-Event-Id:     <delivery id>
X-CertForge-Timestamp:    <unix seconds of this attempt>
X-CertForge-Signature-256: t=<timestamp>,v1=<hex HMAC(secret, f"{t}.{body}")>
```

- **`x-certforge-signature` stays as it is.** Existing receivers verify it,
  and changing it would break them silently. Mark it deprecated in the docs,
  then remove it in a later release after announcing it.
- **Receivers dedupe on the event id (B4).** The docs say so, along with the
  5-minute window for timestamps.
- `event` and `delivery_id` are also added to the JSON body, which can be
  extended without breaking receivers.

### Decision B3: customers can see deliveries and resend one

- `GET /api/v1/orgs/{slug}/webhooks/{id}/deliveries`: the 50 most recent,
  newest first, showing status, attempts, last code and error, and
  `next_attempt_at`.
- `POST /api/v1/orgs/{slug}/webhooks/{id}/deliveries/{delivery_id}/redeliver`:
  sends one more attempt with the same event id. It works on `abandoned`
  deliveries and doesn't reset the automatic schedule.
- Both use the same checks as webhook management today (`require_user`,
  then `require_org_access(..., allowed_roles=("owner", "admin"))` and
  `require_grant(org, "api_access")`). The delivery is looked up by id
  **and** org. Neither is public, so neither goes in `_build_llms_txt` or
  `_build_sitemap_xml`.
- **Developer card:**
  - each endpoint shows its last delivery, as a status tag with the
    response code.
  - an expandable list of recent deliveries, with a Redeliver button on
    failed and abandoned ones.
  - the copy is fixed to "Get told when a CSV batch finishes" (B5).

### Work packages

1. **B-model** (`models/api_key.py`, migration): the table. Run the migration
   against a Neon branch of production before merging, as in the operator
   plan.
2. **B-dispatch** (`core/worker.py`, `services/webhooks.py` new): rows written
   in the batch transaction, the `deliver_webhook` task, 2xx-only success, the
   retry schedule, the new headers, and retention. Ships with B-model.
3. **B-api** (`routes/developers.py`): the deliveries list and redeliver.
4. **B-web** (`developer-card.tsx`, `lib/api.ts`): delivery status, the list,
   Redeliver, and the copy fix.
5. **B-docs and status:** nothing documents `/api/v1` webhooks yet. The
   README has only a row in its endpoint table. `examples/webhook_receiver.py`
   handles the legacy `callback_url` event (`certificate.created`) and
   verifies no signature. So:
   - add a webhooks section to the README covering the headers, dedupe on
     the event id, signature verification, and the late-retry caveat.
   - add `examples/certforge_webhook_receiver.py`, which verifies
     `X-CertForge-Signature-256` and rejects stale timestamps.
   - add the same points to `_build_llms_txt`.

   Then move "Webhook delivery retries" to Live in `app/page.tsx`.

### Tests

| Guard | Bug to reintroduce to see it fail |
|---|---|
| A receiver answering 500 leaves the delivery `failed` with `last_status_code=500` and a retry scheduled. | Treat a returned response as success (today's B2). |
| A timeout schedules a retry. The 7th failure marks it `abandoned` and schedules nothing more. | Remove the attempt cap. |
| Every attempt of one delivery sends the same event id and the same body bytes. | Rebuild the payload per attempt, or make a new id per attempt. |
| `X-CertForge-Signature-256` verifies over `f"{t}.{body}"` with the endpoint's secret, and the legacy `x-certforge-signature` is unchanged. | Sign the body alone, or drop the legacy header. |
| A batch whose webhook endpoint hangs still completes, and the batch job makes no HTTP call. | Move the POST back inside `_process_batch_sync`. |
| A batch that rolls back leaves no delivery row and defers no job. | Defer the job before the batch commits. |
| Redeliver on an `abandoned` delivery sends one attempt with the same event id. Another org's member gets 404. | Scope the lookup by delivery id alone. |
| Rows older than 30 days for an endpoint are gone after the next insert for it. | Drop the retention delete. |
| The developer card no longer promises an event when a credential is issued. | Restore the old copy. (Snapshot test the string.) |

---

## Out of scope

- A `credential.issued` webhook for single issuance (B5). It is a new event,
  not a retry.
- Matching a claimant's sign-in email to `recipient_email` (the fallback in Decision A1).
- Releasing a claim made by the wrong person before Part A shipped.
- Encrypting webhook secrets at rest. The API needs the plaintext to sign.
