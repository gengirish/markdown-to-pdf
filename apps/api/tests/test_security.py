"""Regressions for the auth / webhook / rate-limit fixes.

Each test here corresponds to a way the API could previously be tricked into
trusting something it should not have.
"""

import base64
import hashlib
import hmac
import json
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from api.core import auth


def _unsigned_token(sub="attacker", org_id="org_victim", org_role="owner") -> str:
    """A token with a well-formed body and a garbage signature."""
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').decode().rstrip("=")
    body = base64.urlsafe_b64encode(
        json.dumps({"sub": sub, "org_id": org_id, "org_role": org_role, "exp": 9999999999}).encode()
    ).decode().rstrip("=")
    return f"{header}.{body}.not-a-real-signature"


def _bearer(token: str) -> Mock:
    return Mock(headers={"Authorization": f"Bearer {token}"})


@pytest.fixture(autouse=True)
def _reset_jwks_client():
    auth._jwks_client = None
    yield
    auth._jwks_client = None


# ── Clerk JWT verification ────────────────────────────────────────────────

def test_forged_token_is_never_trusted():
    """An unsigned token must not authenticate, whatever it claims."""
    with pytest.raises(HTTPException) as exc:
        auth.get_current_user(_bearer(_unsigned_token()))
    assert exc.value.status_code in (401, 503)


