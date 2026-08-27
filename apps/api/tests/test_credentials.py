"""Single-credential issuance, and the quota that never bound until now.

`UsageLedger` was read in studio.py and written nowhere, so `used` was always 0
and `monthly_quota` was decoration. These tests are the proof it counts.
"""

from datetime import datetime, timedelta, timezone

import pytest

from api.core.principal import LIVE_PREFIX, TEST_PREFIX, hash_api_key
from api.models.api_key import ApiKey
from api.models.credential import Credential
from api.models.organization import Organization
from api.models.usage import UsageLedger


def org_with_key(db_session, slug, raw_key, quota=50):
    org = Organization(slug=slug, name=slug.title(), tier="community", monthly_quota=quota)
    db_session.add(org)
    db_session.commit()
    db_session.add(ApiKey(org_id=org.id, key_hash=hash_api_key(raw_key), label="k"))
    db_session.commit()
    return org


def auth(raw):
    return {"Authorization": f"Bearer {raw}"}


def issue(client, slug, raw, name="Ada Lovelace", title="Analytical Engines"):
    return client.post(
        f"/api/v1/orgs/{slug}/credentials",
        headers=auth(raw),
        json={"recipient_name": name, "title": title},
    )


# -- issuing -----------------------------------------------------------------

def test_a_key_holder_can_issue_a_credential_with_one_call(client, db_session):
    raw = LIVE_PREFIX + "issuer-key"
    org_with_key(db_session, "issue-me", raw)

    r = issue(client, "issue-me", raw)
    assert r.status_code == 201, r.text
    data = r.json()["data"]

    assert data["id"].startswith("CF-")
    assert data["recipient_name"] == "Ada Lovelace"
    assert data["status"] == "issued"
    assert data["verify_url"].endswith(f"/verify/{data['id']}")
    assert data["badge_url"].endswith(f"/credentials/{data['id']}/badge.json")


def test_the_credential_is_persisted_and_signed(client, db_session):
    raw = LIVE_PREFIX + "persist-key"
    org_with_key(db_session, "persisted", raw)
    public_id = issue(client, "persisted", raw).json()["data"]["id"]

    row = db_session.query(Credential).filter_by(public_id=public_id).one()
    assert row.status == "issued"
    assert len(row.hmac_signature) == 64


def test_issued_credentials_are_immediately_verifiable(client, db_session):
    """A credential that cannot be verified the moment it exists is not issued."""
    raw = LIVE_PREFIX + "verifiable-key"
    org_with_key(db_session, "verifiable", raw)
    public_id = issue(client, "verifiable", raw).json()["data"]["id"]

    r = client.get(f"/api/v1/verify/{public_id}")
    assert r.status_code == 200
    assert r.json()["data"]["id"] == public_id


def test_missing_fields_are_422_not_500(client, db_session):
    raw = LIVE_PREFIX + "validation-key"
    org_with_key(db_session, "validated", raw)
    r = client.post(
        "/api/v1/orgs/validated/credentials", headers=auth(raw), json={"title": "No name"}
    )
    assert r.status_code == 422


def test_issuing_into_another_org_is_refused(client, db_session):
    raw = LIVE_PREFIX + "mine-only"
    org_with_key(db_session, "mine", raw)
    Organization(slug="theirs", name="Theirs", tier="community")
    db_session.add(Organization(slug="theirs", name="Theirs", tier="community"))
    db_session.commit()

    assert issue(client, "theirs", raw).status_code == 403


# -- quota -------------------------------------------------------------------

def test_issuing_increments_the_usage_ledger(client, db_session):
    raw = LIVE_PREFIX + "metered-key"
    org = org_with_key(db_session, "metered", raw)

    for _ in range(3):
        assert issue(client, "metered", raw).status_code == 201

    ledger = (
        db_session.query(UsageLedger)
        .filter_by(org_id=org.id, period=UsageLedger.current_period())
        .one()
    )
    assert ledger.credentials_issued == 3


def test_the_quota_actually_refuses_once_reached(client, db_session):
    """The whole point: monthly_quota was never enforced before."""
    raw = LIVE_PREFIX + "small-quota-key"
    org_with_key(db_session, "tiny", raw, quota=2)

    assert issue(client, "tiny", raw).status_code == 201
    assert issue(client, "tiny", raw).status_code == 201

    refused = issue(client, "tiny", raw)
    assert refused.status_code == 402
    assert "quota" in refused.json()["error"]["message"].lower()


def test_a_refused_request_does_not_consume_quota(client, db_session):
    raw = LIVE_PREFIX + "no-double-charge"
    org = org_with_key(db_session, "nodouble", raw, quota=1)

    issue(client, "nodouble", raw)
    issue(client, "nodouble", raw)  # refused
    issue(client, "nodouble", raw)  # refused

    ledger = (
        db_session.query(UsageLedger)
        .filter_by(org_id=org.id, period=UsageLedger.current_period())
        .one()
    )
    assert ledger.credentials_issued == 1


def test_unlimited_quota_never_refuses(client, db_session):
    raw = LIVE_PREFIX + "scale-tier-key"
    org_with_key(db_session, "unlimited", raw, quota=-1)

    for _ in range(5):
        assert issue(client, "unlimited", raw).status_code == 201


def test_quota_headers_tell_the_caller_where_they_stand(client, db_session):
    raw = LIVE_PREFIX + "headers-key"
    org_with_key(db_session, "headered", raw, quota=10)

    r = issue(client, "headered", raw)
    assert r.headers["X-Quota-Limit"] == "10"
    assert r.headers["X-Quota-Remaining"] == "9"


