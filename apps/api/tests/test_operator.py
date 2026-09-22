"""The operator surface: one org's credential quota, and its plan.

The guards here are the table in docs/operator-quota-overrides-plan.md,
"Tests". Each was seen to fail against the bug it names before it counted.
The ones that matter most test a join rather than a half: an override set
through the operator route has to bind at issuance, and a plan change from
the webhook has to go through the same rule as one from an operator.
"""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.core import config
from api.core.config import get_tier_quota
from api.core.principal import LIVE_PREFIX, hash_api_key
from api.models.api_key import ApiKey
from api.models.organization import Organization, OrgMember
from api.models.quota_change import CredentialQuotaChange
from api.services.issuance import effective_credential_quota
from api.services.plans import UnknownTier, change_tier

OPERATOR = "test_user_123"  # the id mock_clerk signs in as
REASON = "Customer asked on ticket #4521"


@pytest.fixture
def operator(monkeypatch, mock_clerk):
    monkeypatch.setattr(config, "OPERATOR_USER_IDS", frozenset({OPERATOR}))


def make_org(db_session, slug, *, tier="community", override=None, member=False):
    org = Organization(
        slug=slug, name=slug.title(), tier=tier, credential_quota_override=override
    )
    db_session.add(org)
    db_session.commit()
    if member:
        db_session.add(OrgMember(org_id=org.id, clerk_user_id=OPERATOR, role="owner"))
        db_session.commit()
    return org


def reload(db_session, slug):
    db_session.expire_all()
    return db_session.query(Organization).filter_by(slug=slug).one()


def changes(db_session, org):
    db_session.expire_all()
    return (
        db_session.query(CredentialQuotaChange)
        .filter_by(org_id=org.id)
        .order_by(CredentialQuotaChange.created_at)
        .all()
    )


def quota_url(slug):
    return f"/api/v1/operator/orgs/{slug}/credential-quota"


def put_quota(client, slug, limit, reason=REASON):
    return client.put(quota_url(slug), json={"limit": limit, "reason": reason})


def delete_quota(client, slug, reason=REASON):
    return client.request("DELETE", quota_url(slug), json={"reason": reason})


def put_tier(client, slug, tier, reason=REASON):
    return client.put(f"/api/v1/operator/orgs/{slug}/tier", json={"tier": tier, "reason": reason})


# -- who may call it -------------------------------------------------------------

def test_an_allowlisted_user_is_an_operator(client: TestClient, operator, db_session):
    make_org(db_session, "op-allowed")
    r = client.get(quota_url("op-allowed"))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["source"] == "tier"


def test_a_user_not_on_the_allowlist_is_refused(client, mock_clerk, monkeypatch, db_session):
    monkeypatch.setattr(config, "OPERATOR_USER_IDS", frozenset({"user_someone_else"}))
    make_org(db_session, "op-not-listed")
    assert client.get(quota_url("op-not-listed")).status_code == 403
    assert put_quota(client, "op-not-listed", 5000).status_code == 403
    assert put_tier(client, "op-not-listed", "scale").status_code == 403
    assert reload(db_session, "op-not-listed").credential_quota_override is None


def test_an_empty_allowlist_refuses_everyone(client, mock_clerk, monkeypatch, db_session):
    """No dev fallback: unset means nobody, in every environment."""
    monkeypatch.setattr(config, "OPERATOR_USER_IDS", frozenset())
    make_org(db_session, "op-empty-list")
    assert client.get("/api/v1/operator/orgs").status_code == 403
    assert put_tier(client, "op-empty-list", "scale").status_code == 403


