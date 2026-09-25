# TODO · A bulk batch hung at "0 of 1" with no job left to run it

**Opened** 2026-09-24 · **Status** hang CLOSED — fixed, covered by tests and
verified in production 2026-09-24 (#24, Fly v73). **Three follow-ups OPEN**, see
below. · **Trigger** a one-row CSV batch in production, reported from the
dashboard as "Signing batch · 0% · 0 / 1 · 47s", then "hangs indefinitely".

## The finding

Batch `cc2fb037-f56d-4700-bc98-d3479e42e541` (org
`certforge-1787635500301081932`) stayed at `0 / 1` for 90 minutes. The browser
polled `GET …/batches/{id}` every ~3s the whole time, and every poll returned 200.
From the dashboard it looked the same as a batch that was about to start.

Reading the code showed two ways to reach that state, and neither had any
recovery:

1. **Race at upload.** `routes/studio.py` defers `process_batch` *inside* its
   transaction, but Procrastinate commits the job on its own connection and
   NOTIFYs the in-process worker immediately. A worker that read the batch
   before the route's commit landed logged `not found or not pending` and
   **ended the job as a success**. The batch then committed as `pending`, with
   no job left to run it.
2. **Machine replaced mid-batch.** A job running when the machine dies stays
   `doing` under a worker that no longer exists, and its batch stays
   `processing`. Nothing retried stalled jobs, and a retried job would have
   refused a batch that was not `pending`.

**It was (2).** The Fly log shows `Virtual machine exited abruptly` at 15:10:38,
ten seconds after release v72 launched a new machine. When the fix deployed,
its first sweep logged:

```
16:51:05 WARNING Retrying stalled job 22 (batch cc2fb037-…)
16:51:05 WARNING Re-queued stranded batch cc2fb037-…
16:51:05 INFO    Processing batch cc2fb037-…
16:53:06 INFO    Batch cc2fb037-… completed: 1 rendered, 0 failed, 0 delivered, 1 delivery failures.
16:53:06 INFO    Processing batch cc2fb037-…
16:53:06 WARNING Batch cc2fb037-… is completed, not pending; skipping.
```

The last two lines are the duplicate job losing the conditional claim, which is
what the claim is for.

## Why it matters

The dashboard tells the user that the batch "keeps running even if you close
this tab". For this batch that was false, and the screen had no way to show it.
Every deploy that lands while a batch is rendering produces one of these.

## The fix (shipped, #24)

All of it is in `api/core/worker.py`:

- `_process_batch_sync` returns `None` when the batch is not visible yet and `[]`
  when it has already been handled. `process_batch` retries on `None` for up to
  about 10s.
- Batches are claimed with a conditional `UPDATE … WHERE status='pending'`, so a
  duplicate job is harmless.
- `recover_batches` is a once-a-minute Procrastinate periodic task. It retries
  jobs stranded in `doing`, after handing their batch back to `pending`, and
  re-queues batches that have been `pending` for more than
  `STRANDED_BATCH_AFTER_SECONDS` (120).
- A resumed batch starts from its committed counts and processes only the rows
  still `pending`.

The tests are in `tests/test_batch_recovery.py`. Each guard in it was reverted
on purpose, and its test was seen to fail.

## Why the existing tests missed it

Every bulk test patches `process_batch.defer_async` and then calls
`_process_batch_sync` directly, one step after the other. There is no second
connection in that setup, no worker running at the same time and no machine
that can die, so neither the timing gap nor the stall can happen. The race
between two real claims on Postgres is still not covered, because SQLite cannot
exercise it.

## OPEN — 1. One row took two minutes to process

In the recovery run, processing started at 16:51:05 and the send attempt came
back at 16:53:06, so **about two minutes for a single credential**. That long
window is what let a deploy land mid-batch in the first place. Nothing yet
shows which step was slow:

- **The PDF render** on a `shared-cpu-1x` / 512 MB machine. If the template has
  traced artwork, `background_data_uri` (an R2 fetch plus a ~1 MB data URI
  inside xhtml2pdf) is the first suspect.
- **The AgentMail call.** It returned 429, but how long it took to answer has
  not been measured.
- **A cold Neon compute.** The machine had been awake only minutes.

Next step: log how long each stage takes (resolving the background, the render,
the send) inside the per-row loop. A 500-row batch at this rate is about 16
hours.

Related: while that job runs it holds the only worker slot, so
`recover_batches` and `retry_delivery` wait behind it. The sweep's own jobs
queued at 16:52 and 16:53 only started at 16:53:06.

## OPEN — 2. AgentMail daily send limit

The one email in this batch failed with `429 rate_limit_exceeded — Daily send
limit exceeded` (the plan allows 100 a day; the response set
`retry-after: 25614`). `retry_delivery` is deferred at once, with no
`schedule_in`, and is capped at `MAX_DELIVERY_ATTEMPTS` (3). A retry inside the
window only uses up an attempt, so a 429 can exhaust all three within minutes,
and the recipient is never emailed.

Options: upgrade the AgentMail plan (Developer: 1,000 a day, $20 a month),
and/or have `retry_delivery` defer to `Retry-After` on a 429 rather than to
its fixed schedule. Before choosing, check how many of the 100 are being used
by tests or the legacy surface.

## OPEN — 3. The dashboard polls too fast while a batch runs

For the whole time the batch screen was open, the API log showed
`GET …/templates` and `GET …/credentials?limit=1` (each with its CORS
preflight) about **once a second**, on top of the ~3s batch poll. The likely
source is `SetupChecklist`'s `refreshKey`, or a caller that re-renders on every
poll tick. That is roughly 4 requests a second for as long as the tab is open,
and it keeps the Fly machine and Neon awake.

## Related

- `email-delivery-observability.md`: the reason delivery failure is recorded
  on the row and does not fail the batch.
- `CLAUDE.md` › Delivery state, which records the batch-recovery rules.
