# TODO · Every public CertForge URL 404s on `certforge.intelliforge.tech`

**Opened** 2026-08-27 · **Status** open · **Severity** highest open item — it is baked
into printed QR codes · **Trigger** first production issuance, `CF-2026-XEHQNMFZ`

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

## Related

- [b1-single-credential-issuance.md](../b1-single-credential-issuance.md) — §Production
  smoke test and landmine 8.
- [email-delivery-observability.md](./email-delivery-observability.md) — same run. Note
  the delivery email body links to this same 404 URL, so fixing delivery without fixing
  this just delivers a broken link faster.
