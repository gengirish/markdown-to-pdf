# TODO · Every public CertForge URL 404s on `certforge.intelliforge.tech`

**Opened** 2026-08-27 · **Status** fixed in the working tree, **not yet deployed** ·
**Severity** highest open item — it is baked into printed QR codes · **Trigger** first
production issuance, `CF-2026-XEHQNMFZ`

## The finding

`CERTFORGE_WEB_URL` is what CertForge writes into QR codes, badge documents and issued
credentials. Three of its four public paths do not exist. Probed live, 2026-08-27:

| URL on `certforge.intelliforge.tech` | Live | Written by |
|---|---|---|
| `/verify/{credential_id}` | **404** | `worker.py:146`, `issuance.py:103`, `verify.py:115` |
| `/credentials/{id}/badge.json` | **404** | the badge's own `id` |
| `/orgs/{slug}` | **404** | `verify.py:107` — the Open Badges `issuer.id` |
| `/claim/{credential_id}` | 200 | `apps/web/app/claim/[credential_id]` |

The same paths all answer 200 on `certs.intelliforge.tech`, which is why the smoke test
looked healthy: that URL was typed against the **legacy** host by hand. Nothing a
recipient actually receives points there.

## Why

Two independent gaps, and both have to close.

1. **`apps/web` has no such routes.** It ships `claim/[credential_id]`,
   `org/[slug]/dashboard`, `passport/[username]`, `sign-in`, `sign-up` — and nothing
   else. Note `org/` is singular while the badge issues `/orgs/{slug}`; even once a
   page exists, those two spellings have to be reconciled.
2. **`apps/web/vercel.json` declares no rewrites at all** — just `framework`,
   `buildCommand`. The root `vercel.json` (the legacy project) is the one carrying
   `/verify/:path*` and `/credentials/:path*` through to `certforge-api.fly.dev`, which
   is exactly why the legacy host works and the CertForge host does not.

## What it costs

- **Every CertForge PDF issued so far carries a QR code that resolves to a 404**, and a
  printed one cannot be reissued. This is the same class of mistake the freeze contract
  exists to prevent, on the surface that is not yet frozen — which is the only reason
  it is still cheap.
- **The Open Badges document is not dereferenceable.** `issuer.id` and
  `achievement.id` are URLs a consumer is expected to fetch; both 404. The badge
  validates structurally and fails in use.

## Fix

Pick one, then make it the only one:

- **Rewrite** — add `/verify/:path*`, `/credentials/:path*` and `/orgs/:path*` to
  `apps/web/vercel.json`, pointing at `certforge-api.fly.dev`, mirroring the root
  `vercel.json`. Cheapest, ships today, and the API already renders the verify HTML
  (`routes/verify.py` `public_router`).
- **Native pages** — implement `verify/[credential_id]` in `apps/web` against the v1
  API. Better long-term (it is a product surface, not a redirect), but it duplicates
  the viewer that `verify.py` already renders, and until it exists the QR codes stay
  broken.

Whichever way it goes, also:

- Reconcile `/orgs/{slug}` with the existing `app/org/[slug]/`.
- Add a **live smoke assertion** so this cannot regress silently — a check that every
  URL CertForge writes into a credential resolves on the host it names. The bug
  survived code review precisely because each half looked correct in isolation.

## Do not

Repoint `CERTFORGE_WEB_URL` at `certs.intelliforge.tech` to make it work. That is the
frozen legacy brand, `SITE_URL` is immutable per the freeze contract, and shipping
CertForge credentials under someone else's domain is the bug `worker.py:143-145` was
already fixed once to stop doing.

## Resolution (2026-08-27, undeployed)

**Rewrite** was chosen over native pages. The API already renders the verify viewer,
and every hour spent building a second one is another hour of QR codes pointing at
nothing. Native pages remain worth doing later; they are not worth doing first.

What changed:

| | |
|---|---|
| `apps/web/vercel.json` | gained `rewrites` for `/verify/:path*`, `/credentials/:path*`, `/orgs/:path*` → `certforge-api.fly.dev`. It previously had no `rewrites` key at all. |
| `apps/api/api/routes/verify.py` | new `GET /orgs/{slug}` on `public_router` — the issuer profile, content-negotiated: Open Badges `Profile` JSON-LD for validators, an HTML page for people. |
| `apps/web/proxy.ts` | protected-route matcher anchored from `/org(.*)` to `/org/(.*)`. |
| `apps/api/tests/test_contract_certforge.py` | new, 7 tests. |
| `scripts/smoke_test.sh` | new *CertForge public host* section. |

### The `/orgs` vs `/org` reconciliation

The TODO proposed reconciling the two spellings. They are now deliberately **kept
apart**, because they are not the same thing:

```
/org/{slug}/...   the signed-in dashboard    protected by proxy.ts
/orgs/{slug}      the public issuer profile  anonymous, rewritten to the API
```

Pointing `issuer.id` at the singular form — the cheaper-looking option — could not
have worked. There is no page at `/org/{slug}` (only `/org/{slug}/dashboard`), and
`proxy.ts` protects that namespace, so an Open Badges consumer dereferencing the
issuer would have been answered with a sign-in redirect instead of a Profile.

That same matcher was a live trap for this fix: `/org(.*)` also matches `/orgs/acme`,
because `(.*)` happily accepts the `s`. Adding the rewrite without anchoring the
matcher would have put the new public profile straight behind Clerk.

### The regression guard

Two layers, because the bug needed both halves to be wrong and either alone looked fine.

**Offline** — `tests/test_contract_certforge.py` issues a real credential, reads every
URL off it (`verify_url`, `badge_url`, `issuer.id`, `achievement.id`) and asserts each
one is *served by the API* **and**, when it names `CERTFORGE_WEB_URL`, *carried there
by a rewrite in `apps/web/vercel.json`*. Reading the URLs off a live issuance rather
than a hand-written list means a newly-emitted URL is covered the day it appears.

Verified by breaking each half on purpose, per the freeze-contract file's standard:

- removing the rewrites → `test_every_web_hosted_url_is_rewritten_through_to_the_api`
  fails, reproducing the production bug verbatim
- reverting the matcher to `/org(.*)` → the namespace test fails
- unmounting `/orgs/{slug}` → three tests fail

**Live** — `scripts/smoke_test.sh` gained a section that probes `CERTFORGE_WEB_URL`
directly. This is the gap that let the bug ship: every existing check runs against
`BASE`, which defaults to the **legacy** host, where the rewrites have existed since
`3b52e72`.

Note what it asserts. The first version checked for a 404 and **passed against the
broken production host** — Next.js answers an unrouted path with its own 404, so the
status code cannot distinguish "the API refused this credential" from "the request
never reached the API". Each check now pins a response only the API can produce.
Against production it currently reports:

```
CertForge public host
  FAIL /verify reaches the API, not the app shell
       expected: body containing: Invalid or Revoked Credential
       actual:   <!DOCTYPE html><html data-dpl-id="dpl_9kxJ...
  FAIL badge.json reaches the API, not the app shell
  FAIL the issuer profile reaches the API, not the app shell
```

### What is still open

- **Nothing is deployed.** The three failures above are the live state. `apps/web`
  must ship for the QR codes to resolve.
- The good news the fix carries: because the rewrite serves the *same* URLs already
  printed, **every credential issued so far starts working on deploy**. Nothing needs
  reissuing. That stops being true the moment the paths change.
- `apps/web` has no `node_modules` in this working tree, so `next build` was not run.
  The `proxy.ts` change is a two-element string array; the risk is low but unverified.
- `_build_llms_txt` / `_build_sitemap_xml` were left alone. They describe the legacy
  `SITE_URL` surface and list none of the CertForge public paths — not `/verify`, not
  `badge.json`. Adding `/orgs` alone would be inconsistent; publishing the CertForge
  surface to the agent-discovery documents is its own piece of work.
- Native `apps/web` pages for `/verify` and `/orgs`, replacing the rewrite, remain
  the better long-term shape.


## Related

- [b1-single-credential-issuance.md](../b1-single-credential-issuance.md) — §Production
  smoke test and landmine 8.
- [email-delivery-observability.md](./email-delivery-observability.md) — same run. Note
  the delivery email body links to this same 404 URL, so fixing delivery without fixing
  this just delivers a broken link faster.
