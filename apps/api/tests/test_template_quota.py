"""The template allowance: a stock, not a monthly flow.

A tier says how many custom templates an organization may *hold*. It is checked
against the live row count rather than a counter, so deleting a template frees
the slot and there is nothing to drift out of step with the table it gates.

The gate covered here replaced a flat 403 for `community`, which gave the free
tier zero templates and — billing being mocked — gave every other tier zero
too, because no org could reach one. Community now holds 1.

The rule that matters most is that all three doors are locked: create, import a
global template, and read a design with the model each insert a Template for an
org, and a limit enforced on one of three is not a limit.
"""

from unittest.mock import patch

import pytest

from api.core.config import BILLING_TIERS, get_tier_template_limit
from api.core.principal import hash_api_key
from api.models.api_key import ApiKey
from api.models.organization import Organization
from api.models.template import Template
from api.models.usage import UsageLedger

# Siblings, not package imports: tests/ has no __init__.py. Reused rather than
# copied so the `store` fixture's patch targets exist in exactly one place.
from test_template_assets import (  # noqa: E402
    auth,
    key_for,
    png_bytes,
    store,  # noqa: F401 - fixture, used by argument name
    upload,
)
from test_template_from_image import (  # noqa: E402
    FakeResponse,
    a_layout,
    from_image,
    stub_vision,
)

SAFE_HTML = "<html><body><h1>{{name}}</h1></body></html>"


def org_on(db_session, slug: str, tier: str) -> Organization:
    org = Organization(slug=slug, name=slug.title(), tier=tier, monthly_quota=500)
    db_session.add(org)
    db_session.commit()
    db_session.add(ApiKey(org_id=org.id, key_hash=hash_api_key(key_for(slug)), label="k"))
    db_session.commit()
    return org


def create(client, slug, name="Template"):
    return client.post(
        f"/api/v1/orgs/{slug}/templates",
        headers=auth(slug),
        json={"name": name, "html_source": SAFE_HTML},
    )


@pytest.fixture(autouse=True)
def vision_key():
    """The from-image route answers 503 before anything else without one."""
    with (
        patch("api.services.vision.VISION_AVAILABLE", True),
        patch("api.services.vision.ANTHROPIC_API_KEY", "sk-ant-test"),
    ):
        yield


# -- the limit itself ---------------------------------------------------------


def test_community_holds_one_template_and_refuses_the_second(client, db_session):
    org_on(db_session, "quota-free", "community")

    assert create(client, "quota-free", name="First").status_code == 201

    refused = create(client, "quota-free", name="Second")
    assert refused.status_code == 402, refused.text

    error = refused.json()["error"]
    # 402 is also what a credential quota refusal returns. A client that shows
    # different copy for the two cannot tell them apart by status alone.
    assert error["type"] == "template_limit_reached"
    assert error["details"]["limit"] == 1
    assert error["details"]["tier"] == "community"
    # The body has to name a way out: checkout is still mocked, so the only
    # door is support, and the message is where a customer learns that.
    assert [u["tier"] for u in error["details"]["upgrades"]] == [
        "starter",
        "growth",
        "scale",
    ]


def test_a_larger_tier_holds_more(client, db_session):
    """Asserted through get_tier_template_limit rather than the literal, so a
    tier-table edit moves the test with it instead of breaking it."""
    org_on(db_session, "quota-starter", "starter")
    limit = get_tier_template_limit("starter")

    for n in range(limit):
        assert create(client, "quota-starter", name=f"T{n}").status_code == 201

    assert create(client, "quota-starter", name="One too many").status_code == 402


def test_scale_is_unlimited(client, db_session):
    """-1 is the sentinel, and it has to mean "skip the check" rather than
    "the limit is -1", which would refuse the very first template."""
    org_on(db_session, "quota-scale", "scale")

    for n in range(6):
        assert create(client, "quota-scale", name=f"T{n}").status_code == 201


def test_a_tier_the_table_does_not_know_falls_back_to_community(client, db_session):
    """`organizations.tier` is free text and the Razorpay webhook has written
    values BILLING_TIERS never had. Such a row must read as the free tier
    everywhere at once, not as paid by one lookup and free by another."""
    org_on(db_session, "quota-bogus", "enterprise-plus")

    assert create(client, "quota-bogus", name="First").status_code == 201
    refused = create(client, "quota-bogus", name="Second")
    assert refused.status_code == 402
    assert refused.json()["error"]["details"]["limit"] == 1


