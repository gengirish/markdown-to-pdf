# TODO · `api.certforge.intelliforge.tech` does not exist

**Opened** 2026-08-27 · **Status** open · **Severity** medium — it is in every
credential handed to an API caller, but not in anything printed · **Trigger**
post-deploy verification of the delivery-observability change

## The finding

`CERTFORGE_API_URL` names a host that has never been created. Probed live,
2026-08-27:

| Check | Result |
|---|---|
| `nslookup … 8.8.8.8` | **NXDOMAIN** |
| `nslookup … 1.1.1.1` | **NXDOMAIN** |
| `curl https://api.certforge.intelliforge.tech/api/health` | **000** — connection never happens |
| `flyctl certs list -a certforge-api` | **empty** — no certificates at all |

It is not a slow host or an expired certificate. The hostname was never set up,
on either side: no DNS record anywhere, and no Fly certificate to serve it if
there were.

For comparison, on the same run:

```
https://certforge-api.fly.dev/api/health    200  {"status":"healthy",…}
https://certs.intelliforge.tech/api/health  200  {"status":"healthy",…}
```

## Why it matters

`apps/api/api/core/config.py:112` defaults `CERTFORGE_API_URL` to this host, and
`fly.toml` does not override it — its `[env]` block sets `SITE_URL` but not this.
So the default is what production runs with, and
`apps/api/api/services/issuance.py:116` writes it into the `badge_url` of **every
credential the API issues**:

```json
"badge_url": "https://api.certforge.intelliforge.tech/credentials/CF-2026-…/badge.json"
```

That URL cannot be fetched by anyone.

## What it does *not* affect

Worth stating, because the blast radius is much smaller than the 404 incident
this resembles:

- **Nothing printed.** QR codes are built from `CERTFORGE_WEB_URL`, which
  resolves correctly since `c92b8fb`. No certificate on paper points here.
- **Not the dashboard.** `NEXT_PUBLIC_CERTFORGE_API_URL` is set in Vercel
  Production to `https://certs.intelliforge.tech`, a working host. Only
  `apps/web/.env.example` still documents the dead host as the default, which is
  misleading to anyone setting up local dev but breaks nothing deployed.
- **Not the badge document's contents.** `issuer.id` and `achievement.id` inside
  `badge.json` use `CERTFORGE_WEB_URL` and dereference correctly. It is the
  `badge_url` *field* — the pointer handed to the caller — that is dead.

So: an API-facing defect, not a credential-integrity one.

## Fix

Two options, and they are not equivalent.

- **Create the hostname.** A DNS record plus
  `flyctl certs add api.certforge.intelliforge.tech`. This is what the code was
  designed for — `config.py:106-110` says the host exists precisely so customers
  get an API host that "does not depend on the frontend's routing." Needs DNS
  access at the registrar / Vercel.
- **Repoint** `CERTFORGE_API_URL` in `fly.toml` to `https://certs.intelliforge.tech`,
  matching what the dashboard already uses. One line, ships on the next deploy —
  but it bakes the frontend dependency into every credential issued from then on,
  which is the thing the separate host was introduced to avoid.

Creating the hostname is the better end state. Repointing is the faster stopgap
and is reversible; note that credentials issued in between carry whichever URL
was live at the time, and `badge_url` is stored nowhere — it is computed per
request from config — so changing it later fixes old credentials too. That is
the one mercy here, and it is why this is medium rather than high.

Whichever way it goes, also update `apps/web/.env.example`.

## The guard

`scripts/smoke_test.sh` gained a *CertForge API host* section that probes this
host directly and currently fails:

```
CertForge API host
  FAIL the API host resolves
       expected: a reachable host
       actual:   connection failed (no DNS/TLS) for https://api.certforge.intelliforge.tech
  FAIL badge.json is reachable on the API host
```

It distinguishes curl's `000` — no DNS, no TLS, no route — from an ordinary
non-200, because a plain status check reads the former as merely "not 200" and
says nothing about why.

**These two failures are expected until this TODO is closed.** The smoke script
is not run by CI (`.github/workflows/ci.yml` has no such job), so nothing is
gated on them; they are there so the next person who runs it against production
sees this rather than rediscovering it.

## Why the existing tests missed it

`apps/api/tests/test_contract_certforge.py` was written for exactly this class of
bug — a URL written into a credential that resolves nowhere — and it passes.
It asserts two things about every credential URL:

1. the **path** is served by the API, and
2. when the host is `CERTFORGE_WEB_URL`, a rewrite in `apps/web/vercel.json`
   carries it there.

`api.certforge…/credentials/{id}/badge.json` satisfies both. The path *is*
served; the host is not `CERTFORGE_WEB_URL` so check 2 skips it. Nothing asserted
that the host itself exists — an offline test cannot resolve DNS, which is why
the guard above is live rather than in pytest.

If this is fixed by creating the hostname, consider whether the offline test
should additionally assert that every host a credential URL can name appears in
a small allowlist that someone has to consciously edit.

## Related

- [certforge-public-urls-404.md](./certforge-public-urls-404.md) — the same class
  of defect on `CERTFORGE_WEB_URL`, closed 2026-08-27. That one was in printed QR
  codes; this one is not, which is the whole difference in severity.
- `apps/api/api/core/config.py:95-112` — the three-host split and why each exists.
