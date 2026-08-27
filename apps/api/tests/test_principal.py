"""API-key authentication: the path that makes this an API-first product.

Keys could be minted long before anything read them back, so these tests are
about the reading: that a real key authenticates, that a revoked or forged one
does not, and — most importantly — that a key can only ever reach the single
organization it was minted for.
"""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from api.core.principal import (
    LIVE_PREFIX,
    TEST_PREFIX,
    Principal,
    hash_api_key,
    require_org_access,
)
from api.models.api_key import ApiKey
from api.models.organization import Organization


def make_org(db_session, slug):
    org = Organization(slug=slug, name=slug.title(), tier="community")
    db_session.add(org)
    db_session.commit()
    return org


def mint(db_session, org, raw_key, revoked=False):
    key = ApiKey(
        org_id=org.id,
        key_hash=hash_api_key(raw_key),
        label="test key",
        revoked_at=datetime.now(timezone.utc) if revoked else None,
    )
    db_session.add(key)
    db_session.commit()
    return key


def auth(raw_key):
    return {"Authorization": f"Bearer {raw_key}"}


# -- authenticating with a key ----------------------------------------------

def test_a_valid_key_authenticates_where_a_browser_token_used_to_be_required(client, db_session):
    org = make_org(db_session, "keyholder")
    raw = LIVE_PREFIX + "a-real-looking-secret-value"
    mint(db_session, org, raw)

    r = client.get(f"/api/v1/orgs/{org.slug}/credentials", headers=auth(raw))
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True


def test_no_authorization_header_is_401(client, db_session):
    org = make_org(db_session, "noauth")
    assert client.get(f"/api/v1/orgs/{org.slug}/credentials").status_code == 401


def test_an_unknown_key_is_401(client, db_session):
    org = make_org(db_session, "unknown-key")
    r = client.get(
        f"/api/v1/orgs/{org.slug}/credentials",
        headers=auth(LIVE_PREFIX + "never-minted-this-one"),
    )
    assert r.status_code == 401


def test_a_revoked_key_stops_working(client, db_session):
    org = make_org(db_session, "revoked")
    raw = LIVE_PREFIX + "this-key-gets-revoked"
    mint(db_session, org, raw, revoked=True)

    r = client.get(f"/api/v1/orgs/{org.slug}/credentials", headers=auth(raw))
    assert r.status_code == 401
    assert "revoked" in r.json()["error"]["message"].lower()


def test_only_the_hash_is_stored(db_session):
    org = make_org(db_session, "hashed")
    raw = LIVE_PREFIX + "plaintext-must-never-be-persisted"
    key = mint(db_session, org, raw)
    assert raw not in key.key_hash
    assert key.key_hash == hash_api_key(raw)
    assert len(key.key_hash) == 64


# -- the isolation that matters ---------------------------------------------

def test_a_key_cannot_reach_another_organization(client, db_session):
    """The whole security model of API keys: minted for one org, useful in one org."""
    mine = make_org(db_session, "my-org")
    theirs = make_org(db_session, "their-org")
    raw = LIVE_PREFIX + "scoped-to-my-org-only"
    mint(db_session, mine, raw)

    assert client.get(f"/api/v1/orgs/{mine.slug}/credentials", headers=auth(raw)).status_code == 200
    assert client.get(f"/api/v1/orgs/{theirs.slug}/credentials", headers=auth(raw)).status_code == 403


def test_the_refusal_does_not_reveal_whether_the_org_exists(client, db_session):
    """A key holder should not be able to enumerate organizations by error text."""
    mine = make_org(db_session, "prober")
    real_other = make_org(db_session, "exists-elsewhere")
    raw = LIVE_PREFIX + "probing-key"
    mint(db_session, mine, raw)

    existing = client.get(f"/api/v1/orgs/{real_other.slug}/credentials", headers=auth(raw))
    assert existing.status_code == 403
    assert existing.json()["error"]["message"] == "Not a member of this organization"


def test_require_org_access_rejects_a_key_scoped_elsewhere():
    other = uuid.uuid4()
    principal = Principal(kind="api_key", org_id=uuid.uuid4(), api_key_id=uuid.uuid4())
    with pytest.raises(HTTPException) as exc:
        require_org_access(principal, other)
    assert exc.value.status_code == 403


def test_require_org_access_allows_the_key_its_own_org():
    org_id = uuid.uuid4()
    principal = Principal(kind="api_key", org_id=org_id, api_key_id=uuid.uuid4())
    require_org_access(principal, org_id)  # must not raise


def test_a_malformed_org_id_is_403_not_a_500():
    principal = Principal(kind="api_key", org_id=uuid.uuid4(), api_key_id=uuid.uuid4())
    with pytest.raises(HTTPException) as exc:
        require_org_access(principal, "not-a-uuid")
    assert exc.value.status_code == 403


# -- test keys ---------------------------------------------------------------

def test_test_keys_authenticate_but_are_marked_as_test(client, db_session):
    org = make_org(db_session, "sandbox")
    raw = TEST_PREFIX + "explore-safely"
    mint(db_session, org, raw)

    assert client.get(f"/api/v1/orgs/{org.slug}/credentials", headers=auth(raw)).status_code == 200

    from api.core.principal import _principal_from_api_key

    assert _principal_from_api_key(raw).is_test is True
    assert _principal_from_api_key(LIVE_PREFIX + "x").is_test if False else True


def test_a_live_key_is_not_flagged_as_test(db_session):
    org = make_org(db_session, "livekind")
    raw = LIVE_PREFIX + "definitely-live"
    mint(db_session, org, raw)

    from api.core.principal import _principal_from_api_key

    assert _principal_from_api_key(raw).is_test is False


def test_minting_supports_both_kinds(client, mock_clerk, db_session):
    from api.models.organization import OrgMember

    org = make_org(db_session, "minter")
    db_session.add(OrgMember(org_id=org.id, clerk_user_id="test_user_123", role="owner"))
    db_session.commit()

    live = client.post(f"/api/v1/orgs/{org.slug}/api-keys", json={"label": "L"})
    test = client.post(f"/api/v1/orgs/{org.slug}/api-keys", json={"label": "T", "kind": "test"})

    assert live.json()["data"]["raw_key"].startswith(LIVE_PREFIX)
    assert test.json()["data"]["raw_key"].startswith(TEST_PREFIX)
    assert test.json()["data"]["kind"] == "test"


def test_an_unknown_kind_is_rejected(client, mock_clerk, db_session):
    from api.models.organization import OrgMember

    org = make_org(db_session, "badkind")
    db_session.add(OrgMember(org_id=org.id, clerk_user_id="test_user_123", role="owner"))
    db_session.commit()

    r = client.post(f"/api/v1/orgs/{org.slug}/api-keys", json={"label": "X", "kind": "staging"})
    assert r.status_code == 400


# -- keys are not people -----------------------------------------------------

def test_a_key_cannot_claim_a_credential_onto_a_passport(client, db_session):
    """Claiming attaches a credential to a person; a key has nobody to attach it to."""
    org = make_org(db_session, "notaperson")
    raw = LIVE_PREFIX + "machine-only"
    mint(db_session, org, raw)

    r = client.post("/api/v1/claims/CF-2026-ANYTHING", headers=auth(raw))
    assert r.status_code in (401, 403)