def test_deleting_a_template_frees_the_slot(client, db_session):
    """The whole reason the gate counts rows instead of keeping a monthly
    counter: an allowance on a stock has to move both ways."""
    org_on(db_session, "quota-delete", "community")

    first = create(client, "quota-delete", name="First")
    assert first.status_code == 201
    template_id = first.json()["data"]["id"]

    assert create(client, "quota-delete", name="Second").status_code == 402

    dropped = client.delete(
        f"/api/v1/orgs/quota-delete/templates/{template_id}",
        headers=auth("quota-delete"),
    )
    assert dropped.status_code == 200, dropped.text

    assert create(client, "quota-delete", name="Second").status_code == 201


def test_a_seeded_global_template_does_not_count_against_an_org(client, db_session):
    """Global templates have org_id = None and every org renders from them.
    Counting them would put every new org over Community's limit on day one."""
    db_session.add(
        Template(
            org_id=None,
            name="Global",
            html_source=SAFE_HTML,
            variables=["name"],
            is_default=True,
        )
    )
    db_session.commit()
    org_on(db_session, "quota-global", "community")

    assert create(client, "quota-global", name="Mine").status_code == 201


# -- the other two doors ------------------------------------------------------


def test_importing_a_global_template_is_gated_too(client, db_session):
    """An imported template is a copy the org holds, not a reference to one."""
    source = Template(
        org_id=None,
        name="Global",
        html_source=SAFE_HTML,
        variables=["name"],
        is_default=True,
    )
    db_session.add(source)
    db_session.commit()
    source_id = str(source.id)

    org_on(db_session, "quota-import", "community")
    assert create(client, "quota-import", name="First").status_code == 201

    refused = client.post(
        f"/api/v1/orgs/quota-import/templates/import/{source_id}",
        headers=auth("quota-import"),
    )
    assert refused.status_code == 402, refused.text
    assert refused.json()["error"]["type"] == "template_limit_reached"


def test_an_unknown_global_template_still_reads_as_a_404(client, db_session):
    """Order matters: gate after the 404, or a bad id at the limit reports a
    billing problem for a template that does not exist."""
    org_on(db_session, "quota-import-404", "community")
    assert create(client, "quota-import-404", name="First").status_code == 201

    missing = client.post(
        "/api/v1/orgs/quota-import-404/templates/import/"
        "00000000-0000-0000-0000-000000000000",
        headers=auth("quota-import-404"),
    )
    assert missing.status_code == 404


def test_from_image_is_gated_before_it_spends_a_vision_import(client, db_session, store):
    """The model call costs real money. An org that could not keep the result
    has to be refused before the meter moves — the meter is a cost fuse, and a
    request refused before the call cost nothing."""
    org = org_on(db_session, "quota-vision", "community")
    asset_id = upload(client, "quota-vision", png_bytes()).json()["data"]["id"]
    assert create(client, "quota-vision", name="First").status_code == 201

    with stub_vision(FakeResponse(a_layout())):
        refused = from_image(client, "quota-vision", asset_id, name="Read this")

    assert refused.status_code == 402, refused.text
    assert refused.json()["error"]["type"] == "template_limit_reached"

    ledger = (
        db_session.query(UsageLedger)
        .filter_by(org_id=org.id, period=UsageLedger.current_period())
        .first()
    )
    assert ledger is None or ledger.vision_imports == 0


# -- the seam -----------------------------------------------------------------


def test_every_tier_in_the_catalog_is_one_the_gate_can_enforce(client, db_session):
    """The join test.

    BILLING_TIERS is read by the gate, by the usage endpoint, and by the public
    /tiers catalog the pricing page renders. This walks every tier the catalog
    advertises through the gate itself, so a tier that exists on the pricing
    page but grants a different number than it advertises fails here rather
    than in a support ticket.
    """
    for tier, info in BILLING_TIERS.items():
        limit = info["template_limit"]
        slug = f"seam-{tier}"
        org_on(db_session, slug, tier)

        # One past the advertised limit, capped so "unlimited" stays quick.
        attempts = 4 if limit == -1 else limit + 1
        statuses = [create(client, slug, name=f"T{n}").status_code for n in range(attempts)]

        if limit == -1:
            assert statuses == [201] * attempts, f"{tier} advertises unlimited"
        else:
            assert statuses == [201] * limit + [402], (
                f"{tier} advertises {limit} templates but enforced {statuses}"
            )
