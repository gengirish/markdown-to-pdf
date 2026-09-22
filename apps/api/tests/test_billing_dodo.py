"""Dodo Payments: checkout, the portal, and what a webhook may do to a tier.

Webhooks here are signed for real, in Standard Webhooks format, with a test
key, so the handler's own verification runs rather than being patched out. The
Dodo *client* (checkout, portal) is faked at `services/billing._client`, the
one place it is constructed.

The rule most of these tests exist for: a tier is derived from the governing
subscription's current state, never from the event's name, and only the
governing subscription may move it. See docs/dodo-payments-integration-plan.md.
"""

import base64
import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from standardwebhooks import Webhook

from api.core import config
from api.core.config import BILLING_TIERS, get_tier_quota, get_tier_template_limit
from api.core.principal import hash_api_key
from api.index import app
from api.models.api_key import ApiKey
from api.models.billing_event import BillingEvent
from api.services.issuance import effective_credential_quota
from api.models.organization import Organization, OrgMember
from api.services import billing

# Siblings, not package imports: tests/ has no __init__.py.
from test_template_assets import auth, key_for  # noqa: E402

WEBHOOK_KEY = "whsec_" + base64.b64encode(b"certforge-test-webhook-key-32byt").decode()
OTHER_KEY = "whsec_" + base64.b64encode(b"somebody-elses-webhook-key-32byt").decode()

#: One product per paid tier, derived from the table so a tier added to
#: BILLING_TIERS is covered by the join test below without editing this file.
PRODUCTS = {
    tier: f"pdt_test_{tier}"
    for tier, info in BILLING_TIERS.items()
    if info["price_paise"] > 0
}

SAFE_HTML = "<html><body><h1>{{name}}</h1></body></html>"


@pytest.fixture(autouse=True)
def dodo_configured():
    with (
        patch.object(config, "DODO_PAYMENTS_WEBHOOK_KEY", WEBHOOK_KEY),
        patch.object(config, "DODO_PAYMENTS_API_KEY", "dodo_test_key"),
        patch.dict(config.DODO_PRODUCTS, PRODUCTS),
    ):
        yield


# ── arrangement ────────────────────────────────────────────────────────────


def new_org(db_session, *, tier="community", role="owner", with_key=False, **fields) -> Organization:
    slug = f"dodo-{uuid.uuid4().hex[:10]}"
    org = Organization(slug=slug, name="Dodo Org", tier=tier, **fields)
    db_session.add(org)
    db_session.commit()
    if role:
        db_session.add(OrgMember(org_id=org.id, clerk_user_id="test_user_123", role=role))
    if with_key:
        db_session.add(ApiKey(org_id=org.id, key_hash=hash_api_key(key_for(slug)), label="k"))
    db_session.commit()
    return org


def sid(org, name="sub_A") -> str:
    """A subscription id unique to this org. The test database lives for the
    whole session, and a shared literal lets one test's event resolve to
    another test's org through the subscription-id fallback."""
    return f"{name}_{org.id.hex[:12]}"


def subscription(org, *, sub_id="sub_A", status="active", tier="pro",
                 product=None, cancel_at_next=False, next_billing_in_days=30,
                 customer_id="cus_1", metadata=True) -> dict:
    return {
        "payload_type": "Subscription",
        "subscription_id": sid(org, sub_id),
        "status": status,
        "product_id": product or PRODUCTS[tier],
        "cancel_at_next_billing_date": cancel_at_next,
        "next_billing_date": (
            datetime.now(timezone.utc) + timedelta(days=next_billing_in_days)
        ).isoformat(),
        "customer": {"customer_id": customer_id, "email": "owner@example.com", "name": "Owner"},
        "metadata": {"org_id": str(org.id)} if metadata else {},
    }


