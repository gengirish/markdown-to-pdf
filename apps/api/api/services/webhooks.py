"""Outbound /api/v1 webhooks: delivery rows, one attempt at a time, our retry schedule.

A delivery is a row (``WebhookDelivery``); each attempt is a Procrastinate job
(``deliver_webhook`` in api/core/worker.py) that calls ``attempt_delivery``
here and, if it returns a delay, defers itself again with ``schedule_in``.

Things that are easy to break:

- **Only a 2xx is success.** httpx does not raise on a 4xx or 5xx, so a 500
  used to be logged "Webhook dispatched" and forgotten.
- **The stored bytes are the body, every attempt.** ``payload`` is serialized
  once, when the row is created. An attempt never rebuilds it: the event id,
  the body and therefore the receiver's dedupe all stay the same on a retry.
- **``x-certforge-signature`` must not change.** It is HMAC(secret, body), and
  existing receivers verify it. It is deprecated in favour of
  ``X-CertForge-Signature-256``, which signs ``f"{t}.".encode() + body`` so a
  captured request cannot be replayed outside the timestamp window.
- **The HMAC key is the endpoint's whole ``secret`` string as UTF-8**,
  prefix included, exactly as the original dispatcher used it.
- **Retries run late, on purpose.** The machine scales to zero and nothing
  wakes it except inbound HTTP, so a retry due in five minutes runs at the
  next wake. No sweep and no keep-alive: either would hold Fly and Neon awake
  around the clock to save minutes on a retry. ``next_attempt_at`` makes the
  delay visible instead.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Mapping

import httpx

from api.models import get_db
from api.models.api_key import WebhookDelivery, WebhookEndpoint

logger = logging.getLogger(__name__)

EVENT_BATCH_COMPLETED = "batch.completed"

STATUS_PENDING = "pending"        # created, not attempted yet
STATUS_SUCCEEDED = "succeeded"    # a 2xx was received
STATUS_FAILED = "failed"          # the last attempt failed and another is scheduled
STATUS_ABANDONED = "abandoned"    # out of attempts; only a manual redeliver sends again

#: Delay before each retry, after the attempt it follows. 1 min, 5 min, 30 min,
#: 2 h, 6 h, 12 h: seven attempts over about 21 hours, then ``abandoned``.
RETRY_DELAYS_SECONDS: tuple[int, ...] = (60, 300, 1800, 7200, 21600, 43200)
MAX_ATTEMPTS = len(RETRY_DELAYS_SECONDS) + 1

ATTEMPT_TIMEOUT_SECONDS = 10.0
RETENTION = timedelta(days=30)
#: Same truncation as a credential's ``delivery_error``.
MAX_ERROR_LEN = 500


# -- the HTTP seam -------------------------------------------------------------

def http_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """The one place an outbound webhook client is built.

    Tests replace this with one wrapping ``httpx.MockTransport`` rather than
    patching httpx globally. Redirects are not followed: a 3xx is not a 2xx,
    and following one would POST the signed body to a host nobody registered.
    """
    return httpx.Client(
        timeout=ATTEMPT_TIMEOUT_SECONDS,
        transport=transport,
        follow_redirects=False,
    )


# -- signing -------------------------------------------------------------------

def legacy_signature(secret: str, body: bytes) -> str:
    """``x-certforge-signature``: HMAC-SHA256(secret, body). Deprecated, frozen."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def signature_v1(secret: str, timestamp: int, body: bytes) -> str:
    """The ``v1=`` value: HMAC-SHA256(secret, b"<t>." + body).

    Built from bytes. An f-string over ``body`` would sign ``b'...'``, the
    repr, which no receiver following the docs could reproduce.
    """
    signed = f"{timestamp}.".encode("utf-8") + body
    return hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()


def signed_headers(secret: str, delivery_id: uuid.UUID | str, body: bytes, timestamp: int) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-CertForge-Event-Id": str(delivery_id),
        "X-CertForge-Timestamp": str(timestamp),
        "X-CertForge-Signature-256": f"t={timestamp},v1={signature_v1(secret, timestamp, body)}",
        "x-certforge-signature": legacy_signature(secret, body),
    }


# -- creating rows ---------------------------------------------------------------

def serialize_payload(event: str, delivery_id: uuid.UUID, data: Mapping[str, Any]) -> str:
    """The body, once. ``event`` and ``data`` are the shape receivers already parse."""
    return json.dumps({"event": event, "delivery_id": str(delivery_id), "data": dict(data)})


