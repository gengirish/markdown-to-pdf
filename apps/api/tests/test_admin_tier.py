"""PUT /api/v1/admin/orgs/{slug}/tier — the operator's way to move a plan.

Checkout is mocked, so this is the only door out of a tier gate. The two
things it must get right are the join the SQL workaround kept missing — `tier`
and `monthly_quota` written together, from the table — and that the door is
locked to everyone who is not an operator, including the org's own owner.
"""

import pytest
from fastapi.testclient import TestClient

from api.core import config
from api.core.config import get_tier_quota
from api.models.organization import Organization, OrgMember

ADMIN = {"X-Admin-Key": "test-admin-key"}


@pytest.fixture(autouse=True)
def admin_key(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_KEY", "test-admin-key")


def make_org(db_session, slug, *, tier="community", quota=None):
    org = Organization(
        slug=slug,
        name=slug.title(),
        tier=tier,
        monthly_quota=get_tier_quota(tier) if quota is None else quota,
    )
    db_session.add(org)
    db_session.commit()
    return org


def reload(db_session, slug):
    db_session.expire_all()
    return db_session.query(Organization).filter_by(slug=slug).one()


def test_upgrade_community_to_starter(client: TestClient, db_session):
    make_org(db_session, "adm-up")

    r = client.put(
        "/api/v1/admin/orgs/adm-up/tier",
        json={"tier": "starter", "reason": "pilot"},
        headers=ADMIN,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["tier"] == "starter"
    assert data["previous_tier"] == "community"
    assert reload(db_session, "adm-up").tier == "starter"


def test_quota_moves_with_the_tier(client: TestClient, db_session):
    """The half the SQL workaround forgot. Community and Starter share 500,
    so this uses Growth, where a tier-only update leaves the org metered at
    Community volume while every gate says Growth."""
    make_org(db_session, "adm-quota")

    r = client.put("/api/v1/admin/orgs/adm-quota/tier", json={"tier": "growth"}, headers=ADMIN)
    assert r.status_code == 200, r.text
    org = reload(db_session, "adm-quota")
    assert org.monthly_quota == get_tier_quota("growth") != get_tier_quota("community")
    assert r.json()["data"]["monthly_quota"] == get_tier_quota("growth")


def test_scale_quota_is_unlimited_and_null_on_the_wire(client: TestClient, db_session):
    make_org(db_session, "adm-scale")

    r = client.put("/api/v1/admin/orgs/adm-scale/tier", json={"tier": "scale"}, headers=ADMIN)
    assert r.status_code == 200, r.text
    assert reload(db_session, "adm-scale").monthly_quota == -1
    assert r.json()["data"]["monthly_quota"] is None


def test_downgrade_resets_quota_from_the_table(client: TestClient, db_session):
    make_org(db_session, "adm-down", tier="scale")

    r = client.put("/api/v1/admin/orgs/adm-down/tier", json={"tier": "community"}, headers=ADMIN)
    assert r.status_code == 200, r.text
    org = reload(db_session, "adm-down")
    assert (org.tier, org.monthly_quota) == ("community", get_tier_quota("community"))
    assert r.json()["data"]["previous_monthly_quota"] is None


def test_upgrade_is_what_the_gates_read(client: TestClient, mock_clerk, db_session):
    """The point of the exercise, read back through the usage endpoint the
    dashboard's plan card calls — the limits the gates enforce, not the
    column this route wrote."""
    org = make_org(db_session, "adm-gates")
    db_session.add(OrgMember(org_id=org.id, clerk_user_id="test_user_123", role="owner"))
    db_session.commit()

    before = client.get("/api/v1/orgs/adm-gates/usage").json()["data"]
    assert before["templates"]["limit"] == 1

    client.put("/api/v1/admin/orgs/adm-gates/tier", json={"tier": "growth"}, headers=ADMIN)

    after = client.get("/api/v1/orgs/adm-gates/usage").json()["data"]
    assert after["tier_name"] == "Growth"
    assert after["templates"]["limit"] == 25
    assert after["credentials"]["limit"] == get_tier_quota("growth")

    r = client.get("/api/v1/admin/orgs/adm-gates", headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["data"]["tier"] == "growth"
    assert r.json()["data"]["tier_known"] is True


def test_unknown_tier_is_refused_and_nothing_changes(client: TestClient, db_session):
    """`pro` is the value the Razorpay webhook wrote for months. A tier the
    table does not know is Community everywhere, so accepting one would
    report success and grant nothing."""
    make_org(db_session, "adm-bogus")

    r = client.put("/api/v1/admin/orgs/adm-bogus/tier", json={"tier": "pro"}, headers=ADMIN)
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["type"] == "unknown_tier"
    assert "starter" in error["details"]["tiers"]
    assert reload(db_session, "adm-bogus").tier == "community"


def test_missing_org_is_404(client: TestClient):
    r = client.put("/api/v1/admin/orgs/nope/tier", json={"tier": "starter"}, headers=ADMIN)
    assert r.status_code == 404


@pytest.mark.parametrize("headers", [{}, {"X-Admin-Key": "wrong"}, {"X-Admin-Key": ""}])
def test_wrong_or_missing_key_is_401_and_nothing_changes(client: TestClient, db_session, headers):
    slug = f"adm-auth-{len(headers)}-{headers.get('X-Admin-Key', 'none') or 'empty'}"
    make_org(db_session, slug)

    r = client.put(f"/api/v1/admin/orgs/{slug}/tier", json={"tier": "scale"}, headers=headers)
    assert r.status_code == 401
    assert reload(db_session, slug).tier == "community"


def test_org_owner_session_cannot_upgrade_itself(client: TestClient, mock_clerk, db_session):
    """A signed-in owner is the person with the most reason to grant
    themselves a plan. A Clerk session must not open this door."""
    org = make_org(db_session, "adm-self")
    db_session.add(OrgMember(org_id=org.id, clerk_user_id="test_user_123", role="owner"))
    db_session.commit()

    r = client.put("/api/v1/admin/orgs/adm-self/tier", json={"tier": "scale"})
    assert r.status_code == 401
    assert reload(db_session, "adm-self").tier == "community"


def test_unconfigured_admin_key_fails_closed(client: TestClient, db_session, monkeypatch):
    """With ADMIN_KEY unset, an empty header must not match an empty secret."""
    monkeypatch.setattr(config, "ADMIN_KEY", "")
    make_org(db_session, "adm-unset")

    r = client.put(
        "/api/v1/admin/orgs/adm-unset/tier",
        json={"tier": "scale"},
        headers={"X-Admin-Key": ""},
    )
    assert r.status_code == 503
    assert reload(db_session, "adm-unset").tier == "community"
