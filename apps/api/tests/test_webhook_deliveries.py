"""batch.completed webhooks: a delivery is a row, and each attempt is a job.

What this replaced, and what each guard here is against:

  ANY-RESPONSE  The batch POSTed once with httpx, which does not raise on a
                4xx or 5xx, so a receiver's 500 was logged "Webhook
                dispatched" and the event was gone.
  INLINE        The POST ran inside the batch job, 5s per endpoint, so a
                hanging receiver held the batch that was sending to it.
  NO RECORD     Nothing recorded a delivery, so nobody could answer "did you
                send it?", and with no event id a receiver could not tell a
                retry from a new event.

The HTTP seam is ``services.webhooks.http_client``; tests replace it with a
client over ``httpx.MockTransport``. The one test that must prove *no* HTTP
call happens traps httpx's real transport instead, because a reintroduced
inline POST would not go through the seam.
"""

import asyncio
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from api.core import worker
from api.models.api_key import WebhookDelivery, WebhookEndpoint
from api.models.credential import CredentialBatch
from api.models.organization import Organization
from api.services import webhooks

from test_batch_recovery import staged_batch  # noqa: E402

SECRET = "whsec_test_secret"
_real_http_client = webhooks.http_client


def _org(db_session, slug):
    org = Organization(slug=slug, name=slug.title(), tier="starter")
    db_session.add(org)
    db_session.commit()
    return org


def _endpoint(db_session, org, events=("batch.completed",), active=True, url=None):
    ep = WebhookEndpoint(
        org_id=org.id,
        url=url or f"https://hooks.example.com/{uuid.uuid4().hex[:8]}",
        secret=SECRET,
        events=list(events),
        active=active,
    )
    db_session.add(ep)
    db_session.commit()
    return ep


def _delivery(db_session, org, data=None):
    """One pending row, created the way a batch creates it."""
    ids = webhooks.create_deliveries(
        db_session, org.id, webhooks.EVENT_BATCH_COMPLETED, data or {"batch_id": "b-1"}
    )
    db_session.commit()
    assert len(ids) == 1
    return ids[0]


def _row(db_session, delivery_id):
    db_session.expire_all()
    return db_session.get(WebhookDelivery, delivery_id)


@pytest.fixture
def receiver(monkeypatch):
    """A fake receiver behind the seam. Set ``.respond`` to change its answer."""

    class Receiver:
        def __init__(self):
            self.requests: list[httpx.Request] = []
            self.respond = lambda request: httpx.Response(200)

        def handler(self, request):
            self.requests.append(request)
            return self.respond(request)

    rec = Receiver()
    monkeypatch.setattr(
        webhooks,
        "http_client",
        lambda: _real_http_client(transport=httpx.MockTransport(rec.handler)),
    )
    return rec


# -- 2xx is the only success ---------------------------------------------------

def test_a_500_leaves_the_delivery_failed_with_a_retry_scheduled(db_session, receiver):
    org = _org(db_session, "wh-500")
    _endpoint(db_session, org)
    delivery_id = _delivery(db_session, org)
    receiver.respond = lambda request: httpx.Response(500, text="boom")

    before = datetime.now(timezone.utc)
    delay = webhooks.attempt_delivery(delivery_id)

    row = _row(db_session, delivery_id)
    assert row.status == webhooks.STATUS_FAILED
    assert row.last_status_code == 500
    assert row.attempts == 1
    assert row.delivered_at is None
    assert "500" in row.last_error
    assert delay == webhooks.RETRY_DELAYS_SECONDS[0]
    next_at = row.next_attempt_at.replace(tzinfo=row.next_attempt_at.tzinfo or timezone.utc)
    assert next_at >= before + timedelta(seconds=delay - 1)


def test_a_2xx_succeeds_and_schedules_nothing(db_session, receiver):
    org = _org(db_session, "wh-200")
    _endpoint(db_session, org)
    delivery_id = _delivery(db_session, org)
    receiver.respond = lambda request: httpx.Response(204)

    assert webhooks.attempt_delivery(delivery_id) is None
    row = _row(db_session, delivery_id)
    assert row.status == webhooks.STATUS_SUCCEEDED
    assert row.last_status_code == 204
    assert row.delivered_at is not None
    assert row.next_attempt_at is None


def test_a_redirect_is_not_a_success_and_is_not_followed(db_session, receiver):
    org = _org(db_session, "wh-302")
    _endpoint(db_session, org)
    delivery_id = _delivery(db_session, org)
    receiver.respond = lambda request: httpx.Response(
        302, headers={"location": "https://elsewhere.example.com/"}
    )

    assert webhooks.attempt_delivery(delivery_id) == webhooks.RETRY_DELAYS_SECONDS[0]
    assert _row(db_session, delivery_id).status == webhooks.STATUS_FAILED
    assert len(receiver.requests) == 1