def test_missing_pyjwt_rejects_instead_of_decoding_unverified():
    """Without PyJWT the module must 503, not read claims out of the body.

    The old fallback base64-decoded the payload and trusted it, so anyone could
    mint `{"sub": ..., "org_role": "owner"}` and take over any organization.
    """
    real_import = __import__

    def _no_pyjwt(name, *args, **kwargs):
        if name == "jwt":
            raise ImportError("No module named 'jwt'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_no_pyjwt):
        with pytest.raises(HTTPException) as exc:
            auth.get_current_user(_bearer(_unsigned_token()))
    assert exc.value.status_code == 503


def test_missing_auth_header_is_401():
    with pytest.raises(HTTPException) as exc:
        auth.get_current_user(Mock(headers={}))
    assert exc.value.status_code == 401


def test_jwks_url_derived_from_publishable_key():
    key = "pk_test_" + base64.b64encode(b"example-42.clerk.accounts.dev$").decode().rstrip("=")
    assert auth._jwks_url_from_publishable_key(key) == (
        "https://example-42.clerk.accounts.dev/.well-known/jwks.json"
    )


@pytest.mark.parametrize("value", ["", "not-a-key", "pk_test_!!!not-base64!!!"])
def test_jwks_url_derivation_rejects_junk(value):
    assert auth._jwks_url_from_publishable_key(value) == ""


# ── Org membership ────────────────────────────────────────────────────────

def test_org_role_not_granted_by_jwt_claims_alone(client, db_session):
    """Claims must not be able to assert membership; the DB decides.

    `org_id` in a Clerk token is a Clerk id, while callers pass CertForge's own
    UUID — the removed "fast path" compared the two, so only a token crafted to
    match could satisfy it.
    """
    import uuid

    from api.models.organization import Organization

    org_id = uuid.uuid4()
    db_session.add(Organization(id=org_id, name="Victim Org", slug="victim-org"))
    db_session.commit()

    attacker = auth.AuthenticatedUser(
        clerk_user_id="attacker",
        clerk_org_id=str(org_id),   # claims to be in the org
        clerk_org_role="owner",     # claims to own it
    )
    with pytest.raises(HTTPException) as exc:
        auth.require_org_role(attacker, str(org_id))
    assert exc.value.status_code == 403


def test_non_uuid_org_id_is_forbidden_not_a_500(client):
    user = auth.AuthenticatedUser(clerk_user_id="someone")
    with pytest.raises(HTTPException) as exc:
        auth.require_org_role(user, "'; drop table org_members; --")
    assert exc.value.status_code == 403


# ── Razorpay webhook ──────────────────────────────────────────────────────

WEBHOOK_BODY = b'{"event":"subscription.activated","payload":{}}'


def _sign(secret: str) -> str:
    return hmac.new(secret.encode(), WEBHOOK_BODY, hashlib.sha256).hexdigest()


def _post_webhook(client, signature=None):
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["X-Razorpay-Signature"] = signature
    return client.post("/api/v1/webhooks/razorpay", content=WEBHOOK_BODY, headers=headers)


def test_webhook_rejects_the_old_default_secret(client):
    """`rzp_test_secret` used to be the built-in default, so it was public."""
    with patch("api.routes.billing.RAZORPAY_SECRET", "a-real-configured-secret"):
        assert _post_webhook(client, _sign("rzp_test_secret")).status_code == 400


def test_webhook_accepts_a_correctly_signed_payload(client):
    with patch("api.routes.billing.RAZORPAY_SECRET", "a-real-configured-secret"):
        res = _post_webhook(client, _sign("a-real-configured-secret"))
    assert res.status_code == 200
    assert res.json()["success"] is True


def test_webhook_without_a_configured_secret_rejects_everything(client):
    with patch("api.routes.billing.RAZORPAY_SECRET", ""):
        assert _post_webhook(client, _sign("")).status_code == 503


def test_webhook_requires_a_signature_header(client):
    with patch("api.routes.billing.RAZORPAY_SECRET", "a-real-configured-secret"):
        assert _post_webhook(client).status_code == 400


# ── Rate limiting behind the proxy chain ──────────────────────────────────

def _request(forwarded=None, peer="66.33.22.11"):
    req = Mock()
    req.headers = {"x-forwarded-for": forwarded} if forwarded else {}
    req.client = Mock(host=peer) if peer else None
    return req


@pytest.mark.parametrize(
    "forwarded,peer,expected",
    [
        # browser -> Vercel edge -> Fly proxy: the caller is 2 entries from the right.
        ("203.0.113.9, 76.76.21.21", "172.16.0.1", "203.0.113.9"),
        # A request straight to Fly has one hop, so take what Fly recorded.
        ("45.10.0.7", "172.16.0.1", "45.10.0.7"),
        # A client that prepends its own header cannot shift the entry we read.
        ("1.1.1.1, 2.2.2.2, 45.10.0.7", "172.16.0.1", "2.2.2.2"),
        # No forwarding headers at all (local dev): the socket peer.
        (None, "127.0.0.1", "127.0.0.1"),
        (None, None, "unknown"),
    ],
)
def test_client_ip_resolution(forwarded, peer, expected):
    from api.index import _client_ip

    assert _client_ip(_request(forwarded, peer)) == expected


def test_callers_behind_the_proxy_get_separate_buckets():
    """The bug: req.client.host is the Fly proxy, so everyone shared one bucket."""
    from api.index import RATE_LIMIT, _check_rate_limit, _client_ip

    alice = _client_ip(_request("203.0.113.9, 76.76.21.21"))
    bob = _client_ip(_request("198.51.100.4, 76.76.21.21"))
    assert alice != bob

    for _ in range(RATE_LIMIT):
        assert _check_rate_limit(alice)[0] is True
    assert _check_rate_limit(alice)[0] is False   # Alice is out of budget
    assert _check_rate_limit(bob)[0] is True      # Bob is unaffected


# -- JSON-LD injection on the legacy viewer -----------------------------------
#
# json.dumps escapes quotes and backslashes but not "<". The HTML parser ends a
# <script> at the first literal "</script>" regardless of JSON syntax, so a
# participant name carrying one closed the block and executed. The name is
# attacker-controlled: anyone who can generate a certificate can put it there,
# then send the resulting /certificate/{token} link to a victim.

BREAKOUT = "</script><script>alert(document.domain)</script>"


def _json_ld_payload(markup: str) -> dict:
    import json

    return json.loads(markup.split(">", 1)[1].rsplit("<", 1)[0])


def test_a_recipient_name_cannot_close_the_json_ld_block():
    from api.index import _participation_json_ld

    markup = _participation_json_ld(
        participant_name=BREAKOUT,
        course_name="C",
        completion_date="2026-01-01",
        cert_id="CERT-X",
        page_url="https://certs.example/certificate/x",
        brand_name="B",
        participation_title="T",
    )
    assert "</script><script>" not in markup
    assert markup.count("</script>") == 1, "the block is closed more than once"


def test_the_internship_viewer_is_guarded_too():
    """Both builders share _json_ld_script, and a future third must as well."""
    from api.index import _internship_json_ld
    import inspect

    sig = inspect.signature(_internship_json_ld)
    kwargs = {name: "x" for name in sig.parameters}
    kwargs["participant_name"] = BREAKOUT
    markup = _internship_json_ld(**kwargs)
    assert "</script><script>" not in markup


def test_escaping_does_not_change_what_a_consumer_reads():
    """The fix must be invisible to every JSON-LD reader.

    < is valid JSON and decodes to the same character, so a consumer sees
    the name exactly as before. If this ever fails, the fix has started
    corrupting data rather than encoding it.
    """
    from api.index import _participation_json_ld

    markup = _participation_json_ld(
        participant_name=BREAKOUT,
        course_name="Café & <Co>",
        completion_date="2026-01-01",
        cert_id="CERT-X",
        page_url="https://certs.example/certificate/x",
        brand_name="B",
        participation_title="T",
    )
    payload = _json_ld_payload(markup)
    assert payload["awardedTo"]["name"] == BREAKOUT
    assert payload["about"]["name"] == "Café & <Co>"
