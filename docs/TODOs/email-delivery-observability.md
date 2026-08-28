# TODO · Credential email delivery is unobservable

**Opened** 2026-08-27 · **Status** deployed 2026-08-27 (`a0a530d`, migration
`c3d81ea47b19` applied via `release_command`); no live send confirmed yet ·
**Trigger** first production bulk issuance
(`CF-2026-XEHQNMFZ`, batch from `examples/sample-participants.csv`) — the credential
issued and verified fine, and **no email arrived**. We could not determine why.

## What happened

Three participation rows were bulk-issued, all to the same address. The credential
resolves (`GET https://certs.intelliforge.tech/verify/CF-2026-XEHQNMFZ` → 200, status
*Issued*) and its `badge.json` is well-formed. No email was received.

## What we ruled out

AgentMail is configured and healthy on the deployed API:

```
GET /api/health  →  {"dependencies": {"database": "connected", "email": "ready"}}
fly logs         →  INFO:api.core.email:AgentMail inbox ready (support@intelliforge.tech)
```

The send branch **did execute**. In `worker.py:169-177` the send runs *before*
`cred.status = "issued"`, and the credential is `issued` — so the worker reached it.

## What we could not determine, and why

Two candidates remain, and nothing on the system can distinguish them after the fact:

1. `cred.recipient_email` was empty, so `if cred.recipient_email:` skipped silently.
2. `agentmail_deliver` returned `False` and `worker.py:176` logged a warning.

Both are invisible ten minutes later. The Fly log buffer held ~100 lines starting
02:45; issuance was 02:38, so the only record of either outcome had already rolled off.

**This is the actual defect.** Delivery has no persisted state:

| | Today |
|---|---|
| Failure record | one `logger.warning`, nothing else (`worker.py:176`) |
| Retry | none |
| State on the credential | none — no `delivery_status`, no `delivered_at`, no error |
| State on the batch | none — `succeeded`/`failed` count *renders*, not sends |
| Skipped-because-no-email | indistinguishable from sent |

So a credential whose email silently failed is byte-identical, in the database, to one
that was delivered. Every future report of "I didn't get it" is unanswerable the same
way this one was.

## Proposed fix

1. **Persist delivery state on `Credential`**: `delivery_status`
   (`not_requested` | `pending` | `sent` | `failed`), `delivered_at`, `delivery_error`.
   `not_requested` is what an empty `recipient_email` writes — that alone separates
   candidate 1 from candidate 2.
2. **Count it on `CredentialBatch`**, separately from the render counters, so a batch
   can report "30 issued, 28 delivered, 2 failed" instead of implying all 30 landed.
3. **Retry** a failed send — the worker is already on Procrastinate, so this is a
   deferred job with backoff, not new infrastructure.
4. **Expose it** on `GET /api/v1/credentials/{id}` and the batch status route, so
   support can answer the question from the API rather than from logs that expire.
5. **Backfill** existing rows as `unknown` rather than guessing.

## Resolution (2026-08-27, deployed)

All five proposed items, plus the `send_email` flag the B1 plan documented and never
implemented. 180 tests, up from 164.

| | |
|---|---|
| `models/credential.py` | `delivery_status`, `delivered_at`, `delivery_error`, `delivery_attempts` on `Credential`; `delivered` / `delivery_failed` on `CredentialBatch`; the states defined once, beside the lifecycle block. |
| `services/delivery.py` | **new** — the one sender. Both issuance paths call it. |
| `core/worker.py` | inline sender replaced; delivery counted apart from renders; failed sends deferred to a retry task. |
| `services/issuance.py` | honours `send_email`; every branch writes a terminal delivery state. |
| `routes/credentials.py` | `send_email` on the request; `delivery` on the response and on `GET /credentials/{id}`. |
| `routes/studio.py` | batch status reports `delivery`. |
| `migrations/…c3d81ea47b19` | the columns, backfilled `unknown`. |

### The state that does the work

`NOT_REQUESTED` is the whole point. The incident could not be explained because an
empty `recipient_email` and a rejected send both wrote **nothing** — a silent `if`
and a `logger.warning` that had rolled off the Fly buffer. Separating "we never
tried" from "we tried and it failed" is the difference between an answerable support
question and the one we could not answer.

Each also records *why*, so `delivery_error` reads "Delivery not requested
(send_email was not set)" or "AgentMail rejected the request (403)" rather than
leaving it to be inferred.

### One sender, deliberately

The TODO warned that single issuance must not grow its own sender. It now calls the
same `deliver_credential_email` the worker does — one email body, one way of
recording an outcome, one place to fix the next bug.

`send_email` is **off by default**, so no caller written against the version of this
API that could not send email starts sending it. And `is_test` has always documented
"nothing is emailed"; that was vacuously true when nothing was emailed at all, and is
now enforced — a `cf_test_` key never reaches a real recipient even when asked.

### Retry

Failed sends are deferred to a Procrastinate job rather than retried inline, so a
provider outage cannot stall a batch behind one address. `MAX_DELIVERY_ATTEMPTS = 3`
is a hard cap: every AgentMail failure seen so far has been a configuration error,
which retrying does not fix, and an unbounded retry would mail the same person on a
loop. `may_retry` is re-checked when the job runs, because the row may have been
delivered or revoked in between.

`unknown` is excluded from `DELIVERY_RETRYABLE` on purpose — those rows predate any
delivery record, and retrying them would mail people who may have been served months
ago.

### Backfill

`unknown`, never a guess. Writing `sent` or `not_requested` for rows that predate
these columns would invent evidence, which is the exact failure this change exists to
end. Historical batch counters stay at zero for the same reason.

### Verified by breaking it

Reverting the skipped-send branch to the old behaviour — write nothing — fails
`test_a_skipped_send_and_a_failed_send_are_not_the_same_row`, which is the incident
reproduced as a test.

### What is still open

- **Nothing has been sent end to end against real AgentMail.** Every test mocks the
  provider, so the deploy proved the schema and the routes, not delivery itself. The
  first live `send_email: true` issuance is still the real proof — and unlike before,
  it will leave a record either way, which is the point. Use your own address.
- The dashboard does not surface any of this yet; `apps/web` has no delivery UI.
- Bulk issuance still sends whenever a row has an address. Whether the CSV upload
  should carry its own `send_email` is unsettled.


## Related

- `worker.py:169-177` is the only credential-email call site on the CertForge surface.
  **Single issuance sends nothing at all** (`services/issuance.py`) — the `send_email`
  flag in the B1 plan was never implemented. Whatever shape delivery state takes, it
  should be settled before that path grows its own sender, or there will be two.
- [b1-single-credential-issuance.md](../b1-single-credential-issuance.md) §Production
  smoke test — the same run, and the `CERTFORGE_WEB_URL` `/verify` 404 it uncovered,
  which is the more urgent of the two findings.
