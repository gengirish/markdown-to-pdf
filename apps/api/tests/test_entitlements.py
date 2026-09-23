"""What a plan grants beyond its two counts, and the 402s when it does not.

The pricing page sold CSV bulk issuance, artwork upload and API keys as Starter
features while the API granted all three to every tier — a Community org could
do everything Starter was sold on, and the only thing the upgrade bought was
four more template slots. Nothing failed, because nothing compared the page's
feature list with what the routes let through.

So the tests here come in two kinds: each gate refuses the way its route
claims, and a seam test walks every tier in the catalog through every gate, so
a tier that advertises one thing and is granted another fails here.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from api.core.config import BILLING_TIERS, get_tier_csv_batch_limit
from api.models.credential import CredentialBatch
from api.models.organization import Organization, OrgMember
from api.models.template import Template
from api.models.usage import UsageLedger
from api.services.entitlements import month_start

# Siblings, not package imports: tests/ has no __init__.py.
from test_template_assets import (  # noqa: E402
    png_bytes,
    store,  # noqa: F401 - fixture, used by argument name
    upload,
)

DEFER = "api.routes.studio.process_batch.defer_async"


def owned_org(db_session, slug, tier):
    """An org the `mock_clerk` user owns, with one template to bulk-issue from."""
    org = Organization(slug=slug, name=slug.title(), tier=tier, credential_quota_override=500)
    db_session.add(org)
    db_session.commit()
    db_session.add(OrgMember(org_id=org.id, clerk_user_id="test_user_123", role="owner"))
    db_session.add(
        Template(
            org_id=org.id,
            name="Bulk",
            html_source="<html><body>{{name}} — {{title}}</body></html>",
        )
    )
    db_session.commit()
    return org


def bulk(client, db_session, org, *names):
    tpl = db_session.query(Template).filter_by(org_id=org.id).first()
    body = "name,title\n" + "".join(f"{n},Engines\n" for n in names)
    with patch(DEFER, new_callable=AsyncMock):
        return client.post(
            f"/api/v1/orgs/{org.slug}/credentials/bulk",
            data={"template_id": str(tpl.id)},
            files={"file": ("people.csv", body.encode(), "text/csv")},
        )


def new_key(client, org):
    return client.post(f"/api/v1/orgs/{org.slug}/api-keys", json={"label": "k"})


def new_webhook(client, org):
    return client.post(
        f"/api/v1/orgs/{org.slug}/webhooks", json={"url": "https://example.com/hook"}
    )


# -- CSV batches ---------------------------------------------------------------


def test_community_gets_one_csv_batch_a_month(client, mock_clerk, db_session):
    """One, not zero: the homepage promises a cohort in one upload, and a free
    org has to be able to do exactly that."""
    org = owned_org(db_session, "ent-csv", "community")

    first = bulk(client, db_session, org, "Ada", "Grace")
    assert first.status_code == 200, first.text

    second = bulk(client, db_session, org, "Katherine")
    assert second.status_code == 402, second.text
    error = second.json()["error"]
    # Its own type: a credential-quota refusal is also a 402.
    assert error["type"] == "csv_batch_limit_reached"
    assert error["details"]["limit"] == 1
    assert error["details"]["used"] == 1
    assert "starter" in [u["tier"] for u in error["details"]["upgrades"]]


def test_a_refused_batch_spends_no_quota(client, mock_clerk, db_session):
    org = owned_org(db_session, "ent-csv-quota", "community")
    assert bulk(client, db_session, org, "Ada", "Grace").status_code == 200
    assert bulk(client, db_session, org, "Katherine").status_code == 402

    db_session.expire_all()
    ledger = (
        db_session.query(UsageLedger)
        .filter_by(org_id=org.id, period=UsageLedger.current_period())
        .first()
    )
    assert ledger.credentials_issued == 2


def test_last_months_batch_does_not_count(client, mock_clerk, db_session):
    """A flow, not a stock: the allowance resets with the calendar month."""
    org = owned_org(db_session, "ent-csv-month", "community")
    tpl = db_session.query(Template).filter_by(org_id=org.id).first()
    db_session.add(
        CredentialBatch(
            org_id=org.id,
            template_id=tpl.id,
            csv_filename="old.csv",
            total=1,
            status="completed",
            created_by="test_user_123",
            created_at=month_start() - timedelta(seconds=1),
        )
    )
    db_session.commit()

    assert bulk(client, db_session, org, "Ada").status_code == 200


def test_single_issuance_is_not_a_batch(client, mock_clerk, db_session):
    """The 402 tells a Community org it can still issue singly. That has to be
    true after the batch is spent."""
    org = owned_org(db_session, "ent-csv-single", "community")
    assert bulk(client, db_session, org, "Ada").status_code == 200

    single = client.post(
        f"/api/v1/orgs/{org.slug}/credentials",
        json={"recipient_name": "Grace Hopper", "title": "Compilers"},
    )
    assert single.status_code == 201, single.text


def test_usage_reports_the_csv_meter(client, mock_clerk, db_session):
    org = owned_org(db_session, "ent-csv-usage", "community")
    assert bulk(client, db_session, org, "Ada").status_code == 200

    data = client.get(f"/api/v1/orgs/{org.slug}/usage").json()["data"]
    assert data["csv_batches"] == {"used": 1, "limit": 1, "remaining": 0}

    starter = owned_org(db_session, "ent-csv-usage-s", "starter")
    data = client.get(f"/api/v1/orgs/{starter.slug}/usage").json()["data"]
    assert data["csv_batches"] == {"used": 0, "limit": None, "remaining": None}


# -- artwork -------------------------------------------------------------------


def test_community_cannot_upload_artwork(client, mock_clerk, db_session, store):
    org = owned_org(db_session, "ent-art", "community")

    r = upload(client, org.slug, png_bytes())
    assert r.status_code == 402, r.text
    assert r.json()["error"]["type"] == "plan_feature_required"
    assert r.json()["error"]["details"]["feature"] == "custom_artwork"
    assert store.objects == {}, "refused upload still wrote to the bucket"


def test_community_can_still_upload_a_logo(client, mock_clerk, db_session, store):
    """Branding, not a certificate design — every plan prints the org's mark."""
    org = owned_org(db_session, "ent-logo", "community")
    r = client.post(
        f"/api/v1/orgs/{org.slug}/logo",
        files={"file": ("logo.png", png_bytes((200, 200)), "image/png")},
    )
    assert r.status_code == 201, r.text