def test_unlimited_is_reported_as_such_in_headers(client, db_session):
    raw = LIVE_PREFIX + "unlimited-headers"
    org_with_key(db_session, "unl-head", raw, quota=-1)
    r = issue(client, "unl-head", raw)
    assert r.headers["X-Quota-Limit"] == "unlimited"


def test_usage_is_counted_per_month(client, db_session):
    """A quota that never resets is a lifetime cap, not a monthly one."""
    raw = LIVE_PREFIX + "period-key"
    org = org_with_key(db_session, "periodic", raw, quota=2)

    last_month = (datetime.now(timezone.utc).replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    db_session.add(UsageLedger(org_id=org.id, period=last_month, credentials_issued=2))
    db_session.commit()

    assert issue(client, "periodic", raw).status_code == 201


# -- test keys ---------------------------------------------------------------

def test_a_test_key_issues_but_marks_the_credential(client, db_session):
    raw = TEST_PREFIX + "sandbox-key"
    org_with_key(db_session, "sandboxed", raw)

    data = issue(client, "sandboxed", raw).json()["data"]
    assert data["metadata"].get("_test") is True


# -- reading and revoking ----------------------------------------------------

def test_listing_returns_what_was_issued(client, db_session):
    raw = LIVE_PREFIX + "list-key"
    org_with_key(db_session, "listed", raw)
    issue(client, "listed", raw, name="First")
    issue(client, "listed", raw, name="Second")

    body = client.get("/api/v1/orgs/listed/credentials", headers=auth(raw)).json()["data"]
    assert body["total"] == 2
    assert {i["recipient_name"] for i in body["items"]} == {"First", "Second"}


def test_cursor_pagination_walks_without_repeating(client, db_session):
    raw = LIVE_PREFIX + "cursor-key"
    org_with_key(db_session, "paged", raw)
    for i in range(5):
        issue(client, "paged", raw, name=f"Person {i}")

    first = client.get(
        "/api/v1/orgs/paged/credentials?limit=2", headers=auth(raw)
    ).json()["data"]
    assert len(first["items"]) == 2
    assert first["has_more"] is True

    second = client.get(
        f"/api/v1/orgs/paged/credentials?limit=2&cursor={first['next_cursor']}",
        headers=auth(raw),
    ).json()["data"]

    assert not ({i["id"] for i in first["items"]} & {i["id"] for i in second["items"]})


def test_an_unknown_cursor_is_400_not_a_silent_empty_page(client, db_session):
    raw = LIVE_PREFIX + "badcursor-key"
    org_with_key(db_session, "badcursor", raw)
    r = client.get(
        "/api/v1/orgs/badcursor/credentials?cursor=CF-2026-NOTREAL", headers=auth(raw)
    )
    assert r.status_code == 400


def test_fetching_one_credential(client, db_session):
    raw = LIVE_PREFIX + "fetch-key"
    org_with_key(db_session, "fetched", raw)
    public_id = issue(client, "fetched", raw).json()["data"]["id"]

    r = client.get(f"/api/v1/orgs/fetched/credentials/{public_id}", headers=auth(raw))
    assert r.status_code == 200
    assert r.json()["data"]["id"] == public_id


def test_revoking_stops_verification(client, db_session):
    raw = LIVE_PREFIX + "revoke-key"
    org_with_key(db_session, "revoker", raw)
    public_id = issue(client, "revoker", raw).json()["data"]["id"]

    assert client.get(f"/api/v1/verify/{public_id}").status_code == 200

    r = client.post(f"/api/v1/orgs/revoker/credentials/{public_id}/revoke", headers=auth(raw))
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "revoked"

    assert client.get(f"/api/v1/verify/{public_id}").status_code == 404


def test_revoking_twice_is_idempotent(client, db_session):
    raw = LIVE_PREFIX + "twice-key"
    org_with_key(db_session, "twice", raw)
    public_id = issue(client, "twice", raw).json()["data"]["id"]

    client.post(f"/api/v1/orgs/twice/credentials/{public_id}/revoke", headers=auth(raw))
    again = client.post(f"/api/v1/orgs/twice/credentials/{public_id}/revoke", headers=auth(raw))
    assert again.status_code == 200
    assert again.json()["data"]["already_revoked"] is True


def test_revocation_does_not_hand_back_quota(client, db_session):
    """Issuing consumed the allowance; un-issuing does not refund it."""
    raw = LIVE_PREFIX + "norefund-key"
    org = org_with_key(db_session, "norefund", raw, quota=5)
    public_id = issue(client, "norefund", raw).json()["data"]["id"]
    client.post(f"/api/v1/orgs/norefund/credentials/{public_id}/revoke", headers=auth(raw))

    ledger = (
        db_session.query(UsageLedger)
        .filter_by(org_id=org.id, period=UsageLedger.current_period())
        .one()
    )
    assert ledger.credentials_issued == 1


def test_a_revoked_credential_is_still_retrievable_by_its_owner(client, db_session):
    """Verification must be able to say 'revoked', not 'never existed'."""
    raw = LIVE_PREFIX + "keeprow-key"
    org_with_key(db_session, "keeprow", raw)
    public_id = issue(client, "keeprow", raw).json()["data"]["id"]
    client.post(f"/api/v1/orgs/keeprow/credentials/{public_id}/revoke", headers=auth(raw))

    r = client.get(f"/api/v1/orgs/keeprow/credentials/{public_id}", headers=auth(raw))
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "revoked"
    assert r.json()["data"]["revoked_at"] is not None
