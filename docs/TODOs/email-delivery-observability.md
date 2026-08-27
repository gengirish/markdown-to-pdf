# TODO · Credential email delivery is unobservable

**Opened** 2026-08-27 · **Status** open · **Trigger** first production bulk issuance
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

## Related

- `worker.py:169-177` is the only credential-email call site on the CertForge surface.
  **Single issuance sends nothing at all** (`services/issuance.py`) — the `send_email`
  flag in the B1 plan was never implemented. Whatever shape delivery state takes, it
  should be settled before that path grows its own sender, or there will be two.
- [b1-single-credential-issuance.md](../b1-single-credential-issuance.md) §Production
  smoke test — the same run, and the `CERTFORGE_WEB_URL` `/verify` 404 it uncovered,
  which is the more urgent of the two findings.