# -- API access ----------------------------------------------------------------


def test_community_cannot_create_api_keys_or_webhooks(client, mock_clerk, db_session):
    org = owned_org(db_session, "ent-api", "community")

    for r in (new_key(client, org), new_webhook(client, org)):
        assert r.status_code == 402, r.text
        assert r.json()["error"]["type"] == "plan_feature_required"
        assert r.json()["error"]["details"]["feature"] == "api_access"


# -- the seam ------------------------------------------------------------------


def test_every_tier_is_granted_what_the_catalog_advertises(
    client, mock_clerk, db_session, store
):
    """The join test. Each tier the public catalog lists is walked through
    every gate, and what the route lets through must be what the row says."""
    rows = client.get("/api/v1/tiers").json()["data"]
    assert {row["key"] for row in rows} == set(BILLING_TIERS)

    for row in rows:
        tier = row["key"]
        org = owned_org(db_session, f"seam-ent-{tier}", tier)

        artwork = upload(client, org.slug, png_bytes()).status_code
        assert artwork == (201 if row["custom_artwork"] else 402), tier

        for r in (new_key(client, org), new_webhook(client, org)):
            assert r.status_code == (200 if row["api_access"] else 402), tier

        limit = get_tier_csv_batch_limit(tier)
        assert row["csv_batch_limit"] == (None if limit == -1 else limit), tier
        attempts = 3 if limit == -1 else limit + 1
        statuses = [bulk(client, db_session, org, f"R{i}").status_code for i in range(attempts)]
        expected = [200] * attempts if limit == -1 else [200] * limit + [402]
        assert statuses == expected, (tier, statuses)


def test_no_tier_advertises_a_capability_it_is_not_granted():
    """The pricing page prints `features` verbatim. The bug this suite exists
    for was a feature line sitting on a tier that the routes treated
    identically to the one below it."""
    for key, info in BILLING_TIERS.items():
        text = " ".join(info["features"]).lower()
        if not info["custom_artwork"]:
            assert "artwork" not in text, key
        if not info["api_access"]:
            assert "api" not in text and "webhook" not in text, key
        if info["csv_batch_limit"] != -1:
            assert "unlimited csv" not in text, key


def test_starter_buys_capabilities_community_is_actually_refused():
    """Starter is sold on capability as well as volume, so every capability it
    names has to be one the API really withholds from Community."""
    community, starter = BILLING_TIERS["community"], BILLING_TIERS["starter"]
    assert not community["custom_artwork"] and starter["custom_artwork"]
    assert not community["api_access"] and starter["api_access"]
    assert community["csv_batch_limit"] != -1 and starter["csv_batch_limit"] == -1


def test_month_start_is_the_first_utc_instant():
    now = datetime(2026, 9, 21, 15, 30, tzinfo=timezone.utc)
    assert month_start(now) == datetime(2026, 9, 1, tzinfo=timezone.utc)
