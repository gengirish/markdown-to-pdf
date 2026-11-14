# Plan: credential email and the provider's daily send limit

Status: **P0–P5 built 2026-11-13, not yet deployed.** P6 (the advisory
forecast) is not built. Changes from the plan below:

- **P0 was already answered** by `tests/test_email_rate_limit.py`, which holds
  the real production 429: `retry-after: 52642`, `ratelimit-reset: 52642`,
  body `{"code": "rate_limit_exceeded", "limit": 100, "window": "daily"}`. So
  the provider sends a wait time, and the fallback (next midnight UTC + 5 min)
  only applies if a 429 ever arrives without one.
- **The batch status counts delivery off the rows** (`_live_delivery_counts`
  in `routes/studio.py`) rather than the batch's stored counters. Those are
  written once by the batch pass, so a row deferred and sent the next morning
  would never have reached `delivered`.
- **A retried email now carries the org's branding.** `_retry_delivery_sync`
  sent without `org` and fell back to the platform brand.
- Every guard in `tests/test_deferred_delivery.py` was seen to fail with its
  bug put back.

Originally: **planned 2026-11-12.**

Trigger: on 2026-11-12 the org `navodaya-vidyalaya-alumni-…` bulk-issued 86
credentials between 09:13:02 and 09:13:27 UTC. The first 39 emails went out.
From 09:13:19 on, every send failed with AgentMail's
`Daily send limit exceeded`, and so did each row's automatic retry a few
seconds later. That left 44 rows at `failed` with `delivery_attempts = 2`,
one attempt short of `MAX_DELIVERY_ATTEMPTS`.

The credentials were issued correctly and still verify. The only thing that
failed was the email, and nothing was wrong with any address or template.

---

## What is true today

Read from `api/core/email.py`, `api/services/delivery.py`,
`api/core/worker.py`, `api/services/issuance.py`,
`api/services/operator_console.py`, `api/routes/studio.py`,
`api/models/credential.py`.

| # | Finding | Why it matters |
|---|---|---|
| F1 | `agentmail_deliver` returns `(bool, str)`. A 429 and a bad API key both come back as `False` plus a string. | The caller can't tell "try again tomorrow" from "this will never work". The status code and headers are on the SDK's `ApiError` (`status_code`, `headers`) and get discarded. |
| F2 | `deliver_credential_email` adds 1 to `delivery_attempts` before every send, whatever the outcome. | A 429 mails nobody but still uses up one of the three attempts. The ceiling exists to stop us mailing one person on a loop, and a refused send doesn't do that. |
| F3 | `process_batch` calls `retry_delivery.defer_async(...)` with no `schedule_in`, so the retry runs seconds after the first failure. | Against a daily cap the retry can't succeed. It is why all 44 rows show `attempts = 2`. |
| F4 | The batch loop calls the provider for every row, even after the provider has said no. | After the first 429, each of the remaining 44 rows makes a call it already knows will fail, and each of those calls uses an attempt. |
| F5 | The org resend (`resend_credential`) and the operator resend both go through `deliver_credential_email`. | Resending while the cap is still in force uses up the **last** attempt on all 44 rows. The row then can't be resent at all. |
| F6 | The legacy surface (`index.py`, `_agentmail_deliver`) sends from the same AgentMail account and records nothing in the database. | Counting today's sends from `credentials` will always undercount the account's real usage. Any "allowance left" figure we compute is an estimate, never the truth. |
| F7 | The machine scales to zero, and a Procrastinate job scheduled for later doesn't wake it (the same posture as webhook retries). | A send deferred to "after the reset" actually goes out at the first wake after the reset, which may be much later. |

Unknowns that change the details (Phase 0):

- The exact AgentMail 429 body and headers: is there a `Retry-After` or an `X-RateLimit-Reset`?
- When the daily limit resets: midnight UTC, a rolling 24 hours, or account-local time. The comment at `email.py:23-28` notes one reset fourteen hours after the cap was hit.
- The daily number on our current plan, and whether AgentMail exposes usage through its API.
- Whether there is also a short per-second rate limit that returns 429 with a small `Retry-After`.

---

## Decisions

### D1. A rate-limited send is *deferred*, not *failed*

Add a sixth delivery state, `deferred`: "the provider refused for volume. It
will be sent automatically after `delivery_next_attempt_at`."

Why not keep `failed` and just skip the increment:

- `failed` reads "Email failed" in the dashboard and shows a Resend button. For a deferred row both are wrong: it will go out on its own, and resending now just hits the cap again.
- `models/credential.py` already argues for named states over ad-hoc reuse ("adding a fifth forces a decision about what every surface does with it"). The same applies to a sixth.

New column: `credentials.delivery_next_attempt_at TIMESTAMPTZ NULL`. It is set
only while `delivery_status = 'deferred'` and cleared on every other
transition.

`deferred` is **not** in `DELIVERY_RETRYABLE`. That set means "a failure the
worker may retry and count". A deferred row has its own release path (D4).

