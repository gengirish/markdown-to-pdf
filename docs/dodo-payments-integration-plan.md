# Plan: Dodo Payments as CertForge's billing provider

Status: **backend in review on `feature/dodo-billing`, 2026-09-22.**

| Package | State |
|---|---|
| D0 — preconditions | **Not done.** Needs production access and a Dodo account: the `razorpay_sub_id` count, test-mode products, retries and portal switched on. |
| D1 — schema and config | **Done.** Migration `e3a7c5d9b041` adds the columns and `billing_events`. `razorpay_sub_id` is kept, not dropped, until D0's count is in. `RAZORPAY_SECRET` is removed. |
| D2 — checkout and portal | **Done**, with one change: a paid tier that has no product configured answers **503** (`billing_unavailable`), not 400. It is a server misconfiguration, not a bad request. |
| D3 — webhook | **Done.** `POST /api/v1/webhooks/dodo`. The Razorpay route and its tests are gone. |
| D4 — in-app plan change | Not started. |
| D5 — dashboard and copy | Not started. The "upgrades are handled by hand" copy stays until there is a button to replace it. |
| D6 — launch | Not started. |

Reconciled with the operator quota plan (#11) before review:

- **Tier changes go through `change_tier()`.** `apply_tier()` is gone. A real
  plan change clears an operator's credential override and logs it under
  `dodo-webhook`; a redelivery for the tier the org already holds changes
  nothing. The consequence the old comment wanted — "an org hand-set to
  Starter that then buys Starter should carry exactly what the plan grants" —
  no longer holds for an org with an override: it keeps it, by Decision 4.
- **`e3a7c5d9b041` revises `d9e4b7a2c615`,** not `b2d9f4e610ac`. It had been
  written before `c6a1e85f3d27` landed, and would have given Alembic two heads.
- **Copy from the 500-credit Community era is corrected.** Community is 50
  again (#8), so "Community and Starter share a 500/month quota" was false in
  `config.py`, `CLAUDE.md` and the pricing page. The pricing page no longer
  states a quota as a literal at all.

What building D1–D3 turned up that the plan did not say:

- **The SDK's status enum has `paused` and `past_due`**, which the plan's table
  left out. `past_due` is treated like `on_hold`: the org keeps its paid tier
  while Dodo retries. `paused` is treated as revoking, because a paused
  subscription is not collecting and `subscription.unpaused` brings it back to
  `active`.
- **Verification uses `standardwebhooks` directly.** That is all the SDK's
  `webhooks.unwrap` does, and calling it directly means the webhook needs only
  the webhook key, not the API key. It also has to catch every exception: a
  malformed signature header raises `ValueError`, not the library's own error,
  and that must be a 401, not a 500.
- **Every guard in `tests/test_billing_dodo.py` has been seen to fail.** Ten
  bugs were reintroduced one at a time, and each was caught by the test written
  for it.

This plan **replaces P1 of `docs/billing-and-template-quota-plan.md`** ("real
Razorpay"). P2 (the usage endpoint) and P3 (the template gate) have already
landed, and so have the capability gates in `api/services/entitlements.py`. So
every limit this product sells is enforced now, and nothing can raise one. This
plan is the door in that wall.

Scope: `/api/v1` and `apps/web` only. The legacy surface (`api/index.py`, the
tax-invoice generator, `certs.intelliforge.tech`) is untouched. None of this
comes near the freeze contract.

## Why Dodo, and what it changes compared with the Razorpay plan

- **Dodo is the merchant of record.** It collects and remits GST and other
  taxes, issues the invoices, and handles disputes. Two things we would have had
  to build for Razorpay go away: tax-compliant invoices for CertForge
  subscriptions, and the "Invoices, proration, GST" item the old plan left out of
  scope.
- **Hosted checkout plus a customer portal.** Dodo's portal lets the customer
  update a card, cancel, see invoices and recover an `on_hold` subscription. We
  would otherwise build all of that screen by screen.
- **Standard Webhooks signing** (`webhook-id`, `webhook-timestamp`,
  `webhook-signature`, signed over `id.timestamp.body`). This differs from
  Razorpay's single `X-Razorpay-Signature` HMAC, so the existing handler cannot
  be adapted. It gets replaced.
- **Nothing to migrate.** `organizations.razorpay_sub_id` is only ever written
  by a webhook, and that webhook has no configured secret or plan ids. Confirm
  this before dropping the column (step 0 below). Do not assume it.

## What is wrong today

Carried over from the billing plan's findings. These are still open, whichever
provider we use:

| # | Finding | Where this plan fixes it |
|---|---|---|
| B1 | `create_checkout_session` returns `https://rzp.io/i/mock_{org.id}_{tier}`. Nobody can pay. | D2 |
| B2 | Checkout depends on `require_user` only. `require_org_access` is imported and never called. Once checkout is real, anyone signed in can start a subscription against any org's slug. | D2 |
| B3 | The webhook writes `tier = "starter"` for every activation, because there is no plan or product id to map from. | D3 |
| B4 | Only activation is handled. An org that stops paying keeps its tier forever. | D3 |
| B5 | There is no replay guard. | D3 |

## Design decisions

The rest of the plan follows from these. Each one comes with its reason, so it
can be argued with.

### 1. Entitlement is derived from subscription *state*, never from event type

Dodo guarantees **no ordering** between webhooks. It also delivers the **latest
resource state at delivery time**. So the handler should not be written as "on
`subscription.active` grant; on `subscription.expired` revoke". Written that
way, a retried `active` that arrives after an `expired` re-grants a dead
subscription.

Instead, every subscription event runs one function:

```
reconcile(org, subscription_payload) -> tier
```

It reads `status`, `product_id` and `cancel_at_next_billing_date` off the
payload and computes the tier from scratch:

| Subscription status | Tier the org gets |
|---|---|
| `active` | `tier_for_product(product_id)` |
| `on_hold` | Stays on the paid tier, as a grace period. Dodo retries renewals for up to ~13 days, and the dashboard shows a "payment failed" banner with a portal link. |
| `cancelled` + `cancel_at_next_billing_date` | Stays on the paid tier until `next_billing_date`. The later `expired` event does the downgrade. |
| `cancelled` (immediate), `expired`, `failed` | `community` |
| `pending` | No change |

The event type is only recorded for the audit log. It never decides what the
org gets.

### 2. Only the org's *current* subscription can move it

`organizations.dodo_subscription_id` names the one subscription that governs the
org. An event for any other subscription id is recorded and then ignored.
Without this rule, an org that cancels, resubscribes, and then receives the
**old** subscription's `expired` event gets downgraded while paying. That is the
out-of-order case, and it is the most likely way this feature breaks in
production.

A new subscription becomes current only when it arrives `active` for an org
whose current subscription is empty or terminal. If a second `active`
subscription turns up for an org that already has a live one (a double checkout
from two tabs), record it, log at ERROR and leave the current one in place. Do
not cancel it automatically. Refunding a customer is a decision a person
should make.

### 3. Orgs moved by hand are never touched by a webhook

Support has been upgrading orgs by hand, because until now there was no other
way. Those orgs have `dodo_subscription_id IS NULL`, so decision 2 already
excludes them from every webhook. Write that down as intended behaviour rather
than leaving it as a side effect. A hand-granted org that later subscribes
simply becomes Dodo-governed.

### 4. Product ids live in env, keyed off `BILLING_TIERS`

`BILLING_TIERS` stays the only definition of a plan. Each paid tier gets a
product id read from env: `DODO_PRODUCT_STARTER`, `DODO_PRODUCT_GROWTH` and
`DODO_PRODUCT_SCALE`. Test mode and live mode have different ids, so a checked-in
literal would be wrong in one of them. Two helpers in `core/config.py`:

- `product_for_tier(tier) -> str | None`
- `tier_for_product(product_id) -> str | None`

`None` from `tier_for_product` means **unknown product**. The handler logs it,
records the event, answers 200 and does not touch the org. It must never guess
a tier. A guess is exactly B3.

### 5. The price is defined once and checked against Dodo, not copied into it

`price_paise` in `BILLING_TIERS` is what the pricing page prints. The Dodo
product's price is what the customer is charged. These are two copies of one
number, which is how drift happens in this codebase.
`scripts/check_dodo_catalog.py` fetches each configured product and fails if its
price, currency or billing interval disagrees with the table. It is not a CI job,
because it needs live keys. Run it before launch and after any change to either
side, the same way `scripts/smoke_test.sh` is run.

**Open question for the owner:** is `price_paise` GST-inclusive? As merchant of
record, Dodo adds tax at checkout unless the product is set to tax-inclusive
pricing. Either way works, but the pricing page must state which one applies.

### 6. The webhook is processed synchronously, in one transaction

Dodo's pattern is: verify, then enqueue, then answer 2xx. That is for handlers
doing slow work. Ours writes one `billing_events` row and a few columns on one
`organizations` row, well inside Dodo's 15-second timeout. So:

1. `client.webhooks.unwrap(raw_body, headers=...)`. On failure → **401**.
2. Open a transaction. Insert `billing_events(webhook_id UNIQUE, …)`. If the
   insert conflicts, the event is a duplicate → commit and answer 200.
3. `reconcile(...)` inside **the same transaction**.
4. Commit and answer 200. Any exception → **500**, so the claim rolls back with
   the change and Dodo's retry can process the event again.

Putting the claim and the entitlement in one transaction is what makes a retry
safe. If the claim commits first and the change fails, the event is lost for
good, because every retry sees the claim and skips.

Moving this onto Procrastinate is for later, and only if the handler gains slow
work (sending email, for example). If it does, send through an outbox, not
inline.

### 7. The webhook points at the API host, not through Vercel

Register `https://api.certforge.intelliforge.tech/api/v1/webhooks/dodo`. That
host goes straight to Fly (see the host table in `CLAUDE.md`), so **no
`vercel.json` change is needed**, and the endpoint's availability does not
depend on the frontend's routing. It is authenticated by signature, so it stays
out of `_build_llms_txt` and `_build_sitemap_xml`.

### 8. Access is granted by the webhook, never by `return_url`

The return URL is `CERTFORGE_WEB_URL/org/{slug}/dashboard?checkout=complete`.
That page polls `GET /orgs/{slug}/usage` until `tier` changes, with a timeout
and "this can take a minute" copy. It never grants anything itself. The browser
reaches the return URL before Dodo has necessarily finished the mandate.

## Work packages

Dependency order. Each package lands green, and each guard in its tests is seen
to fail at least once, per the house rule.

### D0 — Preconditions (no code)

- `flyctl ssh console -a certforge-api` → `SELECT count(*) FROM organizations
  WHERE razorpay_sub_id IS NOT NULL;`. If the count is not 0, stop and write a
  migration plan for those rows before D1 drops the column.
- Create the Dodo business, and in test mode, three subscription products
  (monthly) whose prices match `BILLING_TIERS`. Create them from a checked-in
  script (`scripts/dodo_seed_products.py`, using the SDK), not by clicking
  through the dashboard. That keeps the catalogue reproducible for live mode.
- Enable Payment Retries (Settings → Recovery) and the customer portal. Decision
  1's `on_hold` grace period assumes retries are on.

### D1 — Schema and config (`models/organization.py`, `models/billing_event.py`, `core/config.py`, migration)

- Add columns to `organizations`, all nullable:
  - `dodo_customer_id`
  - `dodo_subscription_id` (indexed; the governing subscription from decision 2)
  - `subscription_status`
  - `current_period_end`
  - `cancel_at_period_end` (boolean, default false)
- Drop `razorpay_sub_id`, gated on D0.
- Add a `billing_events` table: `id`, `webhook_id` UNIQUE, `event_type`,
  `subscription_id`, `org_id` (nullable, since an unknown org is still worth
  recording), `outcome` (`applied` | `ignored_unknown_product` |
  `ignored_not_current` | `ignored_unknown_org` | …), `received_at`. The
  `outcome` column exists for the same reason `delivery_status` does:
  **ignoring an event is a recorded outcome, not an absence.** "Why didn't my
  upgrade apply?" must be answerable from the database after the logs have
  rolled off.
- Add `dodopayments` to `requirements.txt`. Pin the version, because the
  webhook's `unwrap` needs its `standardwebhooks` dependency.
- Add these to `core/config.py` through `_sanitize_env`, **with no defaults**:
  - `DODO_PAYMENTS_API_KEY`
  - `DODO_PAYMENTS_WEBHOOK_KEY`
  - `DODO_PAYMENTS_ENVIRONMENT`, narrowed to `live_mode` / `test_mode` and
    defaulting to `test_mode`, so that a typo can never charge real cards
  - the three product ids
- Add `product_for_tier` / `tier_for_product`.
- Delete `RAZORPAY_SECRET` and its boot warning.

### D2 — Checkout and portal (`routes/billing.py`, new `services/billing.py`)

`services/billing.py` is the only module that builds a Dodo client, the same
rule as `services/vision.py` for Anthropic. If the key is unset it raises, and
the route turns that into **503**, never into a mock URL.

`POST /orgs/{slug}/checkout {tier}`:

- `require_org_access(principal, org_id, allowed_roles=("owner",))`. This fixes
  B2.
- Answer **400** for a tier not in `BILLING_TIERS`, for `community`, or for a
  tier with no configured product.
- Answer **409** `already_subscribed` when the org has a live subscription. A
  plan change on an existing subscription goes through D4 or the portal, never
  through a second checkout.
- `checkout_sessions.create` with:
  - `product_cart=[{product_id, quantity: 1}]`
  - `customer` set to the org's stored `dodo_customer_id` if it has one,
    otherwise the owner's email and name
  - `metadata={"org_id": str(org.id), "tier": tier}`
  - `return_url` from decision 8
- Return `{checkout_url, tier}`, the same shape as today, so `lib/api.ts` does
  not change its type.
- **To verify in test mode, before building on it:** that checkout `metadata`
  carries through to the subscription payload in webhooks. If it does not,
  capture the subscription id on the session and map it back to the org there.

`POST /orgs/{slug}/billing/portal`:

- Owner only.
- Answers **409** when the org has no `dodo_customer_id`.
- Returns `customers.customer_portal.create(customer_id, return_url=...)`.
  Portal links expire after 24 hours, so create one per click and never store
  it.

### D3 — The webhook (`routes/billing.py` → `POST /api/v1/webhooks/dodo`)

- Implement decision 6's transaction and decision 1's `reconcile`.
- The org is resolved by `metadata.org_id`, then by `dodo_subscription_id`.
- **Tier changes go through one function.** `apply_tier(session, org, tier)`
  sets `org.tier` and `org.monthly_quota = get_tier_quota(tier)`, never a
  literal. It lives beside `consume_quota` and is the only writer of `tier`
  outside the admin path.
- On `active`, store `dodo_customer_id` so the portal and later checkouts reuse
  it.
- Subscribe to these events only: `subscription.active`, `.renewed`,
  `.on_hold`, `.plan_changed`, `.cancelled`, `.expired`, `.failed` and
  `.updated`. Payment events are not needed for entitlements. Refunds and
  disputes go to a log line for now.
- `plan_changed` also fires when `cancel_at_next_billing_date` is toggled. That
  is harmless here, because `reconcile` reads state and not the event name. This
  is the second reason decision 1 exists.
- Delete `POST /webhooks/razorpay` and its four tests in `test_security.py`.
  Their Dodo equivalents are listed below.

**What a downgrade does and does not take away.** This is already how the gates
behave. The webhook only has to leave it that way:

- `monthly_quota` drops to Community's immediately.
- Templates above the new limit are **kept and keep rendering**. The limit
  stops the org creating new ones.
- Artwork keeps rendering, and existing API keys keep working, because
  entitlements are checked where a capability is acquired, never where it is
  used.

Put this in the pricing page copy, because a customer will ask about it.

### D4 — In-app plan change (can ship after D5)

- `POST /orgs/{slug}/billing/change-plan {tier}`, owner only, calling
  `subscriptions.change_plan` with:
  - `proration_billing_mode="prorated_immediately"`
  - `on_payment_failure="prevent_change"`, so a failed upgrade charge leaves
    the old plan intact instead of putting the org `on_hold`
- A preview endpoint wraps `preview_change_plan`, so the dashboard can show the
  charge before the owner confirms.
- The response does **not** change the tier. The `plan_changed` webhook does,
  through `reconcile`, as with every other change.
- Until D4 lands, a plan change goes through the portal (enable plan switching
  on a Product Collection there).

### D5 — Dashboard and copy (`apps/web`, the 402 bodies)

Read `apps/web/CLAUDE.md` and `AGENTS.md` first.

- `plan-card.tsx`:
  - an upgrade button that calls checkout and redirects
  - "Manage billing" (portal) once the org has a customer
  - an `on_hold` banner
  - "Cancels on {date}" when `cancel_at_period_end` is set
- `GET /orgs/{slug}/usage` gains `subscription: {status, current_period_end,
  cancel_at_period_end}` so the card has something to render.
- `pricing/page.tsx`: replace the "How an upgrade works today" note with real
  buttons for a signed-in owner. The page stays on-demand (`connection()`).
- Delete every "upgrades are handled by hand" string. There are six places:
  - `pricing/page.tsx`
  - `plan-card.tsx`
  - `routes/templates.py`
  - `services/entitlements.py`
  - `apps/web/CLAUDE.md`
  - the homepage roadmap item in `app/page.tsx`

  The tests that assert on those 402 bodies (`test_template_quota.py`,
  `test_entitlements.py`) change with them.
- Update `CLAUDE.md`: its "Tiers" section and the billing-plan line in "Where
  the work is going".

### D6 — Launch

- Put the live keys and live product ids on Fly with `flyctl secrets set`.
  Change `DODO_PAYMENTS_ENVIRONMENT` to `live_mode` last.
- Run `scripts/dodo_seed_products.py` against live mode, then
  `scripts/check_dodo_catalog.py`.
- Register the live webhook, send a test event from Dodo's endpoint testing
  tool, and confirm it lands in `billing_events` with `outcome = applied` or a
  reasoned `ignored_*`.
- Make one real purchase on Starter from a real card, cancel it, refund it, and
  watch the org go community → starter → (at period end) community.

## Tests

New `tests/test_billing_dodo.py`. Webhooks are signed with a real test key in
Standard Webhooks format (`whsec_…`, `v1,<base64 hmac of id.ts.body>`), so the
handler's own `unwrap` is exercised rather than patched out. The Dodo client for
checkout and portal is faked at the `services/billing.py` boundary.

Each item below names the bug it must fail against.

**Signing**

- A bad signature → 401.
- An unset webhook key → 503.
- A body re-serialized after signing → 401. This fails if the handler starts
  parsing JSON before it verifies.

**Idempotency**

- The same `webhook-id` delivered twice changes state once.
- A handler that raises after the claim leaves **no** `billing_events` row. This
  fails if the claim is committed separately from the change.

**Ordering**

- `expired` for sub A arrives after `active` for sub B, on the same org → the
  org stays paid. This fails without decision 2.
- A retried `active` for an expired subscription → no re-grant.

**Mapping**

- An unknown `product_id` → tier unchanged, `outcome =
  ignored_unknown_product`, 200. This fails if the handler falls back to a
  default tier.
- `monthly_quota == get_tier_quota(tier)` for every paid tier, asserted through
  the helper and never against a literal.

**Lifecycle**

- `on_hold` keeps the paid tier.
- Cancel at period end keeps it until `expired`.
- An immediate cancel and `failed` both return the org to community.

**Hand-granted orgs**

- An org with no `dodo_subscription_id` is untouched by any event.

**Checkout**

- A non-member → 403. An admin who is not the owner → 403.
- The API key unset → 503, and the response contains no URL.
- Checkout while subscribed → 409.
- `metadata.org_id` is the org's id.

**The join test.** This feature has four seams:

> Dodo product → `tier_for_product` → `BILLING_TIERS` → the gates

One test walks all of them. For **every** paid tier in `BILLING_TIERS`:

1. Configure a product id.
2. Deliver a signed `subscription.active` for it.
3. As that org, create templates up to the tier's limit, plus one more.
4. Assert 201s and then exactly one 402.

It must fail if a tier gains no product mapping, or if the webhook can produce a
tier the table does not know. Iterating the table rather than a hand-written
list covers a fifth tier the day someone adds it. That is the same move
`test_contract_certforge.py` makes with URLs.

## Risks and open questions

1. **GST-inclusive or exclusive pricing** (decision 5). The owner has to decide
   this before products are created.
2. **Does checkout metadata reach the subscription payload?** Verify in test
   mode in D2. There is a stated fallback.
3. **Annual plans and trials.** Neither is in `BILLING_TIERS` today. Adding
   annual plans means a product per tier per interval, so `tier_for_product`
   maps many product ids to one tier. The helper is shaped for that, but do not
   add annual plans in this pass.
4. **International customers.** Dodo can price in other currencies. The catalog
   endpoint hardcodes `"currency": "INR"`. Keep INR only until there is demand.
5. **Double subscription** (decision 2). Handled by logging, not automatically.
   Watch `billing_events` for it after launch.

## Explicitly out of scope

- The legacy tax-invoice generator (`POST /api/invoice`). It is a product
  feature for our customers, not our own billing. It is unrelated and frozen.
- Usage-based or credit-based billing (charging per credential). Quota stays a
  monthly allowance metered by `consume_quota`.
- Moving `/api/v1` API-key customers to Dodo license keys.
