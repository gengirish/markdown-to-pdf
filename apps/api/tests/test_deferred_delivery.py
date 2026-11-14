"""The provider's daily send limit: defer, don't fail, and don't keep asking.

2026-11-12, production: a batch of 86 sent 39 emails, then every remaining
send met AgentMail's `Daily send limit exceeded`. Each refusal cost the row a
delivery attempt, and its automatic retry ran seconds later and cost another.
44 rows reached 2 of 3 attempts in eight seconds, and a well-meant resend that
afternoon would have spent the last one.

The rules these pin (docs/email-daily-cap-plan.md):

- a refusal for volume is `deferred`, costs no attempt, and says when it sends;
- after the first refusal the provider is not called again until the reset;
- a resend made meanwhile is refused before it reaches the provider;
- the sweep sends due rows oldest first and stops at the first new refusal;
- a row deferred past MAX_DEFERRAL is failed instead, with its attempts intact.
"""

import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from api.core import worker
from api.core.email import SEND_RATE_LIMITED, SendResult
from api.core.principal import LIVE_PREFIX
from api.models.credential import (
    DELIVERY_DEFERRED,
    DELIVERY_FAILED,
    DELIVERY_STATUSES,
    SENT,
    Credential,
    CredentialBatch,
)
from api.models.email_send_pause import EmailSendPause
from api.services import send_gate
from api.services.delivery import (
    MAX_DEFERRAL,
    deliver_credential_email,
    release_deferred,
)
from api.services.operator_console import resend_refusal

from test_bulk_issuance import DEFER, a_template, org_with_key, upload  # noqa: E402

SEND = "api.services.delivery.agentmail_deliver"
WAIT = timedelta(hours=14)


def refused():
    return SendResult(False, "Daily send limit exceeded.", kind=SEND_RATE_LIMITED, retry_after=WAIT)


class Provider:
    """Accepts `allowance` sends, then refuses every one for volume. Counts
    every call, which is the number the gate exists to keep down."""

    def __init__(self, allowance):
        self.allowance = allowance
        self.calls = 0

    def __call__(self, **kwargs):
        self.calls += 1
        if self.calls <= self.allowance:
            return SendResult(True, "")
        return refused()


def aware(value):
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def a_credential(db_session, slug, *, email="ada@example.com", issued_at=None, status="issued", **fields):
    raw = LIVE_PREFIX + f"{slug}-key"
    org = org_with_key(db_session, slug, raw, quota=1000)
    cred = Credential(
        public_id=f"CF-T-{uuid.uuid4().hex[:8].upper()}",
        org_id=org.id,
        recipient_name="Ada Lovelace",
        recipient_email=email,
        title="Analytical Engines",
        metadata_={},
        hmac_signature="x",
        status=status,
        issued_at=issued_at or datetime.now(timezone.utc),
        **fields,
    )
    db_session.add(cred)
    db_session.commit()
    return cred


# -- one send -----------------------------------------------------------------

def test_a_volume_refusal_is_deferred_and_costs_no_attempt(db_session):
    cred = a_credential(db_session, "defer-one")
    before = datetime.now(timezone.utc)

    with patch(SEND, return_value=refused()):
        assert deliver_credential_email(cred) is False

    assert cred.delivery_status == DELIVERY_DEFERRED
    assert cred.delivery_attempts == 0
    when = aware(cred.delivery_next_attempt_at)
    assert before + WAIT <= when <= datetime.now(timezone.utc) + WAIT + send_gate.RESET_SLACK
    assert "Sending automatically after" in cred.delivery_error


def test_a_real_refusal_still_fails_and_still_counts(db_session):
    """The regression guard on the other side: not every False is volume."""
    cred = a_credential(db_session, "defer-real-fail")

    with patch(SEND, return_value=(False, "AgentMail rejected the request (403)")):
        deliver_credential_email(cred)

    assert cred.delivery_status == DELIVERY_FAILED
    assert cred.delivery_attempts == 1
    assert cred.delivery_next_attempt_at is None


def test_a_deferred_row_that_later_sends_clears_its_schedule(db_session):
    cred = a_credential(db_session, "defer-then-sent")
    with patch(SEND, return_value=refused()):
        deliver_credential_email(cred)
    db_session.commit()
    send_gate.reset_memo()
    db_session.query(EmailSendPause).delete()

    with patch(SEND, return_value=(True, "")):
        assert deliver_credential_email(cred) is True

    assert cred.delivery_status == SENT
    assert cred.delivery_attempts == 1
    assert cred.delivery_next_attempt_at is None
    assert cred.delivery_error is None


# -- the gate -----------------------------------------------------------------

