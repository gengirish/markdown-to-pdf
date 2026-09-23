# Plan: let an operator change one organization's credential quota

Status: **W1 and W2 in review (#11), 2026-09-22.** W3 (the page) and W4 (drop
`monthly_quota`) not started. The one open question was decided on 2026-09-22:
a plan change clears the override (Decision 4).

#11 also adds `PUT /operator/orgs/{slug}/tier`, the manual plan change Decision
4 anticipates, and one guard the Tests table below does not list: issuance
checked against a tier default changed after the row was written. The
"`quota_state()` reads `monthly_quota`" bug cannot fail the override →
issuance guard while W1 step 3 keeps that column in sync.

Today the only way to change how many credentials an org may issue is a code
edit to `BILLING_TIERS` and a deploy. It happened twice in two days: Community
went 50 → 500 (`4ded16a`), then back to 50 (PR #8). Each change also needed an
Alembic migration. This plan adds a screen where a CertForge operator can give
one org its own limit, such as 1,000 for a customer who asked. That covers the
usual case without touching the tier table.

Changing a whole tier's limits from the UI is a separate, larger piece of work
and is out of scope (see the end of this doc). This plan is built so that piece
can be added later without redoing this one.

## What is true today

Read from `api/core/config.py`, `api/services/issuance.py`,
`api/routes/billing.py`, `api/routes/orgs.py`, `api/core/principal.py`,
`api/core/auth.py`, `apps/web/proxy.ts`, `apps/web/vercel.json`.

| # | Finding | Why it matters here |
|---|---|---|
| Q1 | `organizations.monthly_quota` is copied from the tier when the org is created. `quota_state()` reads the column and never looks at the tier again. | Changing `BILLING_TIERS` does nothing for existing orgs until a migration rewrites their rows. That is why both recent changes needed one. |
| Q2 | The template limit already works the other way. `get_tier_template_limit(org.tier)` is read on every request, and nothing is stored on the org. | Credentials are the only limit copied into the org's row. Nothing needs that copy. |
| Q3 | The Razorpay webhook sets `org.monthly_quota = get_tier_quota("starter")` whenever it grants a tier. | If an override lived in `monthly_quota`, the org's first upgrade would erase it without any error or log line. |
| Q4 | Every role in `/api/v1` (`owner`, `admin`, `issuer`) belongs to a customer's own organization and comes from `org_members`. Nothing represents CertForge staff. | An "admin" quota control built on those roles would let a customer raise their own limit. |
| Q5 | Legacy `/api/admin/*` uses one shared `X-Admin-Key`, and it falls back to `admin-dev-key` outside production. | A shared key cannot record *who* made a change, and it belongs to the frozen legacy surface. It should not be reused here. |
| Q6 | `apps/web/vercel.json` rewrites `/orgs/*` to Fly, and `proxy.ts` protects only `/org` and `/org/*`. | The operator page cannot live under `/orgs`. Whatever path it uses has to be added to `proxy.ts` on purpose. |
| Q7 | `apps/web` calls the API at its own host (`NEXT_PUBLIC_CERTFORGE_API_URL`), not through a same-origin rewrite. The billing plan's P4 confirmed this. | New `/api/v1` routes need no `vercel.json` change. |

## Decision 1: an override column, with the limit worked out on every request

Add a nullable column `organizations.credential_quota_override`. The limit
issuance enforces becomes:

```python
def effective_credential_quota(org) -> int:
    if org.credential_quota_override is not None:
        return org.credential_quota_override
    return get_tier_quota(org.tier)
```

This function lives in `services/issuance.py`, and `quota_state()` calls it
instead of reading `org.monthly_quota`. It is the only place that decides an
org's limit. The usage endpoint and the operator screen both call it, so the
dashboard cannot show a number that issuance doesn't enforce.

This fixes Q1 as a side effect. An org with no override follows its tier live,
the same way templates already do (Q2). Changing a number in `BILLING_TIERS`
then takes effect on the next deploy with no migration. PR #8's migration would
have been unnecessary under this design.

It also fixes Q3. A tier change no longer rewrites a stored limit behind
anyone's back. What happens to an override on a tier change is now a stated
rule with a log entry (Decision 4), not a side effect of the webhook.

**Alternative considered:** keep `monthly_quota` and add a
`quota_source = 'tier' | 'operator'` flag so tier changes skip overridden rows.
It is a smaller diff, but it leaves Q1 in place, and every future tier change
would still need a migration. Rejected.

**Name:** `credential_quota_override`, not `quota_override`. The template limit
and the vision-import counter are also limits an operator will eventually want
to override. Each should get its own column, so one name can't mean three
units. The same reasoning is behind `UsageLedger.vision_imports` being a
separate counter.

**Wire format:** `-1` means unlimited in the column, as it already does in
`BILLING_TIERS`. It never goes over the wire. The API sends `null` for
unlimited, the same as `_meter()` and `tier_catalog()`.

## Decision 2: operators are an allowlist of Clerk user ids

Add `CERTFORGE_OPERATOR_USER_IDS` to `core/config.py`, a comma-separated list of
Clerk user ids set with `fly secrets set`. Add a dependency:

```python
def require_operator(request) -> Principal:
    principal = require_user(request)          # API keys are refused here
    if principal.clerk_user_id not in OPERATOR_USER_IDS:
        raise HTTPException(403, "Operator access required")
    return principal
```

- **Checked against the verified `sub`, never a claim.** Same rule as
  `require_org_role`. `sub` is the one field `_verify_clerk_token` requires and
  checks.
- **An empty or unset list means nobody is an operator, in every
  environment.** No dev fallback like `ADMIN_KEY`'s `admin-dev-key` (Q5). Tests
  set the list explicitly. This is the same fail-closed rule `auth.py` follows.
- **An API key can never be an operator.** A key belongs to one customer org.
  `require_user` already refuses keys with 403.
- **403, not 404.** The route is visible in the OpenAPI schema anyway, so
  hiding it would protect nothing and make a missing env var harder to debug.

**Alternatives considered:**

- **Clerk `publicMetadata` in a JWT template.** It works, but the role would
  depend on a template setting in the Clerk dashboard, which nothing in this
  repo checks.
- **Clerk `privateMetadata`.** It would need a Clerk Backend API call on every
  request, which adds a network dependency to authorization.
- **The allowlist's cost:** adding an operator takes `fly secrets set` and a
  restart. For a handful of staff that is acceptable, and it keeps the change
  on the CLI.

## Decision 3: every change is recorded, with a reason

Add a new append-only table `credential_quota_changes`:

| column | |
|---|---|
| `id` | UUID PK |
| `org_id` | FK → organizations, `ondelete=CASCADE` |
| `previous_override`, `new_override` | nullable int (NULL = no override) |
| `effective_before`, `effective_after` | int, the result of `effective_credential_quota()` before and after |
| `reason` | text, **required**, at least 10 characters |
| `actor` | who made the change: the operator's Clerk user id (`user_…`), or `razorpay-webhook` when a plan change cleared it (Decision 4) |
| `created_at` | timestamptz |

The row is inserted in the same transaction as the update, so a rolled-back
change leaves no record and a committed change always has one. The reason is
required because the question you'll be asked in six months is "why does
acme get 5,000?". Storing `effective_*` as well as the override means the
history still reads correctly after a tier's default changes.

`actor` is free text rather than a Clerk user id column, because the webhook
is not a user. A plan change that clears an override has to be in this log
too. Otherwise the history would show an override set and never show it
removed, and the only record of why would be a log line that has rolled off.

## Decision 4: a plan change clears the override

**Decided 2026-09-22.** When an org moves to a different tier, any override is
removed and the org follows its new tier's quota. An org given 1,000 on
Community that pays for Growth goes to 2,000, with no one needing to notice.

- **One function changes a tier:** `change_tier(session, org, new_tier, *,
  actor, reason)` in `services/`. The Razorpay webhook calls it, and so does
  any later path that moves an org between plans (cancellation handling, B4 in
  the billing plan; a manual plan change). Nothing else writes `org.tier`, so
  every path follows the same rule.
- **Only a real change clears it.** If `new_tier == org.tier` the function does
  nothing. Razorpay retries deliveries (B5 in the billing plan), and a repeated
  `subscription.activated` for the plan the org already has must not wipe an
  override set since.
- **Downgrades clear it too.** The rule is "the plan changed", not "the plan
  went up", so there is one rule to reason about.
- **It is logged.** `change_tier` writes a `credential_quota_changes` row in the
  same transaction, with actor `razorpay-webhook` and a reason like
  "Plan changed from community to growth". If the org had no override it
  writes no row, because the override didn't change.

**The cost, accepted:** an override set *below* the plan on purpose, for
example to stop abuse, is lifted by the org's next plan change. The operator
panel says this next to the input ("A plan change removes this limit"), and
the log shows when it happened. If that becomes a real problem, the fix is a
separate "hold" flag that `change_tier` respects, not a change to this rule.

**Rejected:** the override wins until an operator removes it. It never changes
a limit without a person, but it leaves a paying customer below their plan
until someone notices, and that failure is silent.

## Endpoints

New file `api/routes/operator.py`, `APIRouter(prefix="/operator")`, mounted
under `/api/v1` in `index.py`. Every route depends on `require_operator`. All
responses use the `ApiResponse` envelope.

| Method | Path | Does |
|---|---|---|
| `GET` | `/operator/orgs?q=&limit=&cursor=` | Lists orgs matching slug or name. For each: `slug`, `name`, `tier`, `tier_quota`, `override`, `effective`, `used` this period. |
| `GET` | `/operator/orgs/{slug}/credential-quota` | One org's current state and its full change history, newest first. |
| `PUT` | `/operator/orgs/{slug}/credential-quota` | `{"limit": int \| null, "reason": str}`. `null` means unlimited. Sets the override. |
| `DELETE` | `/operator/orgs/{slug}/credential-quota` | `{"reason": str}`. Removes the override so the org follows its tier again. |

Validation on `PUT`:
- `limit` is 0 or more, and at most 1,000,000. The cap is there to catch a
  mistyped extra zero, not as a policy. Setting it to exactly the tier's quota
  is allowed but returns a `note` field: an override equal to the tier freezes
  the org at that number even if the tier changes later.
- Setting a limit below what the org has already issued this month is allowed.
  An operator may need to stop an org. The response includes `over_by`, and the
  UI asks for confirmation before sending (see below).

The existing `GET /orgs/{slug}/usage` gets one new field,
`credentials.source: "tier" | "override"`, so the customer's plan card can say
"custom limit" instead of showing 1,000 next to a Community plan that the
pricing page says allows 50.

These endpoints are not public, so they are **not** added to `_build_llms_txt`
or `_build_sitemap_xml`.

## Dashboard

- **Page:** `apps/web/app/operator/page.tsx`. `/operator` is not a customer
  area, and it avoids the `/orgs` rewrite (Q6).
- **`proxy.ts`:** add `"/operator"` and `"/operator/(.*)"` to
  `isProtectedRoute`. This only saves a signed-out visitor from seeing a blank
  page. The actual check is `require_operator` on the API.
- **Content:** a search box and a table with slug, tier, plan limit, override,
  and used/limit. Clicking a row opens a side panel with:
  - a number input and an "Unlimited" checkbox, with the note "A plan change
    removes this limit" beside it (Decision 4)
  - a required reason field
  - "Remove override"
  - the change history

  If the new limit is below this month's usage, the panel asks for
  confirmation, showing the numbers.
- **Not an operator:** the list call returns 403, and the page says exactly
  that. It shows no empty table and no fake data (see `apps/web/CLAUDE.md`,
  "Never fake data"). There is no nav link in this version; operators bookmark
  the URL.
- **`lib/api.ts`:** add `listOperatorOrgs`, `getCredentialQuota`,
  `setCredentialQuota` and `clearCredentialQuota` to `CertForgeClient`, with
  typed responses. They are called through `useCertForge()`.
- **Plan card:** when `credentials.source === "override"`, it shows
  "Custom limit". The pricing page is unchanged.
- Use colour tokens only (`bg-ground`, `text-ink`, …), no literals, per
  `apps/web/CLAUDE.md`.

## Work packages

Each package ships separately and can be rolled back separately.

### W1: The column, the change log, and computing the limit on every request (`models/organization.py`, `models/`, `services/issuance.py`, `services/`, `routes/billing.py`, migration)

1. Migration: add `credential_quota_override` (nullable int). Backfill it from
   `monthly_quota` only where the row **differs from its tier's quota**. Those
   rows were set deliberately (`seed_e2e`'s 10,000, anything set by hand).
   Rows that match get NULL and follow their tier from then on. The tier
   quotas are **written into the migration as literals**, not imported from
   `config.py`, because a migration must behave the same when re-run a year
   from now. Rows with a tier the table doesn't know (the old `"pro"`) are
   compared against Community's 50, the same fallback `get_tier()` uses.
2. `effective_credential_quota()` as in Decision 1; `quota_state()` calls it.
3. **Keep writing `monthly_quota` alongside the override until W4.** Every write
   to the override or the tier also sets
   `monthly_quota = effective_credential_quota(org)`. If this deploy has to be
   rolled back, the old code reads `monthly_quota`, and it needs to be current.
4. The `credential_quota_changes` table (Decision 3) and `change_tier()`
   (Decision 4). The webhook calls `change_tier(..., actor="razorpay-webhook")`
   instead of writing `tier` and `monthly_quota` itself. The table lands here
   rather than in W2 because `change_tier` has to record a cleared override
   from the first deploy. The backfill in step 1 can already create overrides.
5. Test fixtures: the 11 test files that pass `monthly_quota=` to
   `Organization(...)` switch to `credential_quota_override=`. Mechanical, but
   it has to happen in this package or the fixtures test a column nothing reads.

**Before merging:** run the migration against a **Neon branch of production**
and check the backfill with
`SELECT tier, monthly_quota, credential_quota_override, count(*) … GROUP BY 1,2,3`.
The pytest suite builds its schema with `create_all` and never runs Alembic, so
nothing in CI runs this SQL.

### W2: Operators and the endpoints (`core/config.py`, `core/principal.py`, `routes/operator.py`, `index.py`)

Decision 2 and the Endpoints section. The operator endpoints write to the
change log W1 created. Also add `credentials.source`
to the usage endpoint.

**Before deploying:** `fly secrets set CERTFORGE_OPERATOR_USER_IDS=user_…`.
Without it the endpoints return 403 to everyone, which is safe but useless.

### W3: The page (`apps/web`)

The Dashboard section above.

### W4: Drop `monthly_quota` (one release after W3)

Stop writing it and drop the column. This waits a release so that W1–W3 can
still be rolled back.

## Tests

Following the house rule, each guard below must be seen to fail against the
bug it describes before it counts.

| Guard | Bug to reintroduce to see it fail |
|---|---|
| A non-operator user, an API key belonging to the target org's owner, and an empty allowlist all get 403. An allowlisted user gets 200. | Remove the allowlist check, or add a dev fallback. |
| A customer cannot change their own quota by any route: `PATCH /orgs/{slug}` with `credential_quota_override` in the body leaves it unchanged. | Add the field to `OrgUpdate`. |
| **Override → issuance:** set the limit to 2 through `PUT /operator/…`, then issue three credentials. The third returns 402. This connects the operator endpoint to the issuance check; testing either half alone would miss a break between them. | Make `quota_state()` read `monthly_quota`. |
| Removing the override brings back the tier's quota. Monkeypatching `BILLING_TIERS` changes a non-overridden org's limit with no migration. | Same as above. |
| A webhook moving an org from Community to Growth clears its override, the org's limit becomes Growth's, and one change log row is written with actor `razorpay-webhook`. | Have the webhook write `org.tier` directly instead of calling `change_tier()`. |
| A repeated webhook for the tier the org already has leaves the override in place and writes no row. | Drop the `new_tier == org.tier` check. |
| A change log row is written in the same transaction as the update. A rejected request (bad `limit`, missing `reason`) writes neither. | Commit the change log row in a separate session. |
| The usage endpoint reports `source: "override"` and the effective limit. | Have `get_usage` read the tier directly. |
| `/operator` is in `proxy.ts`'s protected list; `/verify`, `/credentials` and `/orgs` are still excluded. | Remove the `/operator` entry. |

Add two read-only checks to `scripts/smoke_test.sh`:
- `GET /api/v1/operator/orgs` without a token returns **401** on the API host.
  A 404 would mean the route wasn't deployed.
- `/operator` on the dashboard host redirects to sign-in rather than
  returning 404.

## Out of scope

- **Editing a tier's limits from the UI.** After W1 this reduces to moving
  `BILLING_TIERS` into a table and pointing `get_tier()` at it, because no org
  stores a copy of its tier's number any more. Existing orgs follow the change
  immediately, which is why W1 comes first. The pricing page already reads
  `GET /api/v1/tiers`.
- **Overriding the template limit and vision imports.** Same pattern, one column
  each (see "Name" under Decision 1).
- **Real billing.** See `docs/billing-and-template-quota-plan.md`.
