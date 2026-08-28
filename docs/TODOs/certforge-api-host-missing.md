# TODO · `api.certforge.intelliforge.tech` does not exist

**Opened** 2026-08-27 · **Status** CLOSED — verified in production 2026-08-28 ·
**Severity** medium — it is in every
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

This was filed as a choice between creating the hostname and repointing
`CERTFORGE_API_URL`. That overstated it: **the plan already decided**, at §3 of
[api-first-optimization-plan.md](../api-first-optimization-plan.md), which gives
the records and the `fly certs add`. The host exists precisely so customers get
an API host that "does not depend on the frontend's routing"
(`config.py:106-110`), and repointing it at `certs.intelliforge.tech` would bake
that dependency into every credential issued from then on.

### Step 1 — Fly certificate · DONE 2026-08-28

```
$ fly certs add api.certforge.intelliforge.tech -a certforge-api
✓ Certificate created for api.certforge.intelliforge.tech
$ fly certs check api.certforge.intelliforge.tech -a certforge-api
  Status = Not verified
! No AAAA records were found for your domain
```

### Step 2 — DNS · DONE 2026-08-28

DNS for `intelliforge.tech` is at **GoDaddy** (`ns11`/`ns12.domaincontrol.com`),
not Vercel — the Vercel account holds no domains, so this cannot be done with
`vercel dns`. Add one record in GoDaddy's DNS manager:

| Field | Value |
|---|---|
| Type | `CNAME` |
| Name | `api.certforge` |
| Value | `leqpek9.certforge-api.fly.dev` |
| TTL | `600` |

Two things to get right, both of which the old instructions got wrong:

- **Name is relative to the zone.** `api.certforge`, not the full hostname —
  GoDaddy appends `intelliforge.tech` and you would otherwise create
  `api.certforge.intelliforge.tech.intelliforge.tech`.
- **The target carries a per-app prefix.** `leqpek9.certforge-api.fly.dev`, not
  the bare `certforge-api.fly.dev` that the plan and the handover doc both named
  until 2026-08-28. The bare host does not validate the certificate. Print the
  live values with `fly certs setup api.certforge.intelliforge.tech -a certforge-api`
  rather than trusting any document, including this one.

A + AAAA works too — `66.241.125.183` and `2a09:8280:1::163:aa09:0` — but needs
**both**: the IPv4 is shared, so Fly verifies ownership through the AAAA, and an
A record alone leaves the certificate stuck at `Not verified`. That is exactly
what `certs check` is reporting now.

### Step 3 — verify · DONE 2026-08-28

The CNAME was taken, not A/AAAA:

```
$ nslookup api.certforge.intelliforge.tech 8.8.8.8
Name:    leqpek9.certforge-api.fly.dev
Addresses:  2a09:8280:1::163:aa09:0
            66.241.125.183
Aliases:  api.certforge.intelliforge.tech

$ fly certs check api.certforge.intelliforge.tech -a certforge-api
  Status = Issued · Let's Encrypt · rsa,ecdsa
  ✓ Certificate is verified and active

$ curl https://api.certforge.intelliforge.tech/api/health
{"status":"healthy",…,"dependencies":{"database":"connected","email":"ready"}}

$ bash scripts/smoke_test.sh
25 passed, 0 failed
```

And the thing that actually matters — the `badge_url` of the credential from the
original incident, fetched at exactly the URL the API had been handing out:

```
$ curl https://api.certforge.intelliforge.tech/credentials/CF-2026-XEHQNMFZ/badge.json
200 application/json
{"@context":[…],"id":"urn:uuid:CF-2026-XEHQNMFZ","type":["VerifiableCredential",
 "OpenBadgeCredential"],"issuer":{"id":"https://certforge.intelliforge.tech/orgs/…"}}
```

No code change and no redeploy was needed: `CERTFORGE_API_URL` already defaulted
to this hostname, which is why it broke in the first place. Every credential ever
issued carries a `badge_url` that now resolves, because the field is computed per
request rather than stored.

`apps/web/.env.example` was corrected in the same pass — it had named the dead
host as the local-dev default, handing a new contributor a dashboard that could
not reach the API. The working host is uncommented and this one is available
alongside it.

## The guard

`scripts/smoke_test.sh` gained a *CertForge API host* section that probes this
host directly. It failed from the moment it was written until the DNS record
landed, which is the whole reason it was written that way:

```
CertForge API host
  PASS the API host resolves and is healthy
  PASS badge.json is reachable on the API host
```

It distinguishes curl's `000` — no DNS, no TLS, no route — from an ordinary
non-200, because a plain status check reads the former as merely "not 200" and
says nothing about why. If this regresses — a certificate expiry, a deleted
record — those two lines say so in the words of the failure.

The script is not a CI job (`.github/workflows/ci.yml` has none), so it gates
nothing automatically. Run it after any deploy that touches hosts.

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

That suggested an allowlist of permitted hosts in the offline test. On reflection
it would not have helped: `CERTFORGE_API_URL` **was** one of the three sanctioned
constants, so an allowlist check would have passed throughout. The gap was never
which host was named — it was whether the named host existed, and only a live
probe can answer that. The smoke section above is the right guard, and it is the
only one that ever failed on this bug.

## Related

- [certforge-public-urls-404.md](./certforge-public-urls-404.md) — the same class
  of defect on `CERTFORGE_WEB_URL`, closed 2026-08-27. That one was in printed QR
  codes; this one is not, which is the whole difference in severity.
- `apps/api/api/core/config.py:95-112` — the three-host split and why each exists.