def test_after_one_refusal_the_provider_is_not_called_again(db_session):
    first = a_credential(db_session, "gate-holds")
    second = a_credential(db_session, "gate-holds")

    with patch(SEND, return_value=refused()) as send:
        deliver_credential_email(first)
        deliver_credential_email(second)

    assert send.call_count == 1
    assert second.delivery_status == DELIVERY_DEFERRED
    assert second.delivery_attempts == 0


def test_the_pause_survives_a_lost_memo(db_session):
    """A stopped machine forgets the memo. The table must still hold."""
    first = a_credential(db_session, "gate-table")
    with patch(SEND, return_value=refused()):
        deliver_credential_email(first)
    db_session.commit()

    send_gate.reset_memo()
    second = a_credential(db_session, "gate-table")
    with patch(SEND, return_value=(True, "")) as send:
        deliver_credential_email(second)

    send.assert_not_called()
    assert second.delivery_status == DELIVERY_DEFERRED


def test_a_pause_is_never_shortened(db_session):
    long = datetime.now(timezone.utc) + timedelta(hours=10)
    short = datetime.now(timezone.utc) + timedelta(hours=1)
    send_gate.pause(db_session, long, "first")
    send_gate.pause(db_session, short, "second")
    db_session.commit()

    send_gate.reset_memo()
    assert aware(send_gate.paused_until(db_session)) == long


def test_without_a_header_the_pause_runs_to_the_next_midnight_utc():
    now = datetime(2026, 11, 12, 9, 13, tzinfo=timezone.utc)
    assert send_gate.resume_at(now, None) == datetime(
        2026, 11, 13, 0, 0, tzinfo=timezone.utc
    ) + send_gate.RESET_SLACK


# -- a batch larger than the day's allowance ----------------------------------

