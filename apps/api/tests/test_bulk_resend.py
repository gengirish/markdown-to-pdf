"""Resend every failed email you are looking at, in one gesture.

`POST /orgs/{slug}/credentials/resend-failed` queues rather than sends: each
eligible row becomes `deferred`, due now, and the deferred-send sweep sends
it. That is the whole design, and these pin why it matters:

- a bulk resend never calls the provider from the request, so it cannot spend
  the day's allowance mid-click or hold a request open for N sends;
- it only takes rows that can go (address, not revoked, not test, under the
  attempt ceiling), and says how many it left out and why;
- it filters exactly as the list does, so the number confirmed is the number
  on screen;
- it is owner/admin only — it mails many people at once.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from api.core.principal import LIVE_PREFIX
from api.models.credential import (
    DELIVERY_DEFERRED,
    DELIVERY_FAILED,
    SENT,
    Credential,
)
from api.models.organization import OrgMember
from api.services import delivery as delivery_mod
from api.services import send_gate
from api.services.delivery import MAX_DELIVERY_ATTEMPTS, release_deferred

from test_bulk_issuance import org_with_key  # noqa: E402

SEND = "api.services.delivery.agentmail_deliver"


def key(slug):
    return LIVE_PREFIX + f"{slug}-key"


def failed(db_session, slug, n=1, **fields):
    org = org_with_key(db_session, slug, key(slug), quota=1000)
    rows = []
    for i in range(n):
        values = dict(
            public_id=f"CF-B-{uuid.uuid4().hex[:8].upper()}",
            org_id=org.id,
            recipient_name=f"Person {i}",
            recipient_email=f"p{i}@example.com",
            title="Analytical Engines",
            metadata_={},
            hmac_signature="x",
            status="issued",
            issued_at=datetime.now(timezone.utc) - timedelta(minutes=n - i),
            delivery_status=DELIVERY_FAILED,
            delivery_attempts=1,
            delivery_error="AgentMail rejected the request (403).",
        )
        values.update(fields)
        rows.append(Credential(**values))
    db_session.add_all(rows)
    db_session.commit()
    return org, rows


def resend_failed(client, slug, auth=None, **body):
    return client.post(
        f"/api/v1/orgs/{slug}/credentials/resend-failed",
        headers={"Authorization": f"Bearer {auth or key(slug)}"},
        json=body,
    )


@pytest.fixture(autouse=True)
def _only_this_tests_rows(db_session):
    """The sweep and the org-wide resend read every matching row in a shared
    SQLite file; rows left by other tests would be counted here."""
    db_session.query(Credential).filter(
        Credential.delivery_status.in_([DELIVERY_DEFERRED])
    ).update({"delivery_status": "not_requested", "delivery_next_attempt_at": None})
    db_session.commit()
    yield


# -- the dry run fills the dialog ---------------------------------------------

def test_a_dry_run_counts_and_changes_nothing(client, db_session):
    _, rows = failed(db_session, "bulk-dry", n=3)

    with patch(SEND) as send:
        r = resend_failed(client, "bulk-dry", dry_run=True)

    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["eligible"] == 3
    assert data["queued"] == 0
    send.assert_not_called()
    for row in rows:
        db_session.refresh(row)
        assert row.delivery_status == DELIVERY_FAILED


def test_rows_that_cannot_go_are_counted_by_reason_not_queued(client, db_session):
    org, ok = failed(db_session, "bulk-skip", n=1)
    _, at_limit = failed(db_session, "bulk-skip", n=1, delivery_attempts=MAX_DELIVERY_ATTEMPTS)
    _, revoked = failed(db_session, "bulk-skip", n=1, status="revoked")
    _, no_email = failed(db_session, "bulk-skip", n=1, recipient_email="")
    _, test = failed(db_session, "bulk-skip", n=1, metadata_={"_test": True})

    data = resend_failed(client, "bulk-skip").json()["data"]

    assert data["queued"] == 1
    assert data["skipped"] == {"attempt_limit": 1, "revoked": 1, "no_email": 1, "test": 1}
    for row in at_limit + revoked + no_email + test:
        db_session.refresh(row)
        assert row.delivery_status == DELIVERY_FAILED


# -- queue, then the sweep sends ----------------------------------------------

def test_a_resend_queues_without_calling_the_provider_and_the_sweep_sends(client, db_session):
    _, rows = failed(db_session, "bulk-queue", n=3)

    with patch(SEND, return_value=(True, "")) as send:
        r = resend_failed(client, "bulk-queue")
        assert send.call_count == 0, "the request itself sent email"

        db_session.expire_all()
        for row in rows:
            row = db_session.get(Credential, row.id)
            assert row.delivery_status == DELIVERY_DEFERRED
            assert row.delivery_attempts == 1, "queuing must not spend an attempt"
            assert "Resend queued by" in row.delivery_error

        release_deferred(db_session)
        db_session.commit()

    assert r.json()["data"]["queued"] == 3
    assert send.call_count == 3
    for row in rows:
        db_session.refresh(row)
        assert row.delivery_status == SENT
        assert row.delivery_attempts == 2


def test_a_queued_resend_meets_a_closed_gate_and_waits(client, db_session):
    _, rows = failed(db_session, "bulk-paused", n=2)
    send_gate.pause(db_session, datetime.now(timezone.utc) + timedelta(hours=6), "limit")
    db_session.commit()

    with patch(SEND, return_value=(True, "")) as send:
        data = resend_failed(client, "bulk-paused").json()["data"]
        release_deferred(db_session)

    assert data["queued"] == 2
    assert data["paused_until"] is not None
    send.assert_not_called()


# -- scope --------------------------------------------------------------------

def test_a_resend_is_scoped_to_the_filters_like_the_list(client, db_session):
    """Search text stands in for every filter: they share `_filtered` with
    the list route, so the scope the dialog counts is the scope on screen."""
    _, others = failed(db_session, "bulk-scope", n=2)
    _, [zelda] = failed(db_session, "bulk-scope", n=1, recipient_name="Unique Zelda")

    listed = client.get(
        "/api/v1/orgs/bulk-scope/credentials?delivery_status=failed&q=zelda",
        headers={"Authorization": f"Bearer {key('bulk-scope')}"},
    ).json()["data"]["total"]
    data = resend_failed(client, "bulk-scope", q="zelda").json()["data"]

    assert data["queued"] == listed == 1
    db_session.refresh(zelda)
    assert zelda.delivery_status == DELIVERY_DEFERRED
    for row in others:
        db_session.refresh(row)
        assert row.delivery_status == DELIVERY_FAILED


def test_a_resend_never_reaches_another_orgs_rows(client, db_session):
    failed(db_session, "bulk-mine", n=1)
    _, theirs = failed(db_session, "bulk-theirs", n=2)

    resend_failed(client, "bulk-mine")

    for row in theirs:
        db_session.refresh(row)
        assert row.delivery_status == DELIVERY_FAILED


def test_one_resend_queues_at_most_the_cap_oldest_first(client, db_session, monkeypatch):
    monkeypatch.setattr(delivery_mod, "MAX_BULK_RESEND", 2)
    _, rows = failed(db_session, "bulk-cap", n=3)

    data = resend_failed(client, "bulk-cap").json()["data"]

    assert data["queued"] == 2
    assert data["capped"] is True
    states = []
    for row in rows:
        db_session.refresh(row)
        states.append(row.delivery_status)
    assert states == [DELIVERY_DEFERRED, DELIVERY_DEFERRED, DELIVERY_FAILED]


# -- who may ------------------------------------------------------------------

@pytest.mark.parametrize("role, allowed", [("owner", True), ("admin", True), ("issuer", False)])
def test_only_owners_and_admins_may_resend_in_bulk(client, db_session, mock_clerk, role, allowed):
    slug = f"bulk-role-{role}"
    org, rows = failed(db_session, slug, n=1)
    db_session.add(OrgMember(org_id=org.id, clerk_user_id="test_user_123", role=role))
    db_session.commit()

    r = client.post(f"/api/v1/orgs/{slug}/credentials/resend-failed", json={})

    assert (r.status_code == 200) is allowed, r.text
    db_session.refresh(rows[0])
    assert (rows[0].delivery_status == DELIVERY_DEFERRED) is allowed


@pytest.fixture(autouse=True)
def _no_real_provider(monkeypatch):
    from api.core import email as email_mod
    monkeypatch.setattr(email_mod, "_agentmail_client", None)
