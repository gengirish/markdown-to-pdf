"""The customer-facing delivery routes: list, redeliver, and ``last_delivery``.

The contract is "Delivery object" in docs/build-plan-2026-11.md; B-web reads
it field for field, and parses ``error.type`` on a refused redeliver.

Each guard below was seen failing against the bug named in its docstring.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from api.core import worker
from api.models.api_key import WebhookDelivery, WebhookEndpoint
from api.models.organization import Organization, OrgMember
from api.routes.developers import STRANDED_PENDING_AFTER
from api.services.webhooks import (
    MAX_ATTEMPTS,
    STATUS_ABANDONED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SUCCEEDED,
)

DELIVERY_FIELDS = {
    "id", "event", "status", "attempts", "last_status_code", "last_error",
    "next_attempt_at", "created_at", "delivered_at",
}


def _org(db_session, slug, *, tier="pro", member=True):
    org = Organization(id=uuid.uuid4(), name=slug.title(), slug=slug, tier=tier)
    db_session.add(org)
    if member:
        db_session.add(OrgMember(org_id=org.id, clerk_user_id="test_user_123", role="owner"))
    endpoint = WebhookEndpoint(
        org_id=org.id, url=f"https://{slug}.example/hook", secret="whsec_x",
        events=["batch.completed"],
    )
    db_session.add(endpoint)
    db_session.commit()
    return org, endpoint


def _delivery(db_session, org, endpoint, *, status=STATUS_FAILED, attempts=1,
              created_at=None, next_attempt_at=None):
    row = WebhookDelivery(
        endpoint_id=endpoint.id,
        org_id=org.id,
        event="batch.completed",
        payload='{"secret_payload": true}',
        status=status,
        attempts=attempts,
        last_status_code=500 if attempts else None,
        last_error="HTTP 500: boom" if attempts else None,
        next_attempt_at=next_attempt_at,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db_session.add(row)
    db_session.commit()
    return row


def _deliveries_url(org, endpoint):
    return f"/api/v1/orgs/{org.slug}/webhooks/{endpoint.id}/deliveries"


def _redeliver_url(org, endpoint, delivery_id):
    return f"{_deliveries_url(org, endpoint)}/{delivery_id}/redeliver"


@pytest.fixture
def defer():
    with patch.object(worker.deliver_webhook, "defer_async", new=AsyncMock()) as mock:
        yield mock


def _count(db_session):
    db_session.expire_all()
    return db_session.query(WebhookDelivery).count()


# -- list ----------------------------------------------------------------------

def test_list_is_newest_first_and_never_exposes_the_payload(client, mock_clerk, db_session):
    org, ep = _org(db_session, "wd-list")
    base = datetime.now(timezone.utc) - timedelta(hours=1)
    rows = [_delivery(db_session, org, ep, created_at=base + timedelta(minutes=i)) for i in range(3)]

    res = client.get(_deliveries_url(org, ep))
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert [d["id"] for d in data] == [str(r.id) for r in reversed(rows)]
    for d in data:
        assert set(d) == DELIVERY_FIELDS
    assert "secret_payload" not in res.text


def test_list_returns_at_most_fifty(client, mock_clerk, db_session):
    org, ep = _org(db_session, "wd-fifty")
    base = datetime.now(timezone.utc) - timedelta(days=1)
    for i in range(55):
        _delivery(db_session, org, ep, created_at=base + timedelta(minutes=i))
    data = client.get(_deliveries_url(org, ep)).json()["data"]
    assert len(data) == 50


def test_another_orgs_endpoint_and_delivery_are_404(client, mock_clerk, db_session, defer):
    """Guard. Bug: look the delivery (or endpoint) up by its id alone."""
    mine, my_ep = _org(db_session, "wd-mine")
    theirs, their_ep = _org(db_session, "wd-theirs", member=False)
    their_row = _delivery(db_session, theirs, their_ep, status=STATUS_ABANDONED,
                          attempts=MAX_ATTEMPTS)

    # Their endpoint under my slug.
    assert client.get(_deliveries_url(mine, their_ep)).status_code == 404
    assert client.post(_redeliver_url(mine, their_ep, their_row.id)).status_code == 404
    # My endpoint, their delivery id.
    res = client.post(_redeliver_url(mine, my_ep, their_row.id))
    assert res.status_code == 404
    defer.assert_not_awaited()


def test_malformed_ids_are_404_not_500(client, mock_clerk, db_session, defer):
    org, ep = _org(db_session, "wd-malformed")
    assert client.get(f"/api/v1/orgs/{org.slug}/webhooks/not-a-uuid/deliveries").status_code == 404
    assert client.post(_redeliver_url(org, ep, "not-a-uuid")).status_code == 404
    defer.assert_not_awaited()


def test_community_org_gets_402(client, mock_clerk, db_session, defer):
    """Guard. Bug: drop require_grant."""
    org, ep = _org(db_session, "wd-community", tier="community")
    row = _delivery(db_session, org, ep, status=STATUS_ABANDONED, attempts=MAX_ATTEMPTS)
    for res in (client.get(_deliveries_url(org, ep)),
                client.post(_redeliver_url(org, ep, row.id))):
        assert res.status_code == 402, res.text
        assert res.json()["error"]["type"] == "plan_feature_required"
    defer.assert_not_awaited()


# -- redeliver -----------------------------------------------------------------

def test_redeliver_abandoned_queues_the_same_id_and_creates_no_row(
    client, mock_clerk, db_session, defer
):
    """Guard. Bug: create a new delivery row (a new event id)."""
    org, ep = _org(db_session, "wd-abandoned")
    row = _delivery(db_session, org, ep, status=STATUS_ABANDONED, attempts=MAX_ATTEMPTS)
    before = _count(db_session)

    res = client.post(_redeliver_url(org, ep, row.id))
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert set(data) == DELIVERY_FIELDS
    assert data["id"] == str(row.id)
    assert data["attempts"] == MAX_ATTEMPTS  # not reset
    defer.assert_awaited_once_with(delivery_id=str(row.id))
    assert _count(db_session) == before


def test_redeliver_failed_is_allowed(client, mock_clerk, db_session, defer):
    org, ep = _org(db_session, "wd-failed")
    row = _delivery(db_session, org, ep, status=STATUS_FAILED, attempts=2,
                    next_attempt_at=datetime.now(timezone.utc) + timedelta(minutes=30))
    res = client.post(_redeliver_url(org, ep, row.id))
    assert res.status_code == 200, res.text
    defer.assert_awaited_once_with(delivery_id=str(row.id))


def test_redeliver_succeeded_is_409(client, mock_clerk, db_session, defer):
    """Guard. Bug: drop the status check."""
    org, ep = _org(db_session, "wd-succeeded")
    row = _delivery(db_session, org, ep, status=STATUS_SUCCEEDED, attempts=1)
    res = client.post(_redeliver_url(org, ep, row.id))
    assert res.status_code == 409, res.text
    assert res.json()["error"]["type"] == "delivery_not_redeliverable"
    defer.assert_not_awaited()


def test_stale_pending_is_redeliverable_and_fresh_pending_is_not(
    client, mock_clerk, db_session, defer
):
    """Guard. Bug: treat every pending row the same, either way."""
    org, ep = _org(db_session, "wd-pending")
    now = datetime.now(timezone.utc)
    stale = _delivery(db_session, org, ep, status=STATUS_PENDING, attempts=0,
                      next_attempt_at=now - STRANDED_PENDING_AFTER - timedelta(minutes=1))
    fresh = _delivery(db_session, org, ep, status=STATUS_PENDING, attempts=0,
                      next_attempt_at=now - timedelta(minutes=1))

    res = client.post(_redeliver_url(org, ep, fresh.id))
    assert res.status_code == 409, res.text
    assert res.json()["error"]["type"] == "delivery_not_redeliverable"
    defer.assert_not_awaited()

    res = client.post(_redeliver_url(org, ep, stale.id))
    assert res.status_code == 200, res.text
    defer.assert_awaited_once_with(delivery_id=str(stale.id))


def test_a_queue_failure_is_reported_not_swallowed(client, mock_clerk, db_session):
    org, ep = _org(db_session, "wd-queue-down")
    row = _delivery(db_session, org, ep, status=STATUS_ABANDONED, attempts=MAX_ATTEMPTS)
    with patch.object(worker.deliver_webhook, "defer_async",
                      new=AsyncMock(side_effect=RuntimeError("down"))):
        res = client.post(_redeliver_url(org, ep, row.id))
    assert res.status_code == 503


# -- last_delivery on the endpoint list -----------------------------------------

def test_last_delivery_is_the_newest_row(client, mock_clerk, db_session):
    """Guard. Bug: order ascending (pick the oldest)."""
    org, ep = _org(db_session, "wd-last")
    base = datetime.now(timezone.utc) - timedelta(hours=2)
    _delivery(db_session, org, ep, status=STATUS_ABANDONED, created_at=base)
    newest = _delivery(db_session, org, ep, status=STATUS_SUCCEEDED,
                       created_at=base + timedelta(hours=1))
    _delivery(db_session, org, ep, status=STATUS_FAILED, created_at=base + timedelta(minutes=30))

    quiet = WebhookEndpoint(org_id=org.id, url="https://quiet.example/hook",
                            secret="whsec_y", events=["batch.completed"])
    db_session.add(quiet)
    db_session.commit()

    hooks = {h["id"]: h for h in client.get(f"/api/v1/orgs/{org.slug}/webhooks").json()["data"]}
    last = hooks[str(ep.id)]["last_delivery"]
    assert set(last) == DELIVERY_FIELDS
    assert last["id"] == str(newest.id)
    assert last["status"] == STATUS_SUCCEEDED
    assert hooks[str(quiet.id)]["last_delivery"] is None