def test_retry_after_longer_than_the_schedule_is_honoured(db_session, receiver):
    org = _org(db_session, "wh-retry-after")
    _endpoint(db_session, org)
    delivery_id = _delivery(db_session, org)
    receiver.respond = lambda request: httpx.Response(503, headers={"retry-after": "900"})

    assert webhooks.attempt_delivery(delivery_id) == 900
    # Shorter than the step: the schedule wins.
    assert webhooks.next_delay(2, httpx.Response(503, headers={"retry-after": "5"})) == 300
    # Never parked longer than the longest step.
    assert webhooks.next_delay(1, httpx.Response(503, headers={"retry-after": "9999999"})) == 43200


# -- the attempt cap -----------------------------------------------------------

def test_timeouts_retry_on_schedule_and_the_seventh_failure_abandons(db_session, receiver):
    org = _org(db_session, "wh-timeout")
    _endpoint(db_session, org)
    delivery_id = _delivery(db_session, org)

    def hang(request):
        raise httpx.ReadTimeout("receiver hung", request=request)

    receiver.respond = hang

    delays = [webhooks.attempt_delivery(delivery_id) for _ in range(6)]
    assert delays == list(webhooks.RETRY_DELAYS_SECONDS)
    row = _row(db_session, delivery_id)
    assert row.status == webhooks.STATUS_FAILED
    assert row.last_status_code is None
    assert "Timed out" in row.last_error

    assert webhooks.attempt_delivery(delivery_id) is None
    row = _row(db_session, delivery_id)
    assert row.attempts == webhooks.MAX_ATTEMPTS == 7
    assert row.status == webhooks.STATUS_ABANDONED
    assert row.next_attempt_at is None
    assert len(receiver.requests) == 7


def test_the_task_schedules_the_next_attempt_and_stops_when_final(monkeypatch):
    """The job half of the cap: a delay becomes a schedule_in job, None becomes nothing."""
    configured = MagicMock()
    configured.defer_async = AsyncMock()
    configure = MagicMock(return_value=configured)
    monkeypatch.setattr(worker.deliver_webhook, "configure", configure)
    did = str(uuid.uuid4())

    monkeypatch.setattr(worker, "attempt_webhook_delivery", lambda _id: 300.0)
    asyncio.run(worker.deliver_webhook.func(delivery_id=did))
    configure.assert_called_once_with(schedule_in={"seconds": 300})
    configured.defer_async.assert_awaited_once_with(delivery_id=did)

    configure.reset_mock()
    configured.defer_async.reset_mock()
    monkeypatch.setattr(worker, "attempt_webhook_delivery", lambda _id: None)
    asyncio.run(worker.deliver_webhook.func(delivery_id=did))
    configure.assert_not_called()
    configured.defer_async.assert_not_awaited()


def test_the_task_is_on_its_own_queue_with_procrastinates_retry_off():
    assert worker.deliver_webhook.queue == "webhooks"
    assert not worker.deliver_webhook.retry_strategy


# -- same event, same bytes ----------------------------------------------------

def test_every_attempt_sends_the_same_event_id_and_the_stored_bytes(db_session, receiver):
    org = _org(db_session, "wh-bytes")
    _endpoint(db_session, org)
    delivery_id = _delivery(db_session, org, {"batch_id": "b-9", "succeeded": 3})

    row = _row(db_session, delivery_id)
    body = json.loads(row.payload)
    assert body["event"] == "batch.completed"
    assert body["delivery_id"] == str(delivery_id)
    assert body["data"] == {"batch_id": "b-9", "succeeded": 3}

    # Stored in a shape no serializer here would produce, so an attempt that
    # rebuilds the body from the parsed payload cannot reproduce it.
    stored = json.dumps(body, indent=3, sort_keys=True) + "\n"
    row.payload = stored
    db_session.commit()

    receiver.respond = lambda request: httpx.Response(500)
    for _ in range(3):
        webhooks.attempt_delivery(delivery_id)

    assert len(receiver.requests) == 3
    assert {r.headers["x-certforge-event-id"] for r in receiver.requests} == {str(delivery_id)}
    assert [r.content for r in receiver.requests] == [stored.encode("utf-8")] * 3


# -- signatures ----------------------------------------------------------------

