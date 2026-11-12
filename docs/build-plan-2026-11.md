# Build plan, November 2026: claim enforcement, webhook retries, cleanup

Status: **planned 2026-11-11.** Nothing here has started. `main` @ `e4aeecc`.

This is a work order for a lead Claude Code session that runs parallel
subagents. Every package has a single owner and a fixed list of files it may
edit. Two packages never edit the same file in the same wave. That rule is
what makes running them in parallel safe, so don't relax it to save time.

Read first, in this order: `CLAUDE.md` (especially the freeze contract and
"The failure mode worth knowing"), then
`docs/claim-link-and-webhook-retries-plan.md` Part B. Part B is the design for
most of this work. This file doesn't repeat it, so if the two disagree on a
design point, Part B wins.

---

## What gets built

| # | Package | Why |
|---|---|---|
| 0 | **Claim enforcement on** (ops) | Part A shipped in #35, but with `CLAIM_TOKEN_REQUIRED` off. Until it's on, anyone who has seen a certificate's QR code can claim the credential before its recipient does. |
| 1 | **B-core**: webhook delivery rows, a retrying task, and 2xx-only success | Today, `batch.completed` is POSTed once from inside the batch job, and a 500 from the receiver is logged as success. |
| 2 | **B-api**: delivery list and redeliver routes | Customers and support currently can't answer "did you send it?" |
| 3 | **B-web**: delivery status on the developer card | This also fixes the card's copy, which promises a `credential.issued` event that never fires. |
| 4 | **B-docs**: README section, example receiver, `llms.txt` | Nothing documents `/api/v1` webhooks yet. |
| 5 | **Vision model as config** | `MODEL = "claude-opus-5"` is hardcoded in `services/vision.py:45`. |
| 6 | **Docs reconciliation** | `CLAUDE.md` and several plan docs contradict each other and the code (details below). |
| 7 | **W4a**: stop writing `monthly_quota` | The first half of dropping a column that nothing reads. |
| — | **W4b**: drop the column | This is a **separate later deploy**. It isn't in this round (see W4 below). |

**Deliberately not in this round:**

- **A logo slot in the seeded templates.** The seeded global templates are
  rows written once by `seed.py`, so editing `seed.py` doesn't change a
  database that already exists. It needs a data migration and a decision on
  whether orgs that copied a template get the change. Plan it separately.
- **A `credential.issued` webhook.** Part B lists it as out of scope.

---

## Waves

```
Wave 0  lead, sequential      0  claim flag (needs the user)  ·  .gitignore
Wave 1  4 agents, parallel    1 B-core   3 B-web   4 B-docs   5+6 config & docs
Wave 2  2 agents, parallel    2 B-api    7 W4a
Wave 3  lead, sequential      integration, status flips, gates, PRs
```

Each subagent runs in its own git worktree (`isolation: "worktree"`) on a
branch named `build/<package>`. The lead merges the branches into an
integration branch, `build/2026-11`, in the order shown above. Subagents
never commit to `main`, push, deploy, or run `fly`.

### Why the waves are split where they are

- **Alembic has one head, `b5e2f7a1c9d3`.** B-core adds one migration.
  W4a adds none, and W4b's migration comes later. Never let two packages in
  the same wave create a migration, or there will be two heads and
  `release_command` will fail the deploy.
- **B-api runs after B-core** because it queries the `WebhookDelivery` model.
- **B-web and B-docs can run alongside B-core** because they build against
  the contracts written out below, not against B-core's code. Those
  contracts are the interface. A package that needs to change one stops and
  reports back instead of improvising.
- **W4a runs in Wave 2** because it edits test fixtures that create orgs,
  and B-core's new tests create orgs too. Running it later means B-core's
  tests are written against fixtures that won't change under them. W4a adds
  no migration.

---

## Contracts shared across packages

### Delivery object (B-api produces it; B-web consumes it)

```json
{
  "id": "uuid — also the event id",
  "event": "batch.completed",
  "status": "pending | succeeded | failed | abandoned",
  "attempts": 3,
  "last_status_code": 500,
  "last_error": "string or null, truncated like delivery_error",
  "next_attempt_at": "ISO-8601 or null",
  "created_at": "ISO-8601",
  "delivered_at": "ISO-8601 or null"
}
```

- `GET /api/v1/orgs/{slug}/webhooks/{webhook_id}/deliveries` returns
  `ApiResponse[list[Delivery]]`: the 50 most recent, newest first.