def create_deliveries(session, org_id: uuid.UUID, event: str, data: Mapping[str, Any]) -> list[uuid.UUID]:
    """Insert one pending row per active endpoint of ``org_id`` subscribed to ``event``.

    Runs inside the caller's transaction and makes no HTTP call; the caller
    defers ``deliver_webhook`` for each returned id **after** it commits, so
    a rolled-back caller leaves neither a row nor a job.

    Retention happens here, on the write path: an endpoint's rows older than
    30 days are deleted when a new one is inserted for it. No timer.
    """
    now = datetime.now(timezone.utc)
    endpoints = (
        session.query(WebhookEndpoint)
        .filter_by(org_id=org_id, active=True)
        .all()
    )
    ids: list[uuid.UUID] = []
    for endpoint in endpoints:
        if event not in (endpoint.events or []):
            continue
        session.query(WebhookDelivery).filter(
            WebhookDelivery.endpoint_id == endpoint.id,
            WebhookDelivery.created_at < now - RETENTION,
        ).delete(synchronize_session=False)

        delivery_id = uuid.uuid4()
        session.add(
            WebhookDelivery(
                id=delivery_id,
                endpoint_id=endpoint.id,
                org_id=org_id,
                event=event,
                payload=serialize_payload(event, delivery_id, data),
                status=STATUS_PENDING,
                attempts=0,
                next_attempt_at=now,
                created_at=now,
            )
        )
        ids.append(delivery_id)
    return ids


# -- one attempt -----------------------------------------------------------------

def _retry_after_seconds(response: httpx.Response | None) -> float | None:
    if response is None:
        return None
    value = response.headers.get("retry-after")
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


def next_delay(attempts: int, response: httpx.Response | None = None) -> float | None:
    """Seconds until the next attempt after ``attempts`` failures, or None when out.

    ``Retry-After`` wins when it asks for longer than the schedule's step, but
    never for longer than the schedule's longest step, so a receiver cannot
    park a job in the queue for a year.
    """
    if attempts >= MAX_ATTEMPTS:
        return None
    delay = float(RETRY_DELAYS_SECONDS[attempts - 1])
    asked = _retry_after_seconds(response)
    if asked is not None and asked > delay:
        delay = min(asked, float(RETRY_DELAYS_SECONDS[-1]))
    return delay


def attempt_delivery(delivery_id: uuid.UUID) -> float | None:
    """Make one attempt at a delivery. Returns the seconds until the next one, or None.

    The row is read and the session closed before the POST, so a receiver
    that hangs for the full timeout holds no database connection.
    """
    with get_db() as session:
        row = session.get(WebhookDelivery, delivery_id)
        if row is None:
            # The endpoint was deleted (rows cascade) or retention removed it.
            logger.info("Webhook delivery %s no longer exists; nothing to send.", delivery_id)
            return None
        if row.status == STATUS_SUCCEEDED:
            return None
        endpoint = session.get(WebhookEndpoint, row.endpoint_id)
        if endpoint is None or not endpoint.active:
            row.status = STATUS_ABANDONED
            row.next_attempt_at = None
            row.last_error = "Endpoint is inactive."
            return None
        url, secret = endpoint.url, endpoint.secret
        body = row.payload.encode("utf-8")

    timestamp = int(time.time())
    headers = signed_headers(secret, delivery_id, body, timestamp)
    response: httpx.Response | None = None
    error: str | None = None
    try:
        with http_client() as client:
            response = client.post(url, content=body, headers=headers)
    except httpx.TimeoutException as exc:
        error = f"Timed out after {ATTEMPT_TIMEOUT_SECONDS:g}s: {exc}"
    except Exception as exc:  # network errors, bad URLs: all retried alike
        error = f"{type(exc).__name__}: {exc}"

    succeeded = response is not None and 200 <= response.status_code < 300
    if response is not None and not succeeded:
        error = f"HTTP {response.status_code}: {response.text[:200]}"

    now = datetime.now(timezone.utc)
    with get_db() as session:
        row = session.get(WebhookDelivery, delivery_id)
        if row is None:
            return None
        row.attempts = (row.attempts or 0) + 1
        row.last_status_code = response.status_code if response is not None else None
        if succeeded:
            row.status = STATUS_SUCCEEDED
            row.last_error = None
            row.delivered_at = now
            row.next_attempt_at = None
            logger.info("Webhook %s delivered to %s (%s)", delivery_id, url, response.status_code)
            return None

        row.last_error = (error or "Delivery failed.")[:MAX_ERROR_LEN]
        delay = next_delay(row.attempts, response)
        if delay is None:
            row.status = STATUS_ABANDONED
            row.next_attempt_at = None
            logger.warning(
                "Webhook %s abandoned after %s attempts: %s", delivery_id, row.attempts, row.last_error
            )
            return None
        row.status = STATUS_FAILED
        row.next_attempt_at = now + timedelta(seconds=delay)
        logger.warning(
            "Webhook %s attempt %s failed (%s); next in %ss",
            delivery_id, row.attempts, row.last_error, int(delay),
        )
        return delay
