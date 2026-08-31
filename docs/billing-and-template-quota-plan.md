# Plan: real Razorpay, an import counter, and re-gating templates

Status: proposed, not started.

## The dependency, stated once

`POST /orgs/{slug}/templates` used to answer 403 for `tier == "community"`.
That gate was deleted (see the docstring in `apps/api/api/routes/templates.py`)
because it made custom templates unreachable for *everyone*: the only route to
a paid tier is `POST /orgs/{slug}/checkout`, which returns a fabricated URL, so
no org could ever satisfy the gate.

So three things have to land, in this order, and shipping any one of them alone
reproduces the failure it is meant to fix:

1. **Checkout and the webhook actually move an org between tiers.** Without
   this a gate is a wall with no door.
2. **A counter exists** that says how much of a tier's template allowance an
   org has used. Without this the gate can only be binary — free/paid — which
   is what made it feel arbitrary, and it leaves the free tier unable to try
   the feature at all.
3. **The gate returns**, expressed against the counter and the tier's limit.

Ship 3 before 1 and the endpoint is unreachable again.

## What is wrong today

Read from `apps/api/api/routes/billing.py`, `api/core/config.py`,
`api/models/usage.py`, `api/routes/templates.py`.

| # | Finding | Why it matters |
|---|---|---|
| B1 | `create_checkout_session` returns `https://rzp.io/i/mock_{org.id}_{tier}`. No SDK, no order or subscription created. | Nobody can pay. Root of the whole chain. |
| B2 | The route depends on `require_user` only. `require_org_access` is imported and never called, so any authenticated user can POST to any org's slug. | Harmless while the response is fake. The moment it creates a real subscription it is a billing hole — someone can start a subscription against an org they do not belong to. |
| B3 | The webhook hardcodes `org.tier = "pro"` and `monthly_quota = 500`. `"pro"` is not a key in `BILLING_TIERS` (`community`, `starter`, `growth`, `scale`). | `get_tier_quota("pro")` silently falls back to Community's 50. A paid org would carry a tier string that config, the gate, and the dashboard all fail to recognise — paid in the `tier` column, free everywhere else. |
| B4 | Only `subscription.activated` is handled. `subscription.cancelled` / `halted` / `completed` / `paused` fall through to `ApiResponse.ok`. | No downgrade path. An org that stops paying keeps its tier and quota forever. |
| B5 | No replay guard. Razorpay retries deliveries; the same event id can arrive many times. | Idempotent today only by accident (a straight overwrite). The first time the handler adjusts a counter or writes an invoice row, it stops being. |
| B6 | `UsageLedger` now carries `vision_imports` (`VISION_IMPORTS_PER_MONTH`, default 10), which meters the "read my design" call because it costs real money. Nothing counts *templates* — an org can hand-author or trace unlimited templates as long as it does not ask the model to read them. | Item 2 of the chain is half-built. `vision_imports` bounds the Anthropic bill, not the product allowance; it is a cost fuse, not a tier gate, and the two must not be conflated. |
| B7 | No `GET /orgs/{slug}/usage`. `apps/web/app/org/[slug]/dashboard/page.tsx:126` carries a comment saying so. | The dashboard cannot show a limit, so a 402 from the gate would arrive with no warning in front of it. |

## The design decision worth arguing about

**A template allowance is a stock, not a flow.** `UsageLedger` is keyed
`(org_id, period)` because credentials are a monthly flow — 50 a month, reset
on the 1st. Templates are not consumed; an org holds N of them indefinitely.

Two options:

- **(a) `usage_ledger.templates_created`, monthly.** Symmetric with the
  existing counter, one place to look. But it answers the wrong question: an
  org with three templates created in January and none in February reads as 0
  used, so the gate lets it create three more. It also drifts — delete a
  template and the counter does not move.
- **(b) Gate on the live row count.** `SELECT count(*) FROM templates WHERE
  org_id = :id`. No new column, nothing to drift, and it is definitionally
  correct: the limit is on how many you *have*. Deleting to make room is
  legitimate, and is already refused for any template with issued credentials
  (`delete_org_template`, 409).

**Recommendation: (b) for the gate, plus (a) for the meter, and be explicit
that they answer different questions.** `templates_imported` in the ledger is a
monotonic record of activity — it feeds the usage endpoint and future billing
analytics; it is never what the 402 reads. If only one gets built, build (b): a
counter that gates on the wrong number is worse than no counter, because it
reports an allowance the product does not enforce.

If you want a single number instead, take (a) alone and drop (b) — but write
down that deleting a template does not give the slot back, because support will
be asked.

## Work packages

Order is the dependency order above. Each lands green.

### P1 — Real Razorpay (`api/routes/billing.py`, `api/core/config.py`, `requirements.txt`)

- Add `razorpay` to `apps/api/requirements.txt`. Add `RAZORPAY_KEY_ID` /
  `RAZORPAY_KEY_SECRET` to `core/config.py` alongside the existing
  `RAZORPAY_SECRET`, read through `_sanitize_env`, **no defaults** — the same
  fail-closed posture the webhook secret already has.
- Add a `plan_id` per paid tier to `BILLING_TIERS`, env-backed
  (`RAZORPAY_PLAN_STARTER`, `..._GROWTH`, `..._SCALE`). Never hardcode a plan
  id.