- `POST /api/v1/orgs/{slug}/webhooks/{webhook_id}/deliveries/{delivery_id}/redeliver`
  returns `ApiResponse[Delivery]` with the row as it stands after the job is
  queued. It is allowed on `failed` and `abandoned` deliveries. On any other
  status it returns 409 with `error.type = "delivery_not_redeliverable"`.
- Each item from `GET /api/v1/orgs/{slug}/webhooks` gains
  `"last_delivery": Delivery | null`.
- Auth is the same as webhook management today: `require_user`, then
  `require_org_access(..., allowed_roles=("owner","admin"))`, then
  `require_grant(org, "api_access")`. A delivery is looked up by id **and**
  endpoint **and** org. A delivery that belongs to another org returns 404,
  not 403.

### Wire format (B-core sends it; B-docs documents it)

Every attempt sends these headers:

```
Content-Type:              application/json
X-CertForge-Event-Id:      <delivery id, the same on every attempt>
X-CertForge-Timestamp:     <unix seconds of this attempt>
X-CertForge-Signature-256: t=<timestamp>,v1=<hex HMAC-SHA256(secret, f"{t}.{body}")>
x-certforge-signature:     <hex HMAC-SHA256(secret, body)>   # unchanged, deprecated
```

The body is today's payload plus two top-level keys, `"event"` (already
present) and `"delivery_id"`. It is serialized **once**, stored in
`webhook_deliveries.payload`, and every attempt sends those exact stored
bytes. Receivers should reject timestamps more than 5 minutes old and
deduplicate on the event id.

**The retry schedule** lives in `services/webhooks.py` as
`RETRY_DELAYS_SECONDS = (60, 300, 1800, 7200, 21600, 43200)`. That is 7
attempts in total, and the 7th failure sets the status to `abandoned`. A
`Retry-After` header is honoured when it asks for longer than the next step
in the schedule.

---

## Wave 0: lead, before any agent starts

1. **Claim flag. This is a production change, so confirm with the user
   first.** On 2026-11-11, `fly secrets list` showed both
   `CERTFORGE_CLAIM_SECRET` and `CLAIM_TOKEN_REQUIRED` as already deployed.
   The flag's *value* couldn't be read from this session, so whether
   enforcement is on is still **unverified**. Only the behavioural check below
   can settle it.
   - `fly secrets list -a certforge-api`. `CERTFORGE_CLAIM_SECRET` must
     already be set; production refuses to boot without it.
   - With the user's go-ahead, run
     `fly secrets set CLAIM_TOKEN_REQUIRED=true -a certforge-api`. Setting a
     secret restarts the app.
   - Check the change took effect: claiming an unclaimed test credential with
     no token must return 403 `claim_token_invalid`, and the same request
     with the emailed `?t=` must succeed. Don't count it as verified until a
     no-token claim has actually been refused.
   - Wave 3 moves "Claim link in the delivery email" to Live in
     `apps/web/app/page.tsx`, but **only if this step was verified**.
2. **`.gitignore`**: add `/sports-tournament-handout.pdf`. It is generated by
   `scripts/build_sports_handout.py`. Ask the user whether a copy belongs in
   `docs/samples/` instead.
3. Create `build/2026-11` from `main`.

---

## Wave 1: four agents in parallel

### 1 · B-core (the largest package; give it its own agent)

**May edit:** `apps/api/api/models/api_key.py`,
`apps/api/api/models/__init__.py` (export only),
`apps/api/api/migrations/versions/<new>_add_webhook_deliveries.py`,
`apps/api/api/services/webhooks.py` (new), `apps/api/api/core/worker.py`
(only the webhook block at the end of `_process_batch_sync`, roughly lines
380–420, plus the new task), `apps/api/tests/test_webhook_deliveries.py`
(new).

**Do:** everything under Part B's Decisions B1 and B2.

- Add the `WebhookDelivery` model and its table, with the columns exactly as
  Part B lists them. The migration's `down_revision` is `"b5e2f7a1c9d3"`.
  It needs a working `downgrade()`.
- `_process_batch_sync` inserts one row per active endpoint subscribed to
  `batch.completed`, **in the batch's own transaction**, and makes no HTTP
  call.
- After the batch commits, it defers `deliver_webhook(delivery_id)`. The
  pattern to copy is the way `process_batch` defers `retry_delivery`. A batch
  that rolls back must leave no row and no queued job.
