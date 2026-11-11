# Operator console plan

Turning `/operator` (certforge.intelliforge.tech/operator) from a database
viewer into an operator console. Two phases; Phase 1 ships first and stops for
review.

Status: **shipped.** Merged to `main` in #41 (`f35bccb`), with layout fixes
from the live check in #42 (`04adc81`); `deploy-api` succeeded on both main
CI runs, so the two migrations (`a7d3e91c0b54`, `b5e2f7a1c9d3`) ran in that
release. See "Follow-up after the live check" at the end.

## What exists today (Step 0 findings)

| Concern | Where |
|---|---|
| Page, tabs, org table | `apps/web/app/operator/page.tsx` |
| Org drawer (override, plan, contacts, history) | `apps/web/components/operator/quota-panel.tsx` |
| Email deliveries tab | `apps/web/components/operator/deliveries-panel.tsx` |
| Typed client methods | `apps/web/lib/api.ts` (`listOperatorOrgs`, `setOrgTier`, …) |
| API routes, all behind `require_operator` | `apps/api/api/routes/operator.py` |
| The only writer of tier and override | `apps/api/api/services/plans.py` |
| Change log model | `apps/api/api/models/quota_change.py` (`credential_quota_changes`) |
| Plan definitions | `BILLING_TIERS` in `apps/api/api/core/config.py` |
| Enforced limit | `effective_credential_quota()` in `apps/api/api/services/issuance.py` |
| Tests | `apps/api/tests/test_operator.py` (pytest); `apps/web/lib/*.test.ts` (`node --test`) |
| Checks | `npm run typecheck`, `npm run lint`, `npm test` in `apps/web`; `ruff check apps/api/api/`; `python -m pytest` in `apps/api` |

Two root causes the UI symptoms trace back to:

- **Scale is missing from the dropdown** because the dropdown is fed by the
  public `GET /api/v1/tiers`, and `tier_catalog()` drops `listed: False` tiers
  on purpose (the pricing page must not sell Scale). An org on Scale therefore
  had no matching `<option>`, and the browser showed the first one —
  Community — as if it were selected.
- **Plan changes are mostly unaudited.** `change_tier()` writes a
  `credential_quota_changes` row only when it clears an override. A plan
  change on an org with no override left a log line and nothing in History.

## Phase 1 — correctness and safety

### API (`apps/api`)

- `GET /api/v1/operator/tiers` — every tier in `BILLING_TIERS`, listed or not,
  in display order, with `listed` on the wire. Operator-only. The public
  catalog is unchanged; Scale still does not appear on the pricing page.
- `change_tier()` writes a change-log row on **every real change**, from any
  actor (operator, Dodo, Razorpay), carrying the tier before and after
  alongside the override and enforced limit before and after. A same-tier
  call is still a no-op that writes nothing.
- Migration `a7d3e91c0b54`: two nullable columns, `previous_tier` and
  `new_tier`, on `credential_quota_changes`. Additive; old rows read as
  override-only changes. No backfill — a past plan change that left no row
  cannot be reconstructed honestly.
- The history wire shape gains `previous_tier` / `new_tier` (null on an
  override-only change).

### Dashboard (`apps/web`)

- `lib/operator.ts` — pure logic, unit-tested in `lib/operator.test.ts`:
  `formatLimit`, `planOptions` (the operator catalog, always containing the
  org's current plan), `describePlanChange` (the before → after diff and the
  override it removes), `isReasonValid`, `parseOperatorParams` /
  `operatorSearch` (URL state).
- **1.1** "Plan limit" and "Override" merged into one **Enforced limit**
  column with an `override` badge. The slug moved out of the row into a
  tooltip on a copy button. Below `lg` the drawer is an overlay sheet; at
  `lg`+ it sits beside a table that now has four columns, which fit at 1280px.
- **1.2** Dropdown built from `GET /operator/tiers` through `planOptions`, so
  Scale appears and the current plan is always the selected option.
- **1.3** "Change plan" opens a native `<dialog>` (focus trap and Esc come
  with it) with the diff, an override-removal warning naming its value, its
  own Reason field, a saving spinner, and an inline error that keeps it open.
  Success closes it and shows a toast. The override form has its own Reason.
- **1.4** Email tab: org filter is its own state, shown as a removable chip,
  settable from a searchable org picker, and named in the empty state. Tab,
  org and status live in the URL (`?tab=emails&org=<slug>&status=failed`).
  Selecting an org on the Plans tab no longer filters emails.
- **1.5** × icon button and Esc close the drawer; "No phone on file" is gone.

### Phase 1 — files touched

