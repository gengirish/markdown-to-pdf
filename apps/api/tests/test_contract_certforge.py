"""The CertForge public-URL contract.

The freeze contract protects the legacy surface because its URLs are printed on
paper. CertForge's URLs are printed on paper too — they just aren't frozen yet,
which is the only reason the first production issuance was cheap to fix.

That issuance (`CF-2026-XEHQNMFZ`) shipped a QR code pointing at
`{CERTFORGE_WEB_URL}/verify/{id}`, which 404'd. Nothing caught it because each
half looked correct in isolation: the API really did serve `/verify/{id}`, and
`apps/web` really was deployed at that host — but `apps/web/vercel.json`
declared no rewrites, so the two never met. A test that only checked the API
route table would have passed. So would one that only checked the frontend.

This file asserts the join. For every URL CertForge writes into a credential:

  SERVED     some route on the FastAPI app matches the path.

  REACHABLE  on the host the URL actually names — which for CERTFORGE_WEB_URL
             means a rewrite in apps/web/vercel.json carries it to the API.

Adding a public CertForge URL without wiring both halves fails here.
"""

import json
import re
from pathlib import Path

import pytest

from api.core.config import CERTFORGE_API_URL, CERTFORGE_WEB_URL, SITE_URL
from api.core.principal import LIVE_PREFIX, hash_api_key
from api.models.api_key import ApiKey
from api.models.organization import Organization

REPO_ROOT = Path(__file__).resolve().parents[3]
WEB_VERCEL_JSON = REPO_ROOT / "apps" / "web" / "vercel.json"
WEB_PROXY_TS = REPO_ROOT / "apps" / "web" / "proxy.ts"


# -- the two halves, each expressed as a matcher ------------------------------

def _route_templates() -> set[str]:
    from api.index import app

    return {r.path for r in app.routes if hasattr(r, "path")}


def _template_to_regex(template: str) -> re.Pattern:
    """FastAPI's `/verify/{credential_id}` -> a regex matching a concrete path."""
    parts = re.split(r"(\{[^}]+\})", template)
    out = "".join("[^/]+" if p.startswith("{") else re.escape(p) for p in parts)
    return re.compile(f"^{out}$")


def _served_by_api(path: str) -> bool:
    return any(_template_to_regex(t).match(path) for t in _route_templates())


def _web_rewrites() -> list[dict]:
    config = json.loads(WEB_VERCEL_JSON.read_text(encoding="utf-8"))
    return config.get("rewrites", [])


def _source_to_regex(source: str) -> re.Pattern:
    """Vercel's `/verify/:path*` -> a regex matching a concrete path."""
    out = re.escape(source)
    out = out.replace(re.escape(":path*"), ".*")
    out = re.sub(r"\\:[A-Za-z_][A-Za-z0-9_]*", "[^/]+", out)
    return re.compile(f"^{out}$")


def _rewritten_by_web(path: str) -> bool:
    return any(_source_to_regex(r["source"]).match(path) for r in _web_rewrites())


# -- collecting the URLs a real credential carries ----------------------------

@pytest.fixture
def issued(client, db_session):
    """Issue one credential and return every public URL it carries.

    Deliberately read off a real issuance rather than a hand-written list: a
    URL that stops being written here stops being tested, and a new one starts
    being tested the moment the product starts emitting it.
    """
    raw = LIVE_PREFIX + "contract-url-key"
    # The test database lives for the whole session, so this fixture has to be
    # idempotent: it runs once per test in this file and must not collide with
    # the row its previous run left behind.
    org = db_session.query(Organization).filter_by(slug="contract-urls").first()
    if not org:
        org = Organization(
            slug="contract-urls",
            name="Contract Test College",
            tier="community",
            monthly_quota=500,
        )
        db_session.add(org)
        db_session.commit()
        db_session.add(ApiKey(org_id=org.id, key_hash=hash_api_key(raw), label="k"))
        db_session.commit()

    r = client.post(
        "/api/v1/orgs/contract-urls/credentials",
        headers={"Authorization": f"Bearer {raw}"},
        json={"recipient_name": "Ada Lovelace", "title": "Analytical Engines"},
    )
    assert r.status_code == 201, r.text
    cred = r.json()["data"]

    badge = client.get(f"/credentials/{cred['id']}/badge.json")
    assert badge.status_code == 200, badge.text
    doc = badge.json()

    return {
        "public_id": cred["id"],
        "org_slug": "contract-urls",
        # Labelled by emitter so a failure names what wrote the bad URL,
        # not just the path that broke.
        "urls": {
            "issuance verify_url": cred["verify_url"],
            "issuance badge_url": cred["badge_url"],
            "badge issuer.id": doc["issuer"]["id"],
            "badge achievement.id": doc["credentialSubject"]["achievement"]["id"],
        },
    }