- `deliver_webhook` is a `@worker_app.task(queue="webhooks", retry=False)`.
  Procrastinate's own retry is off because the retry schedule is ours. The
  task makes one attempt with a 10s timeout. Only a 2xx response counts as
  success. It writes the result to the row, then either schedules the next
  attempt with `schedule_in` or marks the row final.
- Retention runs when a new delivery row is inserted: delete rows for the
  same endpoint older than 30 days. There is no timer.
- **Don't** add a periodic sweep or a keep-alive. Part B explains why:
  scale-to-zero is an accepted cost.
- Put the HTTP call behind one function in `services/webhooks.py`, so tests
  can replace it with `httpx.MockTransport` instead of patching `httpx`
  globally.

**Guards.** Each one must be seen failing against the bug named beside it.
Report what you reintroduced and the failing output.

| Guard | Bug to reintroduce |
|---|---|
| A receiver that answers 500 leaves the row `failed`, with `last_status_code=500` and a retry scheduled | Treat any response as success |
| A timeout schedules a retry, and the 7th failure sets `abandoned` with nothing further scheduled | Remove the attempt cap |
| Every attempt sends the same event id and byte-identical bodies | Re-serialize the payload on each attempt |
| `X-CertForge-Signature-256` verifies over `f"{t}.{body}"`, and the legacy header is unchanged | Sign the body alone, or drop the legacy header |
| A batch whose endpoint hangs still completes, and the batch job makes no HTTP call | Move the POST back into `_process_batch_sync` |
| A batch that rolls back leaves no row and queues no job | Defer the job before the commit |
| Rows older than 30 days for an endpoint are gone after the next insert for it | Remove the retention delete |

**Done when:** `cd apps/api && python -m pytest` passes,
`ruff check apps/api/api/` is clean, the migration upgrades and downgrades
on the SQLite test database, and the report lists each guard with the bug
that was reintroduced to watch it fail.

### 3 · B-web

**May edit:** `apps/web/components/dashboard/developer-card.tsx`,
`apps/web/lib/api.ts` (the webhook section only), and a new
`apps/web/lib/webhook-deliveries.ts` with its `.test.ts`.

Read `apps/web/CLAUDE.md` and `AGENTS.md` first.

**Do:** Part B Decision B3, the developer card part, built against the
**Delivery object contract above**. B-api doesn't exist yet, and that's fine
in this wave, because `lib/api.ts` is typed to the contract.

- Each endpoint shows its `last_delivery` as a status tag with the response
  code.
- An expandable list shows recent deliveries, and failed and abandoned ones
  get a Redeliver button. While a redeliver is in flight the button is
  disabled. If it fails, the error appears inline. `next_attempt_at` shows as
  "next try ~in 5 min", with the scale-to-zero caveat in a tooltip.
- Change the copy to "Get told when a CSV batch finishes". Put the copy and
  the status-to-label mapping in `lib/webhook-deliveries.ts`, and have the
  test assert the exact strings. The test must fail if the old "when a
  credential is issued" wording comes back.

**Done when:** `npm run lint`, `npm run typecheck` and `npm test` pass in
`apps/web`.

### 4 · B-docs

**May edit:** `README.md` (a new section only),
`examples/certforge_webhook_receiver.py` (new), and `_build_llms_txt` in
`apps/api/api/index.py`.

`index.py` is **frozen**. `_build_llms_txt`'s body is the only part this
package touches. Change no route, no legacy response, and nothing else in
that file. `test_contract_legacy.py` must still pass.

**Do:** Part B's B-docs, from the **wire format contract above**.

- The README section covers the headers, deduplicating on the event id,
  verifying the signature (a Python snippet), the 5-minute timestamp window,
  the retry schedule, and the caveat that a retry runs late because the API
  scales to zero. It marks `x-certforge-signature` as deprecated.
- The example receiver uses the standard library only. It verifies
  `X-CertForge-Signature-256` with `hmac.compare_digest`, rejects stale
  timestamps, and deduplicates on the event id in memory. Add a small
  self-check under `if __name__ == "__main__"` that signs a sample body and
  verifies it.
- Add the same points to `_build_llms_txt`. Webhook deliveries aren't a
  public URL, so `_build_sitemap_xml` doesn't change.

**Done when:** `python examples/certforge_webhook_receiver.py` runs its
self-check, pytest passes, and ruff is clean.