| File | Change |
|---|---|
| `apps/api/api/routes/operator.py` | `GET /operator/tiers`; `previous_tier` / `new_tier` on history rows |
| `apps/api/api/services/plans.py` | `change_tier()` logs every real change, with tiers |
| `apps/api/api/models/quota_change.py` | `previous_tier`, `new_tier` columns |
| `apps/api/api/migrations/versions/a7d3e91c0b54_log_plan_changes.py` | new, additive |
| `apps/api/tests/test_operator.py` | 6 new tests (catalog, Scale no-op, plan-change audit, 403) |
| `apps/api/tests/test_billing_dodo.py` | redelivery test counts *new* rows, since the first real change now logs one |
| `apps/web/lib/operator.ts`, `lib/operator.test.ts` | new: pure logic and 13 tests |
| `apps/web/lib/api.ts` | `listOperatorTiers()`, tier fields on `CredentialQuotaChange` |
| `apps/web/app/operator/page.tsx` | URL state, merged column, drawer layout, Esc, toast |
| `apps/web/components/operator/quota-panel.tsx` | split reasons, × button, plan dialog, history copy |
| `apps/web/components/operator/plan-change-dialog.tsx` | new |
| `apps/web/components/operator/org-picker.tsx` | new: combobox |
| `apps/web/components/operator/bits.tsx` | new: icons, spinner, copy-slug tooltip, toast |
| `apps/web/components/operator/deliveries-panel.tsx` | controlled filters, chip, picker, named empty state |

### Phase 1 — verification

- `npm run typecheck`, `npm run lint`, `npm test` (62 pass), `next build`
  (`/operator` still prerenders) in `apps/web`.
- `ruff check apps/api/api/ sdk/pdfcert/`; `python -m pytest` in `apps/api`
  (all pass). Alembic has one head, `a7d3e91c0b54`.
- House rule: both new API guards were seen to fail with their bug restored
  (plan change logged only when it cleared an override; operator catalog
  filtered to `listed`).
- **Not done:** a visual check at 1280px and 768px. `/operator` needs a
  signed-in operator against an API that accepts the session, which the
  local setup does not provide. The 1280px claim is by arithmetic: 1152px
  content − 384px drawer − 24px gap leaves 744px for four `nowrap` columns.


## Phase 2 — console features (shipped)

### API (`apps/api`)

New operator-only endpoints, each behind `require_operator`:

| Endpoint | What |
|---|---|
| `GET /operator/kpis` | Active orgs and credentials issued this month, orgs ≥ 80% of limit, failed emails in 7 days. Four aggregate queries. |
| `GET /operator/orgs` (extended) | `tier` (repeatable), `active`, `near_limit`, `has_override`, `sort` (`usage` default, `name`, `plan`, `limit`, `used`, `last_activity`, `slug`), `dir`, `offset`. Rows gain `usage_percent`, `last_activity_at`, `duplicate_name`; the page gains `total`. `next_cursor` is now an opaque offset. |
| `GET /operator/orgs/{slug}/credential-quota` (extended) | `created_at`, `last_activity_at`, `member_count`, `credentials_all_time`, `usage_percent`. |
| `GET /operator/deliveries` (extended) | `since`, `until`, `sort`, `dir`, `offset`; `counts` per status; rows gain `resendable`, `title_looks_like_email`, `possible_duplicate`. The old keyset `cursor` still works for the default sort. |
| `GET /operator/deliveries/export` | The filtered view as CSV, ≤ 10,000 rows (`X-Export-Truncated`), formula cells defused, `no-store`. |
| `POST /operator/deliveries/{id}/resend` | Requires `Idempotency-Key`. Rate-limited. Through `resend_credential()`. Audited in `operator_actions`. |

- `services/operator_console.py` — all of the above. `effective_limit_sql()` is
  the enforced limit as a SQL expression so usage % sorts and filters in the
  database; a parity test holds it to `effective_credential_quota()`.
- `models/operator_action.py` + migration `b5e2f7a1c9d3` — the resend audit
  and idempotency log: unique `idempotency_key`, and a partial unique index
  allowing one `started` action per credential. The migration also adds
  `idx_credentials_org_issued` for last-activity and date-range reads.
- Resend rule (`resend_refusal()`): a failed send, or a pending/unknown one
  issued over an hour ago; never revoked, test, address-less, or at the
  3-attempt ceiling. A `sent` row is the org's call to resend, not an
  operator's.

### Dashboard (`apps/web`)

- **2.1** `components/operator/kpi-strip.tsx`. Each card applies its filter
  (and toggles off); "Failed emails" opens the Emails tab at
  `status=failed&range=7d`.
