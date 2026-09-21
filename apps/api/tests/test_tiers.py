"""GET /api/v1/tiers — the public plan catalog.

The pricing page at certforge.intelliforge.tech renders from this rather than
from a table in TypeScript, so that a price and the quota the API actually
grants cannot drift apart. That makes the catalog part of the product's
surface: what it advertises has to be what an org on that tier receives.

It is public on purpose — a signed-out visitor is the whole audience — and it
is deliberately absent from `_build_llms_txt` / `_build_sitemap_xml`, which
describe the legacy product on SITE_URL.
"""

from api.core.config import BILLING_TIERS, get_tier_quota, get_tier_template_limit


def test_the_catalog_needs_no_session(client):
    """No mock_clerk fixture here: the request carries no credentials, and the
    pricing page is rendered for people who do not have an account yet."""
    response = client.get("/api/v1/tiers")
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_every_tier_is_listed_in_display_order(client):
    rows = client.get("/api/v1/tiers").json()["data"]

    assert [row["key"] for row in rows] == ["community", "starter", "growth", "scale"]
    assert len(rows) == len(BILLING_TIERS)
    # A JSON object has no order once it crosses the wire, which is why the
    # table carries an explicit `order` and this asserts the sequence.
    assert [row["name"] for row in rows] == ["Community", "Starter", "Growth", "Scale"]


def test_the_catalog_advertises_what_the_api_grants(client):
    """The join between the pricing page and the enforcement. A price shown
    next to a quota nobody receives is the failure this exists to prevent, so
    both numbers are asserted against the functions the product reads at
    runtime — not against literals copied out of the same table."""
    rows = client.get("/api/v1/tiers").json()["data"]

    for row in rows:
        quota = get_tier_quota(row["key"])
        templates = get_tier_template_limit(row["key"])
        assert row["monthly_quota"] == (None if quota == -1 else quota)
        assert row["template_limit"] == (None if templates == -1 else templates)


def test_unlimited_is_null_not_the_sentinel(client):
    """-1 is ours. A consumer formatting the catalog would otherwise print
    "-1 credentials a month" on the most expensive plan."""
    rows = {row["key"]: row for row in client.get("/api/v1/tiers").json()["data"]}

    assert rows["scale"]["monthly_quota"] is None
    assert rows["scale"]["template_limit"] is None
    assert rows["community"]["monthly_quota"] == 500


def test_prices_are_paise_and_the_free_tier_is_free(client):
    """Money crosses the wire as an integer minor unit with its currency
    beside it. A float here is a rounding bug waiting for a GST calculation."""
    rows = {row["key"]: row for row in client.get("/api/v1/tiers").json()["data"]}

    for row in rows.values():
        assert isinstance(row["price_paise"], int)
        assert row["currency"] == "INR"

    assert rows["community"]["price_paise"] == 0
    assert rows["starter"]["price_paise"] > 0
    # Ascending: a pricing page that lists a cheaper plan to the right of a
    # dearer one is telling a customer something untrue about the ladder.
    prices = [row["price_paise"] for row in client.get("/api/v1/tiers").json()["data"]]
    assert prices == sorted(prices)


def test_every_tier_carries_the_copy_the_page_needs(client):
    """The page renders whatever the API sends. A tier added to the table with
    no tagline or feature list renders as an empty card, and nothing else would
    notice."""
    for row in client.get("/api/v1/tiers").json()["data"]:
        assert row["tagline"].strip(), row["key"]
        assert row["features"], row["key"]
        assert all(feature.strip() for feature in row["features"]), row["key"]