- `create_checkout_session`:
  - call `require_org_access(principal, str(org.id), allowed_roles=("owner",))`
    — fixes B2; only an owner starts a subscription;
  - reject a `tier` not in `BILLING_TIERS`, and reject `community` (400);
  - create a real subscription through the SDK with
    `notes={"org_id": str(org.id)}` — the webhook already reads
    `notes.org_id`, so that contract stays;
  - return the real short URL. If the SDK is missing or the keys are unset,
    503 — the same way `core/auth.py` refuses rather than degrading.
- Webhook:
  - map `entity["plan_id"]` back to a tier key; an unknown plan id logs and
    returns `ok` without touching the org (never guess a tier — B3);
  - set `org.monthly_quota = get_tier_quota(tier)`, never a literal;
  - handle `subscription.cancelled|completed|halted` → back to `community`
    with Community's quota and `razorpay_sub_id = None` (B4);
  - record `event.id` in a small `billing_events` table and no-op on a repeat
    (B5). Alembic migration required.
- Secrets go on with `flyctl secrets set`, not the dashboard.

### P2 — The counter (`api/models/usage.py`, `api/services/`, migration)

- Alembic migration: `usage_ledger.templates_imported INTEGER NOT NULL DEFAULT
  0`. Backfilling 0 is honest here — unlike `delivery_status`, an uncounted
  past is genuinely zero for metering, and this number never gates anything.
  It sits beside `vision_imports`, which is **not** the same meter and must not
  be reused as one: `vision_imports` is a cost fuse on a paid API call and
  resets monthly; a template allowance is a stock the org holds. Folding them
  together would make "limit reached" mean two different things.
- New `api/services/quota.py`, or extend `services/issuance.py` — but **one
  function, called by every writer**, the same rule `consume_quota` exists to
  enforce. Suggested surface:
  - `template_usage(session, org) -> (limit, used)`, where `used` is the live
    row count and `limit` is `BILLING_TIERS[org.tier]["template_limit"]`;
  - `record_template_import(session, org)` bumps `templates_imported`.
- `GET /orgs/{slug}/usage` returning credentials `{limit, used, period}` and
  templates `{limit, used, imported_this_period}` (B7). It is authenticated, so
  leave it out of `_build_llms_txt` and `_build_sitemap_xml`.

### P3 — The gate returns (`api/routes/templates.py`)

- Add `template_limit` to `BILLING_TIERS`: community **1**, starter 5, growth
  25, scale `-1` (unlimited, reusing the existing sentinel). Community gets
  one, not zero — the whole point is that the free tier can reach the feature.
- In `create_org_template`, after `require_org_access`, call `template_usage`;
  over the limit → **402 Payment Required**, `error.type =
  "template_limit_reached"`, body naming the limit, the current tier, and the
  tiers that would raise it. 402 rather than 403: the caller is not forbidden,
  they are under-provisioned, and the dashboard needs to tell those apart.
- `record_template_import` on success, in the same transaction.
- Replace the "the tier gate is gone" docstring with what the gate now is.
- `POST .../templates/preview` stays ungated — previewing is how you decide to
  buy.

### P4 — Dashboard (`apps/web`)

- Usage tile reads `GET /orgs/{slug}/usage` through `lib/api.ts`; delete the
  stale comment at `dashboard/page.tsx:126`.
- Upgrade button POSTs checkout and redirects to the returned URL.
- The template editor shows `used / limit` and disables Create at the limit, so
  the 402 is a backstop rather than the first signal.
- No `vercel.json` change: everything here is under `/api/v1`, which is already
  rewritten. Confirm that before merging — an unverified assumption about the
  rewrite list is exactly the class of thing this repo has shipped broken.

## Tests

House rule applies: every assertion below gets verified by reintroducing the
bug on purpose and watching it fail.

New `tests/test_billing.py`:

- checkout by a non-member → 403 (fails without the P1 `require_org_access`);
- checkout with keys unset → 503, not a mock URL;
- a webhook with an unknown `plan_id` leaves `tier` untouched — the assertion
  B3 would have caught, and it must fail if the handler goes back to writing
  `"pro"`;
- a tier granted by the webhook sets `monthly_quota == get_tier_quota(tier)`,
  asserted *through* `get_tier_quota`, not against a literal;
- `subscription.cancelled` returns the org to community;
- the same event id delivered twice changes state once.

New `tests/test_template_quota.py`:

- a community org creates its 1st template (201) and its 2nd (402,
  `template_limit_reached`);
- an org on `scale` creates well past any limit;
- deleting an unused template frees the slot;
- `templates_imported` increments on create and does **not** decrement on
  delete.

**The join test — the one that matters.** The failure mode in `CLAUDE.md` is
two correct halves with nothing testing the seam, and this feature has three
seams: webhook → `org.tier` → `BILLING_TIERS` → the gate. One test walks the
whole thing: sign a real `subscription.activated` payload with a configured
secret, POST it, then create templates as that org up to the new tier's limit
and one past it. It must fail if `BILLING_TIERS` gains a tier the webhook
cannot produce, or the webhook produces a tier `BILLING_TIERS` does not know —
which is precisely today's `"pro"`.

Also check whether `test_contract_certforge.py` needs extending; checkout should
not emit a URL any credential or public page depends on, but check rather than
assume.

## Explicitly out of scope

- Invoices, proration, GST, and the legacy tax-invoice surface. Unrelated code
  path, separate decision.
- Changing how credential quota is metered. `consume_quota` is correct and
  stays the single meter.
- Anything on `apps/api/api/index.py`'s legacy surface — the freeze contract is
  untouched by all of this.
