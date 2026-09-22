"""GET /api/v1/tiers — the public plan catalog.

The pricing page at certforge.intelliforge.tech renders from this rather than
from a table in TypeScript, so that a price and the quota the API actually
grants cannot drift apart. That makes the catalog part of the product's
surface: what it advertises has to be what an org on that tier receives.

It is public on purpose — a signed-out visitor is the whole audience — and it
is deliberately absent from `_build_llms_txt` / `_build_sitemap_xml`, which
describe the legacy product on SITE_URL.
"""

from unittest.mock import patch

from api.core.config import (
    BILLING_TIERS,
    is_known_tier,
    get_tier_quota,
    get_tier_template_limit,
    listed_tiers,
)


def test_the_catalog_needs_no_session(client):
    """No mock_clerk fixture here: the request carries no credentials, and the
    pricing page is rendered for people who do not have an account yet."""
    response = client.get("/api/v1/tiers")
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_every_sellable_tier_is_listed_in_display_order(client):
    rows = client.get("/api/v1/tiers").json()["data"]

    assert [row["key"] for row in rows] == ["community", "pro"]
    assert len(rows) == len(listed_tiers())
    # A JSON object has no order once it crosses the wire, which is why the
    # table carries an explicit `order` and this asserts the sequence.
    assert [row["name"] for row in rows] == ["Community", "Pro"]


def test_a_hand_sold_plan_is_not_on_the_pricing_page(client):
    """Scale is a real tier — the gates read it, an operator can set it — but
    there is no checkout behind it, so a card for it is a button that cannot
    be pressed. `listed` is the only thing that decides this; nothing else
    about the tier changes."""
    rows = client.get("/api/v1/tiers").json()["data"]

    assert "scale" in BILLING_TIERS
    assert BILLING_TIERS["scale"]["listed"] is False
    assert "scale" not in [row["key"] for row in rows]


def test_a_retired_plan_name_resolves_to_what_replaced_it():
    """`get_tier`'s fallback is Community, which is the right answer for a name
    nobody recognises and the wrong one for a name that used to be paid. An org
    still marked Starter is a paying org; handing it the free tier's limits is
    the bug the fallback exists to prevent, in the other direction."""
    assert get_tier_quota("starter") == BILLING_TIERS["pro"]["monthly_quota"]
    assert get_tier_template_limit("starter") == BILLING_TIERS["pro"]["template_limit"]
    assert is_known_tier("starter")
    # Still Community for something genuinely unknown.
    assert get_tier_quota("enterprise") == BILLING_TIERS["community"]["monthly_quota"]
    assert not is_known_tier("enterprise")


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

    assert rows["community"]["monthly_quota"] == 50
    assert all(row["monthly_quota"] != -1 for row in rows.values())

    # Every unlimited row is hand-sold today, so listing Scale is how the
    # rendering stays covered. Without this the guard would pass on a catalog
    # that simply has no -1 in it, and go quiet the day an unlimited plan is
    # sold again — which is exactly when it is needed.
    scale = dict(BILLING_TIERS["scale"], listed=True)
    with patch.dict(BILLING_TIERS, {"scale": scale}):
        listed = {row["key"]: row for row in client.get("/api/v1/tiers").json()["data"]}

    assert listed["scale"]["monthly_quota"] is None
    assert listed["scale"]["template_limit"] is None


def test_prices_are_paise_and_the_free_tier_is_free(client):
    """Money crosses the wire as an integer minor unit with its currency
    beside it. A float here is a rounding bug waiting for a GST calculation."""
    rows = {row["key"]: row for row in client.get("/api/v1/tiers").json()["data"]}

    for row in rows.values():
        assert isinstance(row["price_paise"], int)
        assert row["currency"] == "INR"

    assert rows["community"]["price_paise"] == 0
    assert rows["pro"]["price_paise"] > 0
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