### 5+6 · Config and docs (one agent; both pieces are small)

**May edit:** `apps/api/api/core/config.py` (one new line),
`apps/api/api/services/vision.py`, `apps/api/tests/test_template_from_image.py`,
`CLAUDE.md`, `docs/billing-and-template-quota-plan.md`,
`docs/dodo-payments-integration-plan.md`, `docs/operator-console-plan.md`,
`docs/operator-quota-overrides-plan.md`, `docs/b1-single-credential-issuance.md`,
`docs/claim-link-and-webhook-retries-plan.md` (the status line only).

**Vision model:**
- Add `VISION_MODEL = _env("VISION_MODEL", "claude-opus-5-5")` to
  `config.py`, and have `vision.py` read it. **Decided on 2026-11-11:** the
  default is `claude-opus-5-5`. The request already uses adaptive thinking,
  explicit `effort: "medium"` and no forced `tool_choice`, so none of Opus
  5.5's breaking changes apply. Keep `effort` explicit, because Opus 5.5's
  default changed. Don't add `fallbacks`: the pinned `anthropic==0.86.0`
  may predate it, and it's a separate change.
- Change the one line in `CLAUDE.md`'s "Reading a design with a model" that
  names the model, so it names the config key instead.
- Add a test that fails if `vision.py` hardcodes a model string again.

**Docs reconciliation.** Correct each statement against the code and `git
log`, and don't rewrite more than that. Each of these was checked on
2026-11-11:

| Where | Says | Actually |
|---|---|---|
| `CLAUDE.md`, the "Where the work is going" bullet on the billing plan | "P1, real Razorpay, has not [landed], so the gate still has no self-serve door" | Self-serve checkout went live through Dodo (#23, #28). The same file says so in "The gate has a self-serve door now" |
| `CLAUDE.md`, the tiers paragraph | "Four tiers — `community`, `starter`, `growth`, `scale`" | Three are real (Community, Pro, Scale), and starter/growth are aliases of `pro` (`TIER_ALIASES`). The template gate line says "Community 1, Pro 5, Scale unlimited". Check those numbers against `BILLING_TIERS` |
| `CLAUDE.md`, "One known pothole" | Says turbo is fixed, then describes the Windows font problem under the same heading | Retitle the heading so it names the problem it now describes |
| `docs/billing-and-template-quota-plan.md` status | "P1 (real Razorpay) has not" | Dodo replaced Razorpay. Point to the Dodo plan |
| `docs/dodo-payments-integration-plan.md` status | "backend in review on `feature/dodo-billing`" | Merged and live. Name the commits |
| `docs/operator-console-plan.md` status | "implemented, not yet deployed" | Shipped in #41, with layout fixes in #42. `deploy-api` runs on `main`, so confirm it deployed with `git log` and the CI history before writing "deployed" |
| `docs/operator-quota-overrides-plan.md` status | W3 built, W4 not started | W3 shipped (#32). W4 is in progress per this plan |
| `docs/b1-single-credential-issuance.md` status | Dated 2026-09-05 | Add a dated line pointing to this plan. It is the doc `CLAUDE.md` calls authoritative, so it must not lag behind |
| `docs/claim-link-and-webhook-retries-plan.md` status | "Part B not started" | "Part B in build, see `docs/build-plan-2026-11.md`" |

Don't add the webhook delivery section to `CLAUDE.md` here. The lead writes
it in Wave 3, once the code exists.

**Done when:** pytest and ruff pass, and every row in the table above is
either fixed or reported back with a reason it wasn't.

---

## Wave 2: two agents in parallel, after B-core is merged into `build/2026-11`

### 2 · B-api

**May edit:** `apps/api/api/routes/developers.py`,
`apps/api/tests/test_webhook_deliveries_api.py` (new).

**Do:** the routes and the `last_delivery` field, **exactly as the contract
above defines them**. Redeliver queues one more `deliver_webhook` with the
same delivery id. It doesn't reset the automatic schedule. Neither route
goes in `llms.txt` or the sitemap.

**Guards:**

| Guard | Bug to reintroduce |
|---|---|
| A member of another org gets 404 on list and on redeliver | Look up the delivery by its id alone |
| Redelivering an `abandoned` delivery queues one attempt with the same event id | Create a new delivery row |
| Redelivering a `succeeded` delivery returns 409 `delivery_not_redeliverable` | Drop the status check |
| A Community org gets 402 `plan_feature_required` | Drop `require_grant` |
| `last_delivery` is the newest row for that endpoint | Order ascending |

**Done when:** pytest and ruff pass and every guard has been seen failing.

### 7 · W4a: stop writing `monthly_quota`

**May edit:** `apps/api/api/services/plans.py`, `apps/api/api/seed.py`,
`apps/api/api/models/organization.py` (the column comment only),
`apps/api/tests/` (only fixtures that pass `monthly_quota=`),
`docs/operator-quota-overrides-plan.md` (the W4 section).

**Why this takes two deploys.** Fly runs `release_command`, which applies
migrations, before the old machines are replaced. If one deploy dropped the
column, the old code still running during the rollover would write to a
column that no longer exists. So this round only stops the writes, and the
drop comes in a later deploy.

**Do:**
- Remove `org.monthly_quota = …` from `plans.py`, both places.
- **No migration.** The column is `nullable=False` but has a Python-side
  `default=` (`organization.py:98`), so inserts that stop setting it still
  succeed. Leave the model column as it is, and change only its comment to
  say that nothing writes or reads it any more.
- Stop `seed.py` from writing the column.
- Don't touch the *tier dictionary key* `"monthly_quota"` in `BILLING_TIERS`,
  the `operator_console.py` SQL, or `lib/api.ts`. Those are the tier's quota,
  not the column, and `/api/v1/tiers` publishes that key.
- Write W4b, the drop migration, as a written-up next step in the overrides
  plan, not as code.

**Guard:** a test that changes an org's tier and asserts `monthly_quota` was
not written. Reintroduce the write and watch the test fail.
`test_operator_console.py`'s parity test must still pass.

---

## Wave 3: the lead integrates

1. Merge in this order: 5+6, 4, 3, 1, 2, 7. Resolve nothing by hand in a file
   whose owner is still running.
2. **Status flips** in `apps/web/app/page.tsx`, `STATUS`:
   - "Webhook delivery retries" moves to Live.
   - "Claim link in the delivery email" moves to Live **only if** Wave 0's
     no-token refusal was observed.
   - Nobody else edits this file.
3. **`CLAUDE.md`**: add a short "Webhook deliveries" section in the house
   style. Cover: a delivery is a row and each attempt is a job; 2xx is the
   only success; the stored bytes are re-sent unchanged; retries run late
   because of scale-to-zero, on purpose; `x-certforge-signature` is
   deprecated but must not change.
4. **Gates.** All of these must pass on `build/2026-11`:
   - `ruff check apps/api/api/ sdk/pdfcert/`
   - `cd apps/api && python -m pytest`
   - `cd apps/web && npm run lint && npm run typecheck && npm test`
   - `npm run build:web`
   - `alembic heads` prints exactly one head
5. **Break-it spot check.** Pick two of the guards that subagents reported
   and reintroduce their bugs yourself. Don't take a "seen failing" claim on
   trust.
6. **Migration on a Neon branch of production** before merging, as the
   operator plan did. This step needs the user's credentials, so ask.
7. **PRs.** One PR per theme, so each can be rolled back on its own:
   - **PR A:** docs, config and `.gitignore` (packages 5+6 plus Wave 0's
     item 2)
   - **PR B:** webhook delivery retries (packages 1–4 plus the status flip)
   - **PR C:** W4a
   - **The claim flip** rides with PR B's `page.tsx` change, or goes in its
     own one-line PR if Wave 0 happened earlier.
8. After deploy, run `scripts/smoke_test.sh`. Then trigger one CSV batch
   against a test endpoint that returns 500, and watch the delivery row
   move from `failed` to a scheduled retry in the dashboard. That end-to-end
   check is the one that tests the join between the two halves.

---

## Brief for every subagent

Paste this into each agent's prompt, followed by its package section:

> You own only the files listed for your package. If the work needs another
> file, stop and report; don't edit it. Read `CLAUDE.md` first. The freeze
> contract applies, and `apps/api/api/index.py` is frozen except where your
> package says otherwise. Don't commit to `main`, push, deploy, or run
> `fly`. Before you finish, run the "Done when" commands and include their
> output. For every guard, reintroduce the named bug, show the test failing,
> revert it, and show it passing. A guard that has never been seen to fail
> doesn't count as done. Report the files you changed, anything you couldn't
> do, and any contract you think is wrong.