- **2.2** `components/operator/org-table.tsx`. Default sort usage % then last
  activity; every header sorts (`aria-sort`); usage bar neutral / amber ≥ 80% /
  red ≥ 100%, none for unlimited; chips for plan (multi), active, near limit,
  has override; Last activity column with an absolute-time tooltip.
- **2.3** Drawer: created, last activity, members, all-time credentials;
  "View this org's emails" and "Email owner" (mailto, owner first); the new
  History empty state.
- **2.4** Emails tab: counts on status options, date range presets plus a
  custom range, sortable headers, Previous/Next paging that keeps the old
  rows on screen while the next page loads, CSV export, and a Resend action
  with a confirmation dialog (`resend-dialog.tsx`).
- **2.5** Read-only badges: "Dup name" (org list), "Title is email" and
  "Possible dup" (emails).
- All filter, sort and page state is in the URL (`lib/operator.ts`
  `parseOperatorParams` / `operatorSearch`); each tab reads only its own.

### Phase 2 — tests

- `apps/api/tests/test_operator_console.py`, 48 tests: SQL/Python limit parity,
  usage %, org sort and every filter, alias-aware plan filter, last activity,
  shared names, drawer facts, KPI deltas, status counts, date range, sorted
  offset paging, the title detector, the duplicate rule, CSV export and
  formula defusing, resend idempotency / audit / in-flight lock / lock release
  / eligibility / refusals / missing key / 404, and **every** operator route
  answering 403 to a non-operator — the route list is read off the app.
- `apps/web/lib/operator.test.ts`: usage % and tone, relative time, date
  presets, header sort toggling, URL round-trips and junk input.
- House rule, each seen to fail with its bug restored: replay removed from
  resend; aliases removed from the SQL limit; `require_operator` removed from
  `/kpis`; CSV defusing removed; a row allowed to match itself as a duplicate.

### Helper script

`scripts/seed_operator_console.py` — seeds a **local** database with `demo-op-`
orgs and `DEMO-OP-` credentials covering every state above (0/50/86/104%,
unlimited, override, shared name, retired plan name; sent / failed / pending
old and new / unknown / not requested; title-is-email; a possible duplicate).
Re-runnable; refuses `ENV=production`.

### Phase 2 — verification

- `npm run typecheck`, `npm run lint`, `npm test` (67 pass), `next build`;
  `ruff check`; full `pytest` (all pass); one Alembic head, `b5e2f7a1c9d3`.
- The seed was run twice against a scratch SQLite database and the console
  queries read it back as expected.

### Deferred, and why

- **The e2e test** (drawer → change plan → confirm → history). Playwright
  here starts the API and the legacy SPA; `apps/web` needs Clerk keys and the
  operator routes need a Clerk-verified session on the allowlist. A harness
  for that (Clerk testing tokens, or a dev-only principal override) is its
  own piece of work and touches auth, so it was not improvised.
- **Screenshots / GIFs, and the 1280px / 768px checks.** Same cause: the page
  cannot be rendered signed-in locally without the Clerk secrets. Layout
  claims are by construction, not observation.
- **Virtualised rows.** Paging was chosen instead: 50 rows a page does not need
  a virtualiser, and paging keeps export and sharing a view simple.

### Known limits

- Last activity is `max(issued_at)` grouped over credentials per request,
  helped by the new `(org_id, issued_at)` index. Fine at today's scale; a
  stored `last_issued_at` on the org is the move if it is not.
- "Failed emails, last 7 days" is keyed on `issued_at`: a failed send records
  no timestamp of its own. Nearly every send happens at issuance.
- Offset paging can shift by a row if credentials are issued between page
  loads. The keyset `cursor` remains for API callers who need stable paging.
- The duplicate rule compares names and emails trimmed and lower-cased; it
  does not normalise Unicode or Gmail dots.

### Follow-up after the live check (8 November)

Checked live in production after #41. Three layout faults that no test could see, fixed:

- **Org names were crushed beside the drawer** ("IntelliForge Learning" rendered as "I."). The name cell was `max-w-0`, so it got only leftover width. It now has a 11rem floor, and Last activity is hidden whenever the drawer is open (the drawer shows it).
- **Resend sat in a column off the table's right edge.** It now sits in the Email cell under the status it acts on. The filter selects had `w-auto` losing to `inputClass`'s `w-full` (no class merging here), so each spanned the page; they use `w-auto!`.
- **A failed row with no Resend button gave no reason.** Rows now carry `resend_refusal`, and failed, pending and unknown rows show it.