def _split(url: str) -> tuple[str, str]:
    """Separate a credential URL into (host, path), or fail loudly."""
    for host in (CERTFORGE_WEB_URL, CERTFORGE_API_URL, SITE_URL):
        if url.startswith(host + "/"):
            return host, url[len(host):]
    raise AssertionError(f"URL points at an unrecognised host: {url}")


# -- SERVED -------------------------------------------------------------------

def test_every_url_a_credential_carries_is_served_by_the_api(issued):
    """The half that was already true, and was not enough on its own."""
    for label, url in issued["urls"].items():
        _, path = _split(url)
        assert _served_by_api(path), (
            f"{label} -> {url}\n"
            f"  no route on the API matches {path!r}. This is the /orgs/{{slug}} "
            f"failure: a URL written into a badge that nothing renders, on any host."
        )


# -- REACHABLE ----------------------------------------------------------------

def test_every_web_hosted_url_is_rewritten_through_to_the_api(issued):
    """The half that was missing, and the whole reason this file exists.

    apps/web is a Next.js app with no route handlers. A path it neither
    implements nor rewrites gets the app shell or a 404 — exactly what happened
    to /verify/{id} in production while the API served it perfectly.
    """
    for label, url in issued["urls"].items():
        host, path = _split(url)
        if host != CERTFORGE_WEB_URL:
            continue
        assert _rewritten_by_web(path), (
            f"{label} -> {url}\n"
            f"  {path!r} is on CERTFORGE_WEB_URL but no rewrite in "
            f"apps/web/vercel.json carries it to the API. It will 404 in "
            f"production while passing every API test."
        )


def test_no_credential_url_points_at_the_frozen_legacy_host(issued):
    """certs.intelliforge.tech is the legacy brand. Shipping CertForge
    credentials under it is a bug worker.py was already fixed once to stop."""
    for label, url in issued["urls"].items():
        assert not url.startswith(SITE_URL + "/"), (
            f"{label} -> {url} is on SITE_URL, the frozen legacy product"
        )


# -- the issuer profile, which previously had no target at all ----------------

def test_the_issuer_profile_resolves_and_identifies_itself(client, issued):
    """An Open Badges consumer dereferences issuer.id expecting a Profile."""
    r = client.get(
        f"/orgs/{issued['org_slug']}",
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["type"] == "Profile"
    assert doc["name"] == "Contract Test College"
    # It must claim the same URL the badge sent the consumer to, or the two
    # do not describe the same issuer.
    assert doc["id"] == issued["urls"]["badge issuer.id"]


def test_the_issuer_profile_serves_a_page_to_a_browser(client, issued):
    r = client.get(
        f"/orgs/{issued['org_slug']}",
        headers={"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
    )
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Contract Test College" in r.text


def test_an_unknown_issuer_is_404_not_a_blank_profile(client):
    r = client.get("/orgs/no-such-org", headers={"Accept": "application/json"})
    assert r.status_code == 404


# -- the namespace split that keeps the profile public ------------------------

def test_the_public_issuer_namespace_is_not_the_protected_dashboard_one():
    """`/orgs/{slug}` is anonymous; `/org/{slug}/...` is behind Clerk.

    apps/web/proxy.ts protects "/org/(.*)". It used to protect "/org(.*)",
    which also matches "/orgs/acme" — that would answer a badge consumer with
    a sign-in redirect instead of a Profile.
    """
    proxy = WEB_PROXY_TS.read_text(encoding="utf-8")
    # Only the matcher list, not the explanatory comment above it.
    block = proxy.split("createRouteMatcher(")[1].split(")")[0]
    matchers = re.findall(r'"(/org[^"]*)"', block)
    assert matchers, "no /org matcher found in proxy.ts"
    for m in matchers:
        pattern = _source_to_regex(m.replace("(.*)", ":path*"))
        assert not pattern.match("/orgs/contract-urls"), (
            f"proxy.ts matcher {m!r} also captures /orgs/{{slug}}, putting the "
            f"public issuer profile behind authentication"
        )


def test_the_public_credential_paths_skip_the_auth_middleware_entirely():
    """A printed QR code must not depend on Clerk being configured.

    A vercel.json rewrite does NOT bypass Next middleware — it runs first, on
    every rewritten path. The preview deployment of this fix proved it by
    answering 500 on /verify, /credentials and /orgs with "Missing
    publishableKey", because the Clerk env vars are set on Production only.

    These three paths are pure passthrough to the API, so they are excluded
    from the matcher: verification stays up whatever the dashboard's auth is
    doing.
    """
    proxy = WEB_PROXY_TS.read_text(encoding="utf-8")
    matcher_block = proxy.split("matcher:")[1]
    for rewritten in ("verify/", "credentials/", "orgs/"):
        assert rewritten in matcher_block, (
            f"{rewritten!r} is rewritten to the API in apps/web/vercel.json but "
            f"is not excluded from the proxy.ts matcher, so Clerk middleware "
            f"runs on it and a Clerk outage takes credential verification down"
        )
