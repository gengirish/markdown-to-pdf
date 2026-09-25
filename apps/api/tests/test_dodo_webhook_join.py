"""The join between Dodo and this API, and recovering a delivery that never came.

The first live payment succeeded and the org stayed on Community. Both halves
were correct: the handler verified and applied webhooks (test_billing_dodo.py
proves it), and a webhook endpoint existed — in test mode. A live payment
notifies live-mode endpoints only, so nothing ever reached the handler, and no
test noticed because none of them looked at the two together.

`webhook_readiness` is that look; `release._dodo_webhook_ready` is where it is
enforced; `api.reconcile_subscription` repairs an org the gap already cost.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api import release
from api import reconcile_subscription as recon
from api.core import config
from api.models.billing_event import BillingEvent
from api.services import billing

# Siblings, not package imports: tests/ has no __init__.py. `dodo_configured`
# is autouse there and becomes autouse here by being imported.
from test_billing_dodo import (  # noqa: F401
    PRODUCTS,
    WEBHOOK_KEY,
    dodo_configured,
    new_org,
    reloaded,
    subscription,
)

OTHER_SECRET = "whsec_c29tZWJvZHktZWxzZXMtd2ViaG9vay1rZXktMzJieXQ="


def endpoint(*, id="ep_1", url=None, disabled=False, filter_types=(), secret=WEBHOOK_KEY):
    return SimpleNamespace(
        id=id, url=url or billing.webhook_url(), disabled=disabled,
        filter_types=list(filter_types), secret=secret,
    )


class FakeDodo:
    """Endpoints are held per mode, as Dodo holds them: a client built for
    live mode sees live endpoints only. That is the whole incident."""

    def __init__(self, test=(), live=()):
        self.by_mode = {"test_mode": list(test), "live_mode": list(live)}

    def client(self):
        endpoints = self.by_mode[config.DODO_PAYMENTS_ENVIRONMENT]
        by_id = {e.id: e for e in endpoints}
        return SimpleNamespace(webhooks=SimpleNamespace(
            list=lambda: list(endpoints),
            retrieve_secret=lambda webhook_id: SimpleNamespace(secret=by_id[webhook_id].secret),
        ))


@pytest.fixture
def dodo():
    def install(*, mode="live_mode", test=(), live=()):
        fake = FakeDodo(test=test, live=live)
        stack.enter_context(patch.object(config, "DODO_PAYMENTS_ENVIRONMENT", mode))
        stack.enter_context(patch.object(billing, "_client", fake.client))
        return fake

    from contextlib import ExitStack
    with ExitStack() as stack:
        yield install


# ── webhook_readiness ──────────────────────────────────────────────────────


def test_a_correctly_joined_endpoint_has_no_problems(dodo):
    dodo(live=[endpoint()])
    assert billing.webhook_readiness() == []


def test_an_empty_filter_means_every_event_and_is_ready(dodo):
    dodo(live=[endpoint(filter_types=())])
    assert billing.webhook_readiness() == []


def test_the_incident_an_endpoint_in_test_mode_only_while_the_key_is_live(dodo):
    dodo(mode="live_mode", test=[endpoint()], live=[])
    problems = billing.webhook_readiness()
    assert len(problems) == 1
    assert "live_mode" in problems[0]
    # The fix it names must be the live one; the script defaults to test mode.
    assert "--apply --live" in problems[0]


def test_an_endpoint_for_another_host_does_not_count(dodo):
    dodo(live=[endpoint(url="https://certforge.intelliforge.tech/api/v1/webhooks/dodo")])
    assert "No live_mode webhook endpoint" in billing.webhook_readiness()[0]


def test_a_disabled_endpoint_is_a_problem(dodo):
    dodo(live=[endpoint(disabled=True)])
    assert "disabled" in billing.webhook_readiness()[0]


def test_an_endpoint_filtered_past_a_cancellation_is_a_problem(dodo):
    events = [e for e in billing.REQUIRED_WEBHOOK_EVENTS if e != "subscription.cancelled"]
    dodo(live=[endpoint(filter_types=events)])
    problems = billing.webhook_readiness()
    assert len(problems) == 1 and "subscription.cancelled" in problems[0]


def test_a_signing_key_that_is_not_the_endpoints_is_a_problem_and_is_never_printed(dodo):
    dodo(live=[endpoint(secret=OTHER_SECRET)])
    problems = billing.webhook_readiness()
    assert len(problems) == 1 and "401" in problems[0]
    assert WEBHOOK_KEY not in problems[0] and OTHER_SECRET not in problems[0]


def test_an_unset_webhook_key_is_a_problem(dodo):
    dodo(live=[endpoint()])
    with patch.object(config, "DODO_PAYMENTS_WEBHOOK_KEY", ""):
        assert "not set" in billing.webhook_readiness()[0]


def test_the_required_events_are_the_ones_the_provisioning_script_registers():
    """Two lists of one thing; this is what keeps them one."""
    import ast
    from pathlib import Path

    script = Path(__file__).resolve().parents[3] / "scripts" / "provision_dodo_webhook.py"
    tree = ast.parse(script.read_text(encoding="utf-8"))
    registered = next(
        ast.literal_eval(node.value) for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", None) == "EVENT_TYPES" for t in node.targets)
    )
    assert set(registered) == set(billing.REQUIRED_WEBHOOK_EVENTS)


# ── the release gate ───────────────────────────────────────────────────────


def test_a_known_problem_refuses_the_release_before_migrating(dodo):
    dodo(live=[])
    with patch.object(release, "_run_migrations", side_effect=AssertionError("migrated")):
        assert release.main() == 1


def test_warn_mode_releases_despite_a_known_problem(dodo, monkeypatch):
    dodo(live=[])
    monkeypatch.setenv("DODO_WEBHOOK_CHECK", "warn")
    assert release._dodo_webhook_ready() is True


def test_a_joined_endpoint_releases(dodo):
    dodo(live=[endpoint()])
    assert release._dodo_webhook_ready() is True


def test_dodo_being_unreachable_does_not_block_a_release():
    def unreachable():
        raise billing.BillingProviderError("connection reset")
    with patch.object(billing, "webhook_readiness", unreachable):
        assert release._dodo_webhook_ready() is True


def test_an_unconfigured_dodo_is_not_checked():
    with patch.object(config, "DODO_PAYMENTS_API_KEY", ""), \
         patch.object(billing, "webhook_readiness", side_effect=AssertionError("checked")):
        assert release._dodo_webhook_ready() is True


# ── recovering an org the gap already cost ─────────────────────────────────


def dodo_subscription(org, **kwargs):
    """What `subscriptions.retrieve` really returns — the SDK's own model —
    so the test covers its conversion to the dict the webhook path reads."""
    from dodopayments.types import Subscription
    from dodopayments.types.customer_limited_details import CustomerLimitedDetails

    data = subscription(org, **kwargs)
    return Subscription.construct(
        subscription_id=data["subscription_id"],
        status=data["status"],
        product_id=data["product_id"],
        cancel_at_next_billing_date=data["cancel_at_next_billing_date"],
        next_billing_date=datetime.now(timezone.utc) + timedelta(days=30),
        customer=CustomerLimitedDetails.construct(
            customer_id="cus_1", email="owner@example.com", name="Owner"),
        metadata=data["metadata"],
    )


@pytest.fixture
def retrievable():
    def install(model):
        fake = SimpleNamespace(subscriptions=SimpleNamespace(retrieve=lambda _id: model))
        stack.enter_context(patch.object(billing, "_client", lambda: fake))

    from contextlib import ExitStack
    with ExitStack() as stack:
        yield install


def test_a_fetched_subscription_upgrades_and_links_the_org(db_session, retrievable):
    org = new_org(db_session)
    model = dodo_subscription(org)
    retrievable(model)

    outcome, _, tier_before = recon.reconcile(db_session, billing.fetch_subscription("sub"))
    db_session.commit()

    assert (outcome, tier_before) == (billing.APPLIED, "community")
    org = reloaded(db_session, org)
    assert org.tier == "pro"
    # Linked, not merely re-tiered — so its eventual cancellation applies.
    assert org.dodo_subscription_id == model.subscription_id
    assert org.dodo_customer_id == "cus_1"
    assert org.current_period_end is not None
    event = db_session.query(BillingEvent).filter_by(org_id=org.id).one()
    assert event.event_type == recon.EVENT_TYPE


def test_the_dry_run_changes_nothing_and_apply_changes_it(db_session, retrievable):
    org = new_org(db_session)
    retrievable(dodo_subscription(org))

    assert recon.main(["sub"]) == 0
    assert reloaded(db_session, org).tier == "community"
    assert db_session.query(BillingEvent).filter_by(org_id=org.id).count() == 0

    assert recon.main(["sub", "--apply"]) == 0
    assert reloaded(db_session, org).tier == "pro"


def test_running_it_twice_changes_nothing_the_second_time(db_session, retrievable):
    org = new_org(db_session)
    retrievable(dodo_subscription(org))
    assert recon.main(["sub", "--apply"]) == 0
    first = reloaded(db_session, org)
    snapshot = (first.tier, first.dodo_subscription_id, first.subscription_status)

    assert recon.main(["sub", "--apply"]) == 0
    again = reloaded(db_session, org)
    assert (again.tier, again.dodo_subscription_id, again.subscription_status) == snapshot


def test_a_subscription_naming_no_known_org_changes_nothing(db_session, retrievable):
    org = new_org(db_session)
    model = dodo_subscription(org, metadata=False)
    retrievable(model)
    assert recon.main(["sub", "--apply"]) == 1
    assert reloaded(db_session, org).tier == "community"