def test_an_org_owners_api_key_is_refused(client, monkeypatch, db_session):
    """A key belongs to one customer org. Even with its owner allowlisted,
    the key is not a person and cannot be an operator."""
    monkeypatch.setattr(config, "OPERATOR_USER_IDS", frozenset({OPERATOR}))
    org = make_org(db_session, "op-key", member=True)
    raw = LIVE_PREFIX + "op-owner-key"
    db_session.add(ApiKey(org_id=org.id, key_hash=hash_api_key(raw), label="k"))
    db_session.commit()

    r = client.put(
        quota_url("op-key"),
        json={"limit": 5000, "reason": REASON},
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert r.status_code == 403
    assert reload(db_session, "op-key").credential_quota_override is None


def test_a_customer_cannot_set_their_own_quota(client, mock_clerk, db_session):
    make_org(db_session, "op-self-serve", member=True)
    r = client.patch(
        "/api/v1/orgs/op-self-serve",
        json={"name": "Renamed", "credential_quota_override": 1_000_000},
    )
    assert r.status_code == 200, r.text
    assert reload(db_session, "op-self-serve").credential_quota_override is None


def test_no_token_is_401(client, db_session):
    assert client.get("/api/v1/operator/orgs").status_code == 401


# -- the override binds at issuance ---------------------------------------------

def test_an_operator_override_binds_at_issuance(client: TestClient, operator, db_session):
    """The join: the operator route writes, issuance reads. Testing either
    half alone would miss a break between them."""
    make_org(db_session, "op-binds", member=True)
    assert put_quota(client, "op-binds", 2).status_code == 200

    def issue():
        return client.post(
            "/api/v1/orgs/op-binds/credentials",
            json={"recipient_name": "Ada Lovelace", "title": "Engines"},
        )

    assert issue().status_code == 201
    assert issue().status_code == 201
    refused = issue()
    assert refused.status_code == 402, refused.text


def test_removing_the_override_restores_the_tier_quota(client, operator, db_session):
    make_org(db_session, "op-remove", override=1000)

    r = delete_quota(client, "op-remove")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["source"] == "tier"
    assert data["override"] is None
    assert data["effective"] == get_tier_quota("community")
    assert reload(db_session, "op-remove").monthly_quota == get_tier_quota("community")


def test_a_tier_default_change_reaches_orgs_with_no_migration(db_session, monkeypatch):
    """No stored copy: an org without an override follows its tier live."""
    org = make_org(db_session, "op-live-tier")
    overridden = make_org(db_session, "op-live-tier-pinned", override=77)
    patched = {**config.BILLING_TIERS, "community": {**config.BILLING_TIERS["community"], "monthly_quota": 123}}
    monkeypatch.setattr(config, "BILLING_TIERS", patched)

    assert effective_credential_quota(org) == 123
    assert effective_credential_quota(overridden) == 77


def test_issuance_binds_at_the_live_tier_quota_not_the_stored_copy(client, mock_clerk, db_session, monkeypatch):
    """The override test above cannot catch issuance reading `monthly_quota`:
    every write keeps that column equal to the effective limit until W4, so
    both read 2. What only the live rule gets right is a tier default that
    changed after the row was written — the stored copy still says 50."""
    make_org(db_session, "op-live-issue", member=True)
    patched = {**config.BILLING_TIERS, "community": {**config.BILLING_TIERS["community"], "monthly_quota": 1}}
    monkeypatch.setattr(config, "BILLING_TIERS", patched)

    def issue():
        return client.post(
            "/api/v1/orgs/op-live-issue/credentials",
            json={"recipient_name": "Ada Lovelace", "title": "Engines"},
        )

    assert issue().status_code == 201
    assert issue().status_code == 402


def test_unlimited_is_null_on_the_wire_and_minus_one_inside(client, operator, db_session):
    make_org(db_session, "op-unlimited")
    r = put_quota(client, "op-unlimited", None)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["override"] == {"limit": None}
    assert data["effective"] is None
    assert reload(db_session, "op-unlimited").credential_quota_override == -1


def test_below_usage_is_allowed_and_reports_over_by(client, operator, db_session):
    from api.models.usage import UsageLedger

    org = make_org(db_session, "op-over")
    db_session.add(UsageLedger(org_id=org.id, period=UsageLedger.current_period(), credentials_issued=30))
    db_session.commit()

    data = put_quota(client, "op-over", 10).json()["data"]
    assert data["effective"] == 10
    assert data["over_by"] == 20


def test_an_override_equal_to_the_tier_carries_a_note(client, operator, db_session):
    make_org(db_session, "op-equal")
    data = put_quota(client, "op-equal", get_tier_quota("community")).json()["data"]
    assert "freezes" in data["note"]


# -- the change log ---------------------------------------------------------------

def test_every_change_is_logged_with_actor_and_reason(client, operator, db_session):
    org = make_org(db_session, "op-log")
    put_quota(client, "op-log", 1000)
    delete_quota(client, "op-log", reason="Pilot ended, back to plan")

    rows = changes(db_session, org)
    assert [(r.previous_override, r.new_override) for r in rows] == [(None, 1000), (1000, None)]
    assert [r.effective_before for r in rows] == [50, 1000]
    assert [r.effective_after for r in rows] == [1000, 50]
    assert {r.actor for r in rows} == {OPERATOR}
    assert rows[0].reason == REASON

    history = client.get(quota_url("op-log")).json()["data"]["history"]
    assert history[0]["reason"] == "Pilot ended, back to plan"  # newest first
    assert history[1]["new_override"] == {"limit": 1000}


@pytest.mark.parametrize(
    "body",
    [
        {"limit": 1000},                                  # no reason
        {"limit": 1000, "reason": "too short"},           # under 10 characters
        {"limit": 1000, "reason": "          padded   "},  # blank once stripped
        {"limit": -5, "reason": REASON},
        {"limit": 1_000_001, "reason": REASON},           # the mistyped zero
        {"reason": REASON},                               # limit is required
    ],
)
def test_a_rejected_request_writes_nothing(client, operator, db_session, body):
    slug = f"op-reject-{abs(hash(json.dumps(body, sort_keys=True))) % 10**8}"
    org = make_org(db_session, slug)
    r = client.put(quota_url(slug), json=body)
    assert r.status_code == 422, r.text
    assert reload(db_session, slug).credential_quota_override is None
    assert changes(db_session, org) == []


def test_the_log_row_rolls_back_with_the_change(client, operator, db_session):
    """Same transaction: a failure after the write leaves neither."""
    org = make_org(db_session, "op-atomic")
    with patch("api.routes.operator._state", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            put_quota(client, "op-atomic", 1000)
    assert reload(db_session, "op-atomic").credential_quota_override is None
    assert changes(db_session, org) == []


# -- a plan change clears the override (Decision 4) -------------------------------

# The webhook half of Decision 4 — a Dodo plan change clears the override and
# logs it, a redelivery for the same tier changes nothing — is tested beside
# the webhook, in tests/test_billing_dodo.py.


def test_a_downgrade_clears_the_override_too(db_session):
    org = make_org(db_session, "op-downgrade", tier="scale", override=5000)
    assert change_tier(db_session, org, "community", actor="test") is True
    assert org.credential_quota_override is None
    assert effective_credential_quota(org) == get_tier_quota("community")


def test_change_tier_refuses_a_tier_the_table_does_not_know(db_session):
    org = make_org(db_session, "op-unknown-fn")
    with pytest.raises(UnknownTier):
        change_tier(db_session, org, "enterprise", actor="test")
    assert org.tier == "community"


# -- the manual plan change --------------------------------------------------------

def test_an_operator_can_move_an_org_to_a_paid_plan_without_payment(client, operator, db_session):
    make_org(db_session, "op-upgrade")
    r = put_tier(client, "op-upgrade", "pro")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert (data["tier"], data["previous_tier"], data["changed"]) == ("pro", "community", True)
    assert reload(db_session, "op-upgrade").tier == "pro"


def test_a_manual_plan_change_is_what_the_gates_read(client, operator, db_session):
    """Read back through the customer's own usage endpoint — the limits the
    gates enforce, not the column this route wrote."""
    make_org(db_session, "op-gates", member=True)
    assert client.get("/api/v1/orgs/op-gates/usage").json()["data"]["templates"]["limit"] == 1

    put_tier(client, "op-gates", "pro")

    after = client.get("/api/v1/orgs/op-gates/usage").json()["data"]
    assert after["tier_name"] == "Pro"
    assert after["templates"]["limit"] == 5
    assert after["credentials"]["limit"] == get_tier_quota("pro")
    assert after["credentials"]["source"] == "tier"


def test_a_manual_plan_change_clears_the_override_under_the_operators_name(client, operator, db_session):
    org = make_org(db_session, "op-manual-clear", override=1000)
    data = put_tier(client, "op-manual-clear", "pro").json()["data"]
    assert data["override_cleared"] is True
    assert data["effective"] == get_tier_quota("pro")

    rows = changes(db_session, org)
    assert len(rows) == 1
    assert rows[0].actor == OPERATOR
    assert REASON in rows[0].reason


def test_a_manual_change_to_the_current_plan_is_a_no_op(client, operator, db_session):
    org = make_org(db_session, "op-same-tier", override=1000)
    data = put_tier(client, "op-same-tier", "community").json()["data"]
    assert data["changed"] is False
    assert reload(db_session, "op-same-tier").credential_quota_override == 1000
    assert changes(db_session, org) == []


def test_an_unknown_tier_is_refused_and_nothing_changes(client, operator, db_session):
    make_org(db_session, "op-bogus")
    r = put_tier(client, "op-bogus", "enterprise")
    assert r.status_code == 422
    assert r.json()["error"]["type"] == "unknown_tier"
    assert reload(db_session, "op-bogus").tier == "community"


def test_a_plan_change_needs_a_reason(client, operator, db_session):
    make_org(db_session, "op-tier-reason")
    assert client.put("/api/v1/operator/orgs/op-tier-reason/tier", json={"tier": "scale"}).status_code == 422
    assert reload(db_session, "op-tier-reason").tier == "community"


def test_missing_org_is_404(client, operator):
    assert put_tier(client, "nope-not-here", "pro").status_code == 404
    assert put_quota(client, "nope-not-here", 10).status_code == 404


# -- the list ------------------------------------------------------------------------

def test_list_searches_and_pages_by_slug(client, operator, db_session):
    for s in ("oplist-a", "oplist-b", "oplist-c"):
        make_org(db_session, s)
    make_org(db_session, "oplist-d", override=1000)

    first = client.get("/api/v1/operator/orgs", params={"q": "oplist-", "limit": 2}).json()["data"]
    assert [o["slug"] for o in first["orgs"]] == ["oplist-a", "oplist-b"]
    assert first["next_cursor"] == "oplist-b"

    rest = client.get(
        "/api/v1/operator/orgs", params={"q": "oplist-", "limit": 2, "cursor": first["next_cursor"]}
    ).json()["data"]
    assert [o["slug"] for o in rest["orgs"]] == ["oplist-c", "oplist-d"]
    assert rest["next_cursor"] is None
    assert rest["orgs"][1]["override"] == {"limit": 1000}
    assert rest["orgs"][1]["source"] == "override"