def test_signature_256_signs_timestamp_dot_body_and_the_legacy_header_is_unchanged(
    db_session, receiver
):
    org = _org(db_session, "wh-sig")
    _endpoint(db_session, org)
    delivery_id = _delivery(db_session, org)

    webhooks.attempt_delivery(delivery_id)
    (request,) = receiver.requests
    raw = request.content
    h = request.headers

    assert h["content-type"] == "application/json"
    t = h["x-certforge-timestamp"]
    assert abs(int(t) - time.time()) < 60

    # Computed here from the raw request body, not through the module's own
    # helpers: the key is the whole secret string as UTF-8, the input is
    # b"<t>." + body, bytes throughout.
    expected_v1 = hmac.new(SECRET.encode("utf-8"), t.encode() + b"." + raw, hashlib.sha256).hexdigest()
    assert h["x-certforge-signature-256"] == f"t={t},v1={expected_v1}"

    # The deprecated header, byte-for-byte as the original dispatcher built it.
    expected_legacy = hmac.new(SECRET.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    assert h["x-certforge-signature"] == expected_legacy


# -- the batch writes rows, never requests ----------------------------------------

@pytest.fixture
def no_real_http(monkeypatch):
    """Trap httpx below the seam: any real request is recorded and hangs up."""
    calls = []

    def trap(self, request):
        calls.append(str(request.url))
        raise httpx.ReadTimeout("hung receiver", request=request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", trap)
    return calls


def test_a_batch_with_a_hanging_endpoint_completes_without_any_http_call(
    client, db_session, no_real_http
):
    batch = staged_batch(client, db_session, "wh-batch", "Ada", "Grace")
    org = db_session.get(Organization, batch.org_id)
    endpoint = _endpoint(db_session, org)
    _endpoint(db_session, org, events=())                  # not subscribed
    _endpoint(db_session, org, active=False)               # switched off

    with patch.object(worker.deliver_webhook, "defer_async", new=AsyncMock()) as defer, \
         patch.object(worker.retry_delivery, "defer_async", new=AsyncMock()):
        asyncio.run(worker.process_batch.func(batch_id_str=str(batch.id)))

    assert no_real_http == []
    db_session.expire_all()
    assert db_session.get(CredentialBatch, batch.id).status == "completed"

    rows = db_session.query(WebhookDelivery).filter_by(org_id=org.id).all()
    assert [r.endpoint_id for r in rows] == [endpoint.id]
    (row,) = rows
    assert row.status == webhooks.STATUS_PENDING
    assert row.attempts == 0
    body = json.loads(row.payload)
    assert body["data"]["batch_id"] == str(batch.id)
    assert body["data"]["succeeded"] == 2
    defer.assert_awaited_once_with(delivery_id=str(row.id))


def test_a_batch_that_rolls_back_leaves_no_row_and_queues_no_job(
    client, db_session, monkeypatch
):
    batch = staged_batch(client, db_session, "wh-rollback", "Ada")
    org = db_session.get(Organization, batch.org_id)
    endpoint = _endpoint(db_session, org)

    real_create = worker.create_webhook_deliveries

    def create_then_poison(session, *args, **kwargs):
        ids = real_create(session, *args, **kwargs)
        # A NOT NULL violation that only surfaces at the batch's final commit,
        # after the delivery rows are in the session.
        session.add(WebhookDelivery(endpoint_id=endpoint.id, org_id=org.id, event="x", payload=None))
        return ids

    monkeypatch.setattr(worker, "create_webhook_deliveries", create_then_poison)
    defer_async, defer_sync = AsyncMock(), MagicMock()
    monkeypatch.setattr(worker.deliver_webhook, "defer_async", defer_async)
    monkeypatch.setattr(worker.deliver_webhook, "defer", defer_sync)
    monkeypatch.setattr(worker.retry_delivery, "defer_async", AsyncMock())

    with pytest.raises(Exception):
        asyncio.run(worker.process_batch.func(batch_id_str=str(batch.id)))

    db_session.expire_all()
    assert db_session.query(WebhookDelivery).filter_by(endpoint_id=endpoint.id).count() == 0
    defer_async.assert_not_awaited()
    defer_sync.assert_not_called()


# -- retention ------------------------------------------------------------------

def test_rows_older_than_30_days_go_on_the_next_insert_for_that_endpoint(db_session):
    org = _org(db_session, "wh-retention")
    endpoint = _endpoint(db_session, org)
    other = _endpoint(db_session, org, events=())  # gets no new row, so keeps its old one
    now = datetime.now(timezone.utc)

    def old_row(ep, age):
        row = WebhookDelivery(
            endpoint_id=ep.id, org_id=org.id, event="batch.completed", payload="{}",
            status=webhooks.STATUS_SUCCEEDED, attempts=1, created_at=now - age,
        )
        db_session.add(row)
        db_session.commit()
        return row.id

    expired = old_row(endpoint, timedelta(days=31))
    recent = old_row(endpoint, timedelta(days=29))
    elsewhere = old_row(other, timedelta(days=31))

    new_id = _delivery(db_session, org)

    db_session.expire_all()
    remaining = {r.id for r in db_session.query(WebhookDelivery).filter_by(org_id=org.id)}
    assert expired not in remaining
    assert {recent, elsewhere, new_id} <= remaining


# -- odds and ends --------------------------------------------------------------

def test_an_inactive_endpoint_is_abandoned_without_a_request(db_session, receiver):
    org = _org(db_session, "wh-inactive")
    endpoint = _endpoint(db_session, org)
    delivery_id = _delivery(db_session, org)
    endpoint.active = False
    db_session.commit()

    assert webhooks.attempt_delivery(delivery_id) is None
    assert receiver.requests == []
    assert _row(db_session, delivery_id).status == webhooks.STATUS_ABANDONED


def test_a_succeeded_delivery_is_not_sent_again(db_session, receiver):
    org = _org(db_session, "wh-done")
    _endpoint(db_session, org)
    delivery_id = _delivery(db_session, org)
    webhooks.attempt_delivery(delivery_id)
    webhooks.attempt_delivery(delivery_id)
    assert len(receiver.requests) == 1


def test_the_attempt_timeout_is_ten_seconds():
    with _real_http_client() as c:
        assert c.timeout.read == 10.0 and c.timeout.connect == 10.0
