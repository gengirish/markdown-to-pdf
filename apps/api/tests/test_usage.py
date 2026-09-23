"""GET /orgs/{slug}/usage.

UsageLedger was written by consume_quota() (single and bulk issuance) and by
the vision-import counter in routes/templates.py, but nothing ever read it
back — apps/web's PlanCard said so outright rather than fake a number. This
is that read path: it must reflect exactly what those two writers left
behind, never create a ledger row itself, and represent an unlimited tier
(an effective quota of -1) as `null`, not the internal `-1` sentinel.
"""

from fastapi.testclient import TestClient

from api.core.config import get_tier_template_limit
from api.models.organization import Organization, OrgMember
from api.models.template import Template
from api.models.usage import UsageLedger


def org_owned_by_test_user(db_session, slug, *, tier="community", override=None):
    org = Organization(slug=slug, name=slug.title(), tier=tier, credential_quota_override=override)
    db_session.add(org)
    db_session.commit()
    db_session.add(OrgMember(org_id=org.id, clerk_user_id="test_user_123", role="owner"))
    db_session.commit()
    return org


def test_usage_with_no_ledger_row_reports_zero(client: TestClient, mock_clerk, db_session):
    """A fresh org has issued nothing this month and has no ledger row at
    all — the endpoint must not create one just because it was asked."""
    org = org_owned_by_test_user(db_session, "usage-fresh")

    response = client.get("/api/v1/orgs/usage-fresh/usage")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["tier"] == "community"
    assert data["credentials"] == {"used": 0, "limit": 50, "remaining": 50, "source": "tier"}
    assert data["vision_imports"] == {"used": 0, "limit": 10, "remaining": 10}
    # Community's template allowance, counted from rows rather than a ledger.
    assert data["templates"] == {"used": 0, "limit": 1, "remaining": 1}

    assert db_session.query(UsageLedger).filter_by(org_id=org.id).first() is None


def test_usage_reflects_what_the_writers_left(client: TestClient, mock_clerk, db_session):
    org = org_owned_by_test_user(db_session, "usage-active")
    ledger = UsageLedger(
        org_id=org.id,
        period=UsageLedger.current_period(),
        credentials_issued=12,
        vision_imports=3,
    )
    db_session.add(ledger)
    db_session.commit()

    response = client.get("/api/v1/orgs/usage-active/usage")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["credentials"] == {"used": 12, "limit": 50, "remaining": 38, "source": "tier"}
    assert data["vision_imports"] == {"used": 3, "limit": 10, "remaining": 7}


def test_unlimited_tier_reports_null_not_the_sentinel(client: TestClient, mock_clerk, db_session):
    """An effective quota of -1 means unlimited internally (UNLIMITED). A JSON
    consumer should never have to know that sentinel — it must see `null`."""
    org_owned_by_test_user(db_session, "usage-scale", tier="scale")

    response = client.get("/api/v1/orgs/usage-scale/usage")
    assert response.status_code == 200
    data = response.json()["data"]["credentials"]
    assert data["used"] == 0
    assert data["limit"] is None
    assert data["remaining"] is None


def test_usage_404s_for_an_unknown_org(client: TestClient, mock_clerk):
    response = client.get("/api/v1/orgs/does-not-exist/usage")
    assert response.status_code == 404


def test_usage_403s_for_a_non_member(client: TestClient, mock_clerk, db_session):
    """test_user_123 (mock_clerk) must not be a member of this org."""
    org = Organization(slug="usage-not-mine", name="Not Mine", tier="community")
    db_session.add(org)
    db_session.commit()
    db_session.add(OrgMember(org_id=org.id, clerk_user_id="someone_else", role="owner"))
    db_session.commit()

    response = client.get("/api/v1/orgs/usage-not-mine/usage")
    assert response.status_code == 403


def test_usage_requires_sign_in(client: TestClient, db_session):
    """No mock_clerk override here — the request carries no credentials."""
    org = Organization(slug="usage-anon", name="Anon", tier="community")
    db_session.add(org)
    db_session.commit()

    response = client.get("/api/v1/orgs/usage-anon/usage")
    assert response.status_code == 401


def test_the_template_meter_counts_rows_the_org_holds(client: TestClient, mock_clerk, db_session):
    """Templates are a stock, not a monthly flow — the number here is the same
    one `routes/templates.py` gates on, so the card cannot show room the gate
    will refuse. Global templates (org_id = None) belong to nobody and must
    not appear in anyone's count."""
    org = org_owned_by_test_user(db_session, "usage-templates", tier="starter")
    db_session.add_all([
        Template(org_id=org.id, name="Mine", html_source="<p>{{name}}</p>", variables=[]),
        Template(org_id=None, name="Global", html_source="<p>{{name}}</p>", variables=[]),
    ])
    db_session.commit()

    data = client.get("/api/v1/orgs/usage-templates/usage").json()["data"]
    limit = get_tier_template_limit("starter")
    assert data["templates"] == {"used": 1, "limit": limit, "remaining": limit - 1}


def test_an_unknown_tier_reports_the_plan_its_limits_came_from(
    client: TestClient, mock_clerk, db_session
):
    """`organizations.tier` is free text and the Razorpay webhook has written
    values BILLING_TIERS never had. The card must not print a plan name whose
    limits are not the ones being enforced — so the endpoint reports the row
    the numbers were actually read from, and says the raw value is unknown."""
    org_owned_by_test_user(db_session, "usage-bogus", tier="pro")

    data = client.get("/api/v1/orgs/usage-bogus/usage").json()["data"]
    assert data["tier"] == "pro"
    assert data["tier_name"] == "Community"
    assert data["tier_known"] is False
    assert data["templates"]["limit"] == 1


def test_an_override_is_reported_as_the_source(client: TestClient, mock_clerk, db_session):
    """1,000 beside a Community plan the pricing page says allows 50 looks
    like a bug unless the plan card can say where the number came from."""
    org_owned_by_test_user(db_session, "usage-override", override=1000)

    data = client.get("/api/v1/orgs/usage-override/usage").json()["data"]
    assert data["tier_name"] == "Community"
    assert data["credentials"] == {"used": 0, "limit": 1000, "remaining": 1000, "source": "override"}