def test_a_batch_sends_what_it_can_and_defers_the_rest_without_asking(client, db_session):
    """The incident, in miniature: allowance 4, batch of 10."""
    raw = LIVE_PREFIX + "gate-batch-key"
    org = org_with_key(db_session, "gate-batch", raw, quota=100)
    tpl = a_template(db_session, org)
    names = [f"Person{i}" for i in range(10)]
    with patch(DEFER):
        r = upload(client, "gate-batch", raw, tpl.id, *names)
    batch_id = uuid.UUID(r.json()["data"]["batch_id"])

    provider = Provider(allowance=4)
    with patch(SEND, side_effect=provider):
        retry_ids = worker._process_batch_sync(batch_id)

    # Four accepted, one refused, and five never asked.
    assert provider.calls == 5
    assert retry_ids == [], "a deferred row was queued for an immediate retry"

    db_session.expire_all()
    rows = db_session.query(Credential).filter_by(batch_id=batch_id).all()
    by = {}
    for c in rows:
        by.setdefault(c.delivery_status, []).append(c)
    assert len(by.get(SENT, [])) == 4
    assert len(by.get(DELIVERY_DEFERRED, [])) == 6
    assert all(c.delivery_attempts == 0 for c in by[DELIVERY_DEFERRED])

    batch = db_session.get(CredentialBatch, batch_id)
    assert batch.delivery_failed == 0

    status = client.get(
        f"/api/v1/orgs/gate-batch/batches/{batch_id}",
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert status.status_code == 200, status.text
    delivery = status.json()["data"]["delivery"]
    assert delivery["delivered"] == 4
    assert delivery["deferred"] == 6
    assert delivery["not_requested"] == 0, "deferred rows reported as never requested"


# -- resend -------------------------------------------------------------------

def test_a_resend_while_paused_is_refused_before_the_provider(client, db_session):
    raw = LIVE_PREFIX + "gate-resend-key"
    cred = a_credential(
        db_session, "gate-resend",
        delivery_status=DELIVERY_FAILED, delivery_attempts=2,
    )
    send_gate.pause(db_session, datetime.now(timezone.utc) + WAIT, "Daily send limit exceeded.")
    db_session.commit()
    send_gate.reset_memo()

    with patch(SEND, return_value=(True, "")) as send:
        r = client.post(
            f"/api/v1/orgs/gate-resend/credentials/{cred.public_id}/resend",
            headers={"Authorization": f"Bearer {raw}"},
        )

    assert r.status_code == 409, r.text
    assert r.json()["error"]["type"] == "email_paused"
    send.assert_not_called()
    db_session.expire_all()
    assert db_session.get(Credential, cred.id).delivery_attempts == 2


def test_a_deferred_row_is_never_resendable(client, db_session):
    raw = LIVE_PREFIX + "gate-resend-deferred-key"
    cred = a_credential(
        db_session, "gate-resend-deferred",
        delivery_status=DELIVERY_DEFERRED,
        delivery_next_attempt_at=datetime.now(timezone.utc) + WAIT,
    )

    with patch(SEND, return_value=(True, "")) as send:
        r = client.post(
            f"/api/v1/orgs/gate-resend-deferred/credentials/{cred.public_id}/resend",
            headers={"Authorization": f"Bearer {raw}"},
        )

    assert r.status_code == 409
    assert "send automatically" in r.json()["error"]["message"]
    send.assert_not_called()


def test_the_operator_console_names_the_pause_instead_of_offering_resend(db_session):
    cred = a_credential(
        db_session, "gate-operator",
        delivery_status=DELIVERY_FAILED, delivery_attempts=1,
    )
    assert resend_refusal(cred, session=db_session) is None

    send_gate.pause(db_session, datetime.now(timezone.utc) + WAIT, "Daily send limit exceeded.")
    refusal = resend_refusal(cred, session=db_session)
    assert refusal and "paused until" in refusal

    cred.delivery_status = DELIVERY_DEFERRED
    assert "send automatically" in resend_refusal(cred, session=db_session)


# -- the sweep ----------------------------------------------------------------

def _due(db_session, slug, n, *, start):
    rows = []
    for i in range(n):
        rows.append(a_credential(
            db_session, slug,
            email=f"p{i}@example.com",
            issued_at=start + timedelta(seconds=i),
            delivery_status=DELIVERY_DEFERRED,
            delivery_next_attempt_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        ))
    return rows


def test_the_sweep_sends_due_rows_oldest_first(db_session):
    start = datetime.now(timezone.utc) - timedelta(days=1)
    rows = _due(db_session, "sweep-order", 3, start=start)
    sent_to = []

    def provider(**kwargs):
        sent_to.append(kwargs["to_email"])
        return SendResult(True, "")

    with patch(SEND, side_effect=provider):
        outcome = release_deferred(db_session)
    db_session.commit()

    assert outcome["sent"] >= 3
    mine = [r.recipient_email for r in rows]
    assert [e for e in sent_to if e in mine] == mine
    for r in rows:
        db_session.refresh(r)
        assert r.delivery_status == SENT
        assert r.delivery_next_attempt_at is None


def test_the_sweep_stops_at_the_first_new_refusal(db_session):
    """When the limit resets, every row deferred that day is due at once. If
    the allowance is smaller than the backlog, 44 due rows must cost one
    refused call, not 44."""
    start = datetime.now(timezone.utc) - timedelta(days=2)
    rows = _due(db_session, "sweep-stampede", 6, start=start)

    with patch(SEND, return_value=refused()) as send:
        outcome = release_deferred(db_session)
    db_session.commit()

    assert send.call_count == 1
    assert outcome["paused"] is True
    for r in rows:
        db_session.refresh(r)
        assert r.delivery_status == DELIVERY_DEFERRED
        assert r.delivery_attempts == 0


def test_the_sweep_does_nothing_while_paused(db_session):
    _due(db_session, "sweep-paused", 2, start=datetime.now(timezone.utc) - timedelta(days=3))
    send_gate.pause(db_session, datetime.now(timezone.utc) + WAIT, "limit")

    with patch(SEND, return_value=(True, "")) as send:
        outcome = release_deferred(db_session)

    send.assert_not_called()
    assert outcome == {"sent": 0, "deferred": 0, "failed": 0, "paused": True}


def test_a_revoked_credential_is_not_mailed_by_the_sweep(db_session):
    [cred] = _due(db_session, "sweep-revoked", 1, start=datetime.now(timezone.utc) - timedelta(days=4))
    cred.status = "revoked"
    db_session.commit()

    with patch(SEND, return_value=(True, "")) as send:
        release_deferred(db_session)

    send.assert_not_called()
    assert cred.delivery_status != DELIVERY_DEFERRED


# -- the deadline -------------------------------------------------------------

def test_a_row_deferred_past_the_deadline_fails_with_its_attempts_intact(db_session):
    cred = a_credential(
        db_session, "defer-deadline",
        delivery_status=DELIVERY_DEFERRED,
        delivery_deferred_since=datetime.now(timezone.utc) - MAX_DEFERRAL - timedelta(days=1),
        delivery_attempts=1,
    )

    with patch(SEND, return_value=refused()):
        deliver_credential_email(cred)

    assert cred.delivery_status == DELIVERY_FAILED
    assert cred.delivery_attempts == 1
    assert "persisted for 7 days" in cred.delivery_error


# -- the status vocabulary, across the boundary --------------------------------

def test_every_delivery_state_is_accepted_by_every_filter_and_the_dashboard():
    """A state the backend writes and a filter refuses is a row nobody can
    find; one the dashboard's type lacks renders as nothing. Two halves, each
    fine alone — the failure this codebase keeps producing."""
    from api.routes import credentials as credentials_route
    from api.routes import operator as operator_route

    operator_values = set(operator_route._DELIVERY_PATTERN.strip("^$()").split("|"))
    assert DELIVERY_STATUSES <= operator_values

    from api.index import app
    list_route = next(
        r for r in app.routes
        if getattr(r, "path", "") == "/api/v1/orgs/{slug}/credentials"
        and "GET" in getattr(r, "methods", set())
    )
    param = next(p for p in list_route.dependant.query_params if p.name == "delivery_status")
    pattern = next(
        m.pattern for m in param.field_info.metadata if getattr(m, "pattern", None)
    )
    assert set(pattern.strip("^$()").split("|")) == set(DELIVERY_STATUSES)
    assert credentials_route  # imported for the side effect of registering

    api_ts = Path(__file__).resolve().parents[2] / "web" / "lib" / "api.ts"
    source = api_ts.read_text(encoding="utf-8")
    match = re.search(r"export type DeliveryStatus\s*=\s*([^;]+);", source)
    assert match, "DeliveryStatus type not found in apps/web/lib/api.ts"
    web_values = set(re.findall(r'"([a-z_]+)"', match.group(1)))
    assert web_values == set(DELIVERY_STATUSES), (
        f"apps/web/lib/api.ts DeliveryStatus {sorted(web_values)} "
        f"!= backend {sorted(DELIVERY_STATUSES)}"
    )


@pytest.fixture(autouse=True)
def _no_deferred_rows_from_other_tests(db_session):
    """The sweep reads every due row in the database, and the suite shares one
    SQLite file. Rows another test left deferred would be swept here, and a
    'not called' assertion would fail for someone else's row."""
    db_session.query(Credential).filter(
        Credential.delivery_status == DELIVERY_DEFERRED
    ).update({"delivery_status": "not_requested", "delivery_next_attempt_at": None})
    db_session.commit()
    yield


@pytest.fixture(autouse=True)
def _no_real_provider(monkeypatch):
    """Belt and braces: nothing in this file may reach a real client."""
    from api.core import email as email_mod
    monkeypatch.setattr(email_mod, "_agentmail_client", None)


# -- the one-off repair --------------------------------------------------------

def test_the_repair_defers_limit_failures_and_nothing_else(db_session):
    from api.repair_rate_limited_deliveries import repair

    hit = a_credential(
        db_session, "repair-org",
        delivery_status=DELIVERY_FAILED, delivery_attempts=2,
        delivery_error="Daily send limit exceeded. Share the credential link instead.",
    )
    other = a_credential(
        db_session, "repair-org",
        delivery_status=DELIVERY_FAILED, delivery_attempts=1,
        delivery_error="AgentMail rejected the request (403).",
    )
    revoked = a_credential(
        db_session, "repair-org", status="revoked",
        delivery_status=DELIVERY_FAILED, delivery_attempts=2,
        delivery_error="Daily send limit exceeded.",
    )

    moved = repair(db_session, "repair-org")
    db_session.commit()

    assert [c.public_id for c in moved] == [hit.public_id]
    assert hit.delivery_status == DELIVERY_DEFERRED
    assert hit.delivery_attempts == 2, "the repair must not guess at attempts"
    assert hit.delivery_next_attempt_at is not None
    assert other.delivery_status == DELIVERY_FAILED
    assert revoked.delivery_status == DELIVERY_FAILED
    assert repair(db_session, "repair-org") == [], "a second run must change nothing"


def test_the_deadline_counts_from_the_deferral_not_the_issue(db_session):
    """A month-old credential re-queued for a resend has been deferred for
    minutes. Measured from issued_at, its first refusal failed it with "the
    send limit persisted for 7 days"."""
    cred = a_credential(
        db_session, "defer-deadline-old-issue",
        issued_at=datetime.now(timezone.utc) - timedelta(days=30),
    )

    with patch(SEND, return_value=refused()):
        deliver_credential_email(cred)

    assert cred.delivery_status == DELIVERY_DEFERRED
    assert cred.delivery_deferred_since is not None


def test_the_deferral_start_survives_a_second_refusal(db_session):
    """The sweep sets `pending` before each send; a refusal then must keep the
    original start, or the deadline restarts on every attempt and never ends."""
    start = datetime.now(timezone.utc) - timedelta(days=2)
    cred = a_credential(
        db_session, "defer-since-kept",
        delivery_status=DELIVERY_DEFERRED, delivery_deferred_since=start,
    )

    with patch(SEND, return_value=refused()):
        deliver_credential_email(cred)

    assert aware(cred.delivery_deferred_since) == start


def test_leaving_deferred_clears_the_start(db_session):
    cred = a_credential(
        db_session, "defer-since-cleared",
        delivery_status=DELIVERY_DEFERRED,
        delivery_deferred_since=datetime.now(timezone.utc) - timedelta(days=1),
    )
    with patch(SEND, return_value=(True, "")):
        deliver_credential_email(cred)
    assert cred.delivery_deferred_since is None