### D2. A rate-limited send does not consume an attempt

The increment moves to *after* the provider answers. It happens on an
accepted send or a real rejection, never on a 429. `delivery_attempts` then
means "times the provider accepted or rejected this message", which is what
the ceiling was always meant to bound.

To stop a row from being deferred forever, use a **deadline** instead of a
counter. Once a row has been deferred for longer than
`MAX_DEFERRAL = 7 days` (measured from `issued_at`), the next 429 turns it
into `failed` with the error
`"Provider daily limit persisted for 7 days; not sent."`. It then has its
normal attempts left for a manual resend.

### D3. One send gate, shared by every CertForge sender

A small table records that the provider is paused:

```
email_send_pauses(provider TEXT PK, paused_until TIMESTAMPTZ, reason TEXT, updated_at TIMESTAMPTZ)
```

- A 429 anywhere (batch, single issue, retry, resend) upserts `paused_until`. The value is `Retry-After` when the provider sends one; otherwise it's the next reset by the rule Phase 0 settles, plus 5 minutes of slack.
- Before each send, `deliver_credential_email` reads the gate (memoised per process for a few seconds, so a 500-row batch doesn't do 500 reads). If the gate is closed, it marks the row `deferred` **without calling the provider**.
- It lives in the database, not in memory, because memory doesn't survive a machine stop (the idempotency cache already learned that) and a second instance wouldn't see it.

This is what fixes gap 2 without needing to know the allowance in advance.
The batch sends until the provider first says no. That one refused call trips
the gate, and every remaining row is deferred at zero cost. "Queue the rest
for tomorrow" falls out of the gate, so it needs no forecast.

The legacy sender (`index.py`) is **not** wired to the gate. Its response
shape is frozen, and the sender lives inside the frozen file. It keeps
drawing on the same allowance (F6), and that's accepted.

### D4. Deferred rows are released by the existing periodic sweep

`recover_batches` already runs once a minute while the machine is up. Add
`release_deferred_deliveries` next to it:

1. If the gate is closed, do nothing.
2. Otherwise select `deferred` rows with `delivery_next_attempt_at <= now()`, oldest `issued_at` first, `LIMIT 50`, `FOR UPDATE SKIP LOCKED`.
3. Send them one at a time through `deliver_credential_email`. On the first 429 the gate closes again and the rest of the page stays deferred, at a cost of one refused call. 44 rows coming due at the same instant must not turn into 44 refused calls.

The same sweep is the backstop for any scheduled `retry_delivery` job that
gets lost, the way `recover_batches` is for lost batch jobs.

`process_batch` stops deferring an immediate `retry_delivery` for rows that
are `deferred`. Real failures keep today's retry, but now with
`schedule_in` of a few minutes rather than none (F3).

### D5. Resend respects the gate, and says why

Both resend paths check the gate first. While it's closed they answer
**409**, typed `email_paused`, with the message
`"Email sending is paused until 14:05 UTC (provider daily limit). This credential will send automatically."`
That costs no attempt and makes no provider call.

`resend_refusal()` in `operator_console.py` gets the same rule, so the
operator console shows the reason instead of a Resend button that only fails.
A `deferred` row is never resendable. It is already queued.

### D6. A forecast is advisory only, and comes last

A pre-batch warning ("about 40 of these 86 will send today, the rest after
the reset") is useful, but it can only be an estimate (F6). If we build it:

- Use `AGENTMAIL_DAILY_SEND_LIMIT` (config), less today's CertForge sends counted from `delivered_at` and attempts. If Phase 0 finds a usage endpoint, prefer that.
- Show it in the upload response and on the batch page. **Never block** an upload with it. The gate is what's actually enforced.

---

## Phases

Each phase ships and rolls back on its own.

### P0. Find out what the provider actually sends (no code)

- Search `fly logs` for the 2026-11-12 09:13 `AgentMail send to … failed` lines. `ApiError.__str__` prints headers, status code and body, so if a line is still there it answers most of the unknowns. It may have rolled off.
- Read AgentMail's docs and our plan for the daily limit, reset semantics and any usage endpoint.
- If the logs are gone, capture a 429 on purpose with a test inbox against a low limit, or wait for the next one. P1 logs the full error once on the first 429 so this never has to be guessed again.
- Write the answers into this file under "What is true today".

### P1. Classify the refusal, and stop it using attempts

- `core/email.py`: `agentmail_deliver` returns a `SendResult(ok, kind, message, retry_after)`, where `kind` is `sent | rate_limited | failed`. `rate_limited` means `ApiError.status_code == 429`, or a body message containing `send limit`, as a fallback for the observed text. Parse `Retry-After` (seconds or an HTTP date). Callers that read the tuple are updated in the same change; `delivery.py` is the only one.
- `models/credential.py`: add `DELIVERY_DEFERRED = "deferred"` and a `DELIVERY_STATUSES` frozenset that becomes the single source for every pattern below.
- Migration: add `delivery_next_attempt_at`, plus a partial index on it `WHERE delivery_status = 'deferred'`.
- `services/delivery.py`: move the increment as described in D2, write `deferred` on `rate_limited`, and apply the D2 deadline.
- `routes/credentials.py` and `routes/operator.py`: build the `delivery_status` regex from `DELIVERY_STATUSES` instead of hand-writing it.

### P2. The send gate

- Model and migration for `email_send_pauses`. `services/send_gate.py` with `is_paused()` / `pause(until, reason)`, memoised for a few seconds.
- `deliver_credential_email` checks the gate before calling the provider, and closes it on `rate_limited`.
- Resend paths and `resend_refusal()` respect the gate (D5).
- `process_batch`: no immediate retry for deferred rows; `schedule_in` for real failures.

### P3. Release sweep and deadline

- `release_deferred_deliveries` periodic task (D4).
- Deadline handling (D2), with the error text above.

### P4. Surfaces

- `apps/web/lib/api.ts` `DeliveryStatus` and `apps/web/lib/operator.ts`: add `deferred`.
- `components/dashboard/credentials-card.tsx` and `recent-credentials-card.tsx`: an "Email scheduled" status filter, and a row badge reading "Sends after 14:05 UTC".
- `components/operator/deliveries-panel.tsx`: the `deferred` option, and adding it to `STUCK` only once it's past `delivery_next_attempt_at` plus 30 minutes, which is the real "stuck" signal.
- Batch status (`routes/studio.py` `get_batch_status`): add `delivery_deferred` as a live count over the batch's rows. It's not a stored counter, because a stored counter would have to be decremented by the sweep, and that is a second writer to keep in step.

### P5. Repair the 44 rows from 2026-11-12

`python -m api.repair_rate_limited_deliveries [--apply]`, run on the Fly
machine, dry run by default, in the shape of `api.reconcile_subscription`.

- Selects `failed` rows whose `delivery_error` starts with `Daily send limit exceeded` and that are not revoked or test credentials.
- Sets them to `deferred`, with `delivery_next_attempt_at = now()`. Each one is logged.
- **Leaves `delivery_attempts` as it is.** We can't prove how many of the 2 attempts were refusals, because the error column keeps only the last one, and this codebase doesn't backfill what it can't prove. With 2 of 3 used, a later accepted send takes the row to 3. That's fine, because it was delivered.

Until P5 runs: **do not resend those rows by hand while the cap is in force**
(F5).

### P6. Advisory forecast (optional)

D6, only after P0 says what we can measure.

---

## Tests

House rule: each guard below must be seen to fail by putting the bug back on
purpose before it counts.

| Test | Asserts | Break it by |
|---|---|---|
| 429 is deferred | Fake `ApiError(status_code=429, headers={"retry-after": "3600"})`: status `deferred`, `delivery_attempts` unchanged, `delivery_next_attempt_at` ≈ now + 1h | Restoring the pre-send increment |
| Real failure still counts | A 403 → `failed`, attempts +1 | Classifying every `ApiError` as rate-limited |
| Batch stops at the gate | Fake provider that accepts 4 and then 429s. A 10-row batch gives 4 `sent`, 6 `deferred`, and **exactly 5 provider calls** | Removing the pre-send gate check |
| Resend while paused | 409 `email_paused`, attempts unchanged, 0 provider calls | Dropping the gate check from `resend_credential` |
| Operator resend refusal | `resend_refusal()` names the pause, and a `deferred` row is never resendable | Same, in `operator_console.py` |
| Sweep caps the stampede | 44 due rows, provider 429s at once: 1 call, 44 still `deferred` | Sending the page without re-reading the gate |
| Sweep releases in order | Gate open: rows sent oldest first, `next_attempt_at` cleared | Ordering by id |
| Deadline | A row issued 8 days ago that gets a 429 → `failed`, with the deadline message | Removing the deadline branch |
| Status vocabulary join | `DELIVERY_STATUSES` equals the values accepted by both route regexes **and** the `DeliveryStatus` union parsed out of `apps/web/lib/api.ts` | Adding `deferred` to the backend only. This is the two-halves failure mode the root CLAUDE.md warns about |
| Retry-After parsing | Seconds, HTTP date, missing → fallback reset rule | Returning `None` for the date form |

`cd apps/api && python -m pytest` stays green. Nothing here touches the
legacy surface, so `test_contract_legacy.py` is unaffected.

---

## Open questions for the owner

1. **Wake the machine for deferred sends?** As planned, deferred emails go out at the first wake after the reset (F7). A once-daily scheduled wake just after the reset (a Fly scheduled machine, or a cron hitting `/api/health`) would make "tomorrow" mean tomorrow. It goes against the no-keep-alive posture, but only once a day.
2. **Raise the AgentMail plan?** This plan makes hitting the cap graceful. It doesn't change how many emails a day we can send. A cohort of a few hundred will still take several days on the current limit.
3. **Is 7 days the right deadline** for `MAX_DEFERRAL`?