def signed(event_type: str, data: dict, *, webhook_id=None, key=WEBHOOK_KEY):
    body = json.dumps({
        "business_id": "bus_test",
        "type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    })
    webhook_id = webhook_id or f"evt_{uuid.uuid4().hex}"
    now = datetime.now(timezone.utc)
    headers = {
        "webhook-id": webhook_id,
        "webhook-timestamp": str(int(now.timestamp())),
        "webhook-signature": Webhook(key).sign(webhook_id, now, body),
        "content-type": "application/json",
    }
    return body, headers


def deliver(client, event_type, data, **kwargs):
    body, headers = signed(event_type, data, **kwargs)
    return client.post("/api/v1/webhooks/dodo", content=body.encode(), headers=headers)


def reloaded(db_session, org) -> Organization:
    db_session.expire_all()
    return db_session.get(Organization, org.id)


def events_for(db_session, org) -> list[BillingEvent]:
    db_session.expire_all()
    return db_session.query(BillingEvent).filter_by(org_id=org.id).all()


# ── signing ────────────────────────────────────────────────────────────────


def test_a_correctly_signed_activation_grants_the_tier(client, db_session):
    org = new_org(db_session)
    res = deliver(client, "subscription.active", subscription(org))
    assert res.status_code == 200, res.text
    assert res.json()["data"]["outcome"] == "applied"

    org = reloaded(db_session, org)
    assert org.tier == "pro"
    assert org.dodo_subscription_id == sid(org, "sub_A")
    assert org.dodo_customer_id == "cus_1"
    assert org.subscription_status == "active"


def test_a_delivery_signed_with_another_key_is_401_and_changes_nothing(client, db_session):
    org = new_org(db_session)
    res = deliver(client, "subscription.active", subscription(org), key=OTHER_KEY)
    assert res.status_code == 401
    assert reloaded(db_session, org).tier == "community"


def test_an_unconfigured_webhook_key_rejects_everything(client, db_session):
    org = new_org(db_session)
    body, headers = signed("subscription.active", subscription(org))
    with patch.object(config, "DODO_PAYMENTS_WEBHOOK_KEY", ""):
        res = client.post("/api/v1/webhooks/dodo", content=body.encode(), headers=headers)
    assert res.status_code == 503
    assert reloaded(db_session, org).tier == "community"


def test_a_body_reserialized_after_signing_is_rejected(client, db_session):
    """Verification is over the exact bytes. A handler that parsed JSON before
    verifying and re-serialized it would accept this; ours must not."""
    org = new_org(db_session)
    body, headers = signed("subscription.active", subscription(org))
    reformatted = json.dumps(json.loads(body), indent=2)
    res = client.post("/api/v1/webhooks/dodo", content=reformatted.encode(), headers=headers)
    assert res.status_code == 401


def test_missing_or_malformed_signature_headers_are_401_not_500(client, db_session):
    org = new_org(db_session)
    body, headers = signed("subscription.active", subscription(org))

    missing = {k: v for k, v in headers.items() if k != "webhook-signature"}
    assert client.post("/api/v1/webhooks/dodo", content=body.encode(), headers=missing).status_code == 401

    # No comma: standardwebhooks raises ValueError here, not its own error type.
    garbled = {**headers, "webhook-signature": "garbage"}
    assert client.post("/api/v1/webhooks/dodo", content=body.encode(), headers=garbled).status_code == 401


def test_a_delivery_older_than_five_minutes_is_rejected(client, db_session):
    org = new_org(db_session)
    body = json.dumps({"type": "subscription.active", "data": subscription(org)})
    old = datetime.now(timezone.utc) - timedelta(minutes=10)
    headers = {
        "webhook-id": "evt_old",
        "webhook-timestamp": str(int(old.timestamp())),
        "webhook-signature": Webhook(WEBHOOK_KEY).sign("evt_old", old, body),
    }
    assert client.post("/api/v1/webhooks/dodo", content=body.encode(), headers=headers).status_code == 401


# ── idempotency ────────────────────────────────────────────────────────────


def test_the_same_webhook_id_twice_applies_once(client, db_session):
    org = new_org(db_session)
    data = subscription(org)
    first = deliver(client, "subscription.active", data, webhook_id="evt_dup")
    second = deliver(client, "subscription.active", data, webhook_id="evt_dup")

    assert first.json()["data"]["status"] == "received"
    assert second.json()["data"]["status"] == "duplicate"
    assert len(events_for(db_session, org)) == 1


def test_a_failure_while_applying_rolls_back_the_claim_so_the_retry_applies(db_session):
    """The claim and the change share one transaction. Committed separately,
    the failed attempt would leave its claim behind and every retry would be
    skipped as a duplicate — the event lost for good."""
    org = new_org(db_session)
    data = subscription(org)
    original = billing.reconcile_subscription

    def explode(session, payload, **kw):
        original(session, payload, **kw)  # mutate, then fail before commit
        raise RuntimeError("database went away")

    with TestClient(app, raise_server_exceptions=False) as client:
        with patch.object(billing, "reconcile_subscription", explode):
            failed = deliver(client, "subscription.active", data, webhook_id="evt_retry")
        assert failed.status_code == 500
        assert events_for(db_session, org) == []
        assert reloaded(db_session, org).tier == "community"

        retried = deliver(client, "subscription.active", data, webhook_id="evt_retry")
    assert retried.status_code == 200
    assert retried.json()["data"]["outcome"] == "applied"
    assert reloaded(db_session, org).tier == "pro"


# ── mapping ────────────────────────────────────────────────────────────────


def test_an_unknown_product_never_guesses_a_tier(client, db_session):
    """The Razorpay stub wrote a tier on every activation because it had
    nothing to map from. An unmapped product must leave the org alone."""
    org = new_org(db_session)
    res = deliver(client, "subscription.active", subscription(org, product="pdt_nobody_sells"))
    assert res.status_code == 200
    assert res.json()["data"]["outcome"] == "ignored_unknown_product"

    org = reloaded(db_session, org)
    assert org.tier == "community"
    assert org.dodo_subscription_id is None
    assert events_for(db_session, org)[0].outcome == "ignored_unknown_product"


def test_an_unknown_product_still_revokes(client, db_session):
    """Revocation goes to Community whatever the product, so a misconfigured
    product id can never keep a lapsed org on a paid plan."""
    org = new_org(db_session)
    deliver(client, "subscription.active", subscription(org))
    deliver(client, "subscription.expired",
            subscription(org, status="expired", product="pdt_renamed_since"))
    assert reloaded(db_session, org).tier == "community"


@pytest.mark.parametrize("tier", sorted(PRODUCTS))
def test_the_granted_quota_is_the_tier_tables(client, db_session, tier):
    org = new_org(db_session)
    deliver(client, "subscription.active", subscription(org, tier=tier))
    org = reloaded(db_session, org)
    assert org.tier == tier
    # What binds is the effective limit; monthly_quota is kept equal until W4.
    assert effective_credential_quota(org) == get_tier_quota(tier)
    assert org.monthly_quota == get_tier_quota(tier)


def test_a_non_subscription_event_is_recorded_and_changes_nothing(client, db_session):
    org = new_org(db_session)
    res = deliver(client, "payment.succeeded", {"payment_id": "pay_1", "metadata": {"org_id": str(org.id)}})
    assert res.status_code == 200
    assert res.json()["data"]["outcome"] == "ignored_event_type"
    assert reloaded(db_session, org).tier == "community"


# ── lifecycle ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("status", ["on_hold", "past_due"])
def test_a_failed_renewal_keeps_the_paid_tier_while_dodo_retries(client, db_session, status):
    org = new_org(db_session)
    deliver(client, "subscription.active", subscription(org))
    deliver(client, f"subscription.{status}", subscription(org, status=status))
    org = reloaded(db_session, org)
    assert org.tier == "pro"
    assert org.subscription_status == status


def test_cancel_at_period_end_keeps_the_tier_until_expiry(client, db_session):
    org = new_org(db_session)
    deliver(client, "subscription.active", subscription(org))
    deliver(client, "subscription.cancelled",
            subscription(org, status="cancelled", cancel_at_next=True))
    org = reloaded(db_session, org)
    assert org.tier == "pro"
    assert org.cancel_at_period_end is True

    deliver(client, "subscription.expired", subscription(org, status="expired"))
    assert reloaded(db_session, org).tier == "community"


def test_cancel_at_period_end_whose_period_has_passed_revokes(client, db_session):
    """A retry of the cancellation after the period ended must not re-grant."""
    org = new_org(db_session)
    deliver(client, "subscription.active", subscription(org))
    deliver(client, "subscription.cancelled",
            subscription(org, status="cancelled", cancel_at_next=True, next_billing_in_days=-1))
    assert reloaded(db_session, org).tier == "community"


@pytest.mark.parametrize("status", ["cancelled", "failed", "expired", "paused"])
def test_every_ending_returns_the_org_to_community(client, db_session, status):
    org = new_org(db_session)
    deliver(client, "subscription.active", subscription(org, tier="scale"))
    deliver(client, f"subscription.{status}", subscription(org, status=status, tier="scale"))
    org = reloaded(db_session, org)
    assert org.tier == "community"
    assert effective_credential_quota(org) == get_tier_quota("community")
    assert org.monthly_quota == get_tier_quota("community")


def test_a_plan_change_moves_the_tier_by_product(client, db_session):
    org = new_org(db_session)
    deliver(client, "subscription.active", subscription(org, tier="pro"))
    deliver(client, "subscription.plan_changed", subscription(org, tier="scale"))
    assert reloaded(db_session, org).tier == "scale"


# ── ordering: only the governing subscription moves an org ─────────────────


def test_an_old_subscriptions_late_expiry_does_not_downgrade_a_resubscribed_org(client, db_session):
    """The out-of-order case, and the likeliest way this breaks in production:
    cancel A at period end, subscribe B, then A's `expired` arrives."""
    org = new_org(db_session)
    deliver(client, "subscription.active", subscription(org, sub_id="sub_A"))
    deliver(client, "subscription.cancelled",
            subscription(org, sub_id="sub_A", status="cancelled", cancel_at_next=True))
    deliver(client, "subscription.active", subscription(org, sub_id="sub_B", tier="scale"))
    late = deliver(client, "subscription.expired",
                   subscription(org, sub_id="sub_A", status="expired"))

    assert late.json()["data"]["outcome"] == "ignored_not_current"
    org = reloaded(db_session, org)
    assert org.tier == "scale"
    assert org.dodo_subscription_id == sid(org, "sub_B")


def test_a_terminal_subscription_never_grants_again(client, db_session):
    org = new_org(db_session)
    deliver(client, "subscription.active", subscription(org))
    deliver(client, "subscription.expired", subscription(org, status="expired"))
    stale = deliver(client, "subscription.active", subscription(org))
    assert stale.json()["data"]["outcome"] == "ignored_stale"
    assert reloaded(db_session, org).tier == "community"


def test_a_second_live_subscription_does_not_take_over(client, db_session):
    """A double checkout. Logged for a person to refund; the first stays."""
    org = new_org(db_session)
    deliver(client, "subscription.active", subscription(org, sub_id="sub_A"))
    second = deliver(client, "subscription.active",
                     subscription(org, sub_id="sub_B", tier="scale"))
    assert second.json()["data"]["outcome"] == "ignored_not_current"
    org = reloaded(db_session, org)
    assert org.tier == "pro"
    assert org.dodo_subscription_id == sid(org, "sub_A")


def test_an_org_whose_tier_was_set_by_hand_is_not_touched_by_a_stray_event(client, db_session):
    org = new_org(db_session, tier="scale")
    res = deliver(client, "subscription.expired",
                  subscription(org, sub_id="sub_stray", status="expired"))
    assert res.json()["data"]["outcome"] == "ignored_not_current"
    assert reloaded(db_session, org).tier == "scale"


def test_an_event_naming_no_known_org_is_recorded_as_such(client, db_session):
    data = {"subscription_id": "sub_orphan", "status": "active",
            "product_id": PRODUCTS["pro"], "metadata": {}}
    res = deliver(client, "subscription.active", data)
    assert res.status_code == 200
    assert res.json()["data"]["outcome"] == "ignored_unknown_org"


def test_an_event_without_metadata_is_matched_by_subscription_id(client, db_session):
    org = new_org(db_session)
    deliver(client, "subscription.active", subscription(org))
    deliver(client, "subscription.expired", subscription(org, status="expired", metadata=False))
    assert reloaded(db_session, org).tier == "community"


# ── checkout ───────────────────────────────────────────────────────────────


class FakeDodo:
    def __init__(self):
        self.checkout_calls = []
        self.portal_calls = []
        self.checkout_sessions = SimpleNamespace(create=self._create_checkout)
        self.customers = SimpleNamespace(
            customer_portal=SimpleNamespace(create=self._create_portal)
        )

    def _create_checkout(self, **kwargs):
        self.checkout_calls.append(kwargs)
        return SimpleNamespace(checkout_url="https://test.checkout.dodopayments.com/cs_1",
                               session_id="cs_1")

    def _create_portal(self, customer_id, **kwargs):
        self.portal_calls.append((customer_id, kwargs))
        return SimpleNamespace(link="https://customer.dodopayments.com/portal/abc")


@pytest.fixture
def fake_dodo():
    fake = FakeDodo()
    with patch.object(billing, "_client", lambda: fake):
        yield fake


def checkout(client, org, tier="pro"):
    return client.post(f"/api/v1/orgs/{org.slug}/checkout", json={"tier": tier})


def test_checkout_returns_the_hosted_url_and_tags_the_org(client, mock_clerk, db_session, fake_dodo):
    org = new_org(db_session)
    res = checkout(client, org)
    assert res.status_code == 200, res.text
    assert res.json()["data"]["checkout_url"].startswith("https://test.checkout.dodopayments.com/")

    call = fake_dodo.checkout_calls[0]
    assert call["product_cart"] == [{"product_id": PRODUCTS["pro"], "quantity": 1}]
    assert call["metadata"]["org_id"] == str(org.id)
    assert f"/org/{org.slug}/dashboard" in call["return_url"]
    # mock_clerk's session carries no email, so Dodo's page collects it.
    assert "customer" not in call
    # And checking out grants nothing.
    assert reloaded(db_session, org).tier == "community"


def test_checkout_reuses_the_orgs_dodo_customer(client, mock_clerk, db_session, fake_dodo):
    org = new_org(db_session, dodo_customer_id="cus_existing")
    checkout(client, org)
    assert fake_dodo.checkout_calls[0]["customer"] == {"customer_id": "cus_existing"}


@pytest.mark.parametrize("role", [None, "admin", "issuer"])
def test_only_an_owner_can_start_a_subscription(client, mock_clerk, db_session, fake_dodo, role):
    org = new_org(db_session, role=role)
    assert checkout(client, org).status_code == 403
    assert fake_dodo.checkout_calls == []


@pytest.mark.parametrize("tier", ["community", "enterprise", None])
def test_checkout_refuses_a_tier_that_is_not_for_sale(client, mock_clerk, db_session, fake_dodo, tier):
    org = new_org(db_session)
    res = checkout(client, org, tier=tier)
    assert res.status_code == 400
    assert res.json()["error"]["type"] == "invalid_tier"


def test_checkout_on_a_retired_plan_name_buys_what_replaced_it(
    client, mock_clerk, db_session, fake_dodo
):
    """A client can hold a retired name for a long time — a pricing page loaded
    before the change, a saved link, a support thread. Starter is sold as Pro
    now, so the checkout is for Pro's product rather than a 400 telling a
    paying customer the plan they were about to buy does not exist."""
    org = new_org(db_session)
    res = checkout(client, org, tier="starter")

    assert res.status_code == 200
    assert res.json()["data"]["tier"] == "pro"
    assert fake_dodo.checkout_calls[-1]["product_cart"] == [
        {"product_id": PRODUCTS["pro"], "quantity": 1}
    ]


def test_checkout_without_an_api_key_is_503_and_carries_no_url(client, mock_clerk, db_session):
    org = new_org(db_session)
    with patch.object(config, "DODO_PAYMENTS_API_KEY", ""):
        res = checkout(client, org)
    assert res.status_code == 503
    assert res.json()["error"]["type"] == "billing_unavailable"
    assert res.json()["data"] is None


def test_checkout_for_a_tier_with_no_product_configured_is_503(client, mock_clerk, db_session, fake_dodo):
    org = new_org(db_session)
    with patch.dict(config.DODO_PRODUCTS, {"pro": ""}):
        assert checkout(client, org).status_code == 503
    assert fake_dodo.checkout_calls == []


def test_checkout_while_subscribed_is_409(client, mock_clerk, db_session, fake_dodo):
    org = new_org(db_session)
    deliver(client, "subscription.active", subscription(org))
    res = checkout(client, org, tier="scale")
    assert res.status_code == 409
    assert res.json()["error"]["type"] == "already_subscribed"


def test_checkout_after_cancelling_at_period_end_is_allowed(client, mock_clerk, db_session, fake_dodo):
    org = new_org(db_session)
    deliver(client, "subscription.active", subscription(org))
    deliver(client, "subscription.cancelled",
            subscription(org, status="cancelled", cancel_at_next=True))
    assert checkout(client, org, tier="scale").status_code == 200


def test_a_provider_failure_is_502(client, mock_clerk, db_session, fake_dodo):
    import httpx
    from dodopayments import APIConnectionError

    def refuse(**kwargs):
        raise APIConnectionError(request=httpx.Request("POST", "https://test.dodopayments.com"))

    fake_dodo.checkout_sessions.create = refuse
    org = new_org(db_session)
    res = checkout(client, org)
    assert res.status_code == 502
    assert res.json()["error"]["type"] == "billing_provider_error"


# ── portal and usage ───────────────────────────────────────────────────────


def test_the_portal_needs_a_billing_account(client, mock_clerk, db_session, fake_dodo):
    org = new_org(db_session)
    res = client.post(f"/api/v1/orgs/{org.slug}/billing/portal")
    assert res.status_code == 409
    assert res.json()["error"]["type"] == "no_billing_account"


def test_the_portal_link_is_minted_for_the_orgs_customer(client, mock_clerk, db_session, fake_dodo):
    org = new_org(db_session, dodo_customer_id="cus_portal")
    res = client.post(f"/api/v1/orgs/{org.slug}/billing/portal")
    assert res.status_code == 200
    assert res.json()["data"]["portal_url"].startswith("https://customer.dodopayments.com/")
    assert fake_dodo.portal_calls[0][0] == "cus_portal"


def test_the_portal_is_owner_only(client, mock_clerk, db_session, fake_dodo):
    org = new_org(db_session, role="admin", dodo_customer_id="cus_portal")
    assert client.post(f"/api/v1/orgs/{org.slug}/billing/portal").status_code == 403


def test_usage_reports_the_governing_subscription(client, mock_clerk, db_session):
    org = new_org(db_session)
    assert client.get(f"/api/v1/orgs/{org.slug}/usage").json()["data"]["subscription"] is None

    deliver(client, "subscription.active", subscription(org, cancel_at_next=True))
    summary = client.get(f"/api/v1/orgs/{org.slug}/usage").json()["data"]["subscription"]
    assert summary["status"] == "active"
    assert summary["cancel_at_period_end"] is True
    assert summary["manageable"] is True
    assert summary["current_period_end"]


# ── the join ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("tier", sorted(PRODUCTS))
def test_a_paid_webhook_reaches_the_template_gate(client, db_session, tier):
    """Dodo product → tier_for_product → BILLING_TIERS → the gate, end to end.

    Iterates the tier table, so a tier with no product mapping, or a webhook
    producing a tier the table does not know, fails here the day it appears.
    """
    org = new_org(db_session, role=None, with_key=True)
    assert deliver(client, "subscription.active", subscription(org, tier=tier)).status_code == 200

    def create(i):
        return client.post(
            f"/api/v1/orgs/{org.slug}/templates",
            headers=auth(org.slug),
            json={"name": f"T{i}", "html_source": SAFE_HTML},
        )

    limit = get_tier_template_limit(tier)
    allowed = limit if limit != -1 else get_tier_template_limit("community") + 3
    for i in range(allowed):
        assert create(i).status_code == 201, f"{tier}: template {i + 1} of {allowed}"

    if limit != -1:
        refused = create(allowed)
        assert refused.status_code == 402
        assert refused.json()["error"]["type"] == "template_limit_reached"


# ── the operator quota plan's Decision 4 ────────────────────────────────────

def test_a_dodo_plan_change_clears_an_operator_override_and_logs_it(client, db_session):
    """Dodo moves tiers through change_tier(), so a real plan change removes
    an operator's override and says so in the change log."""
    from api.models.quota_change import CredentialQuotaChange

    org = new_org(db_session, credential_quota_override=1000)
    deliver(client, "subscription.active", subscription(org, tier="scale"))
    org = reloaded(db_session, org)
    assert org.tier == "scale"
    assert org.credential_quota_override is None
    assert effective_credential_quota(org) == get_tier_quota("scale")

    rows = db_session.query(CredentialQuotaChange).filter_by(org_id=org.id).all()
    assert [(r.actor, r.previous_override, r.new_override) for r in rows] == [
        ("dodo-webhook", 1000, None)
    ]


def test_a_redelivered_dodo_event_keeps_an_override_set_since(client, db_session):
    """Dodo redelivers. Once the org is on Growth, an override an operator sets
    must survive the same subscription's next `active` for the same tier."""
    from api.models.quota_change import CredentialQuotaChange

    org = new_org(db_session)
    deliver(client, "subscription.active", subscription(org, tier="scale"))
    org = reloaded(db_session, org)
    org.credential_quota_override = 9000
    db_session.commit()

    deliver(client, "subscription.renewed", subscription(org, tier="scale"))
    org = reloaded(db_session, org)
    assert org.credential_quota_override == 9000
    assert db_session.query(CredentialQuotaChange).filter_by(org_id=org.id).count() == 0
