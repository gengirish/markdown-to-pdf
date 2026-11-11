"""
CertForge /api/v1 webhook receiver (standard library only).

Verifies ``X-CertForge-Signature-256``, rejects stale timestamps, and
deduplicates on ``X-CertForge-Event-Id``. See the "CertForge Webhooks" section
of the repository README for the wire format.

This is for the /api/v1 webhooks registered at
``POST /api/v1/orgs/{slug}/webhooks``. The legacy ``callback_url`` event
(``certificate.created``) is handled by ``examples/webhook_receiver.py``.

Usage:
    python examples/certforge_webhook_receiver.py            # self-check, no network
    CERTFORGE_WEBHOOK_SECRET=whsec_... \\
        python examples/certforge_webhook_receiver.py --serve [--port 8080]

The default (no arguments) runs a self-check: it signs a sample body and
verifies it, and asserts that a tampered body, a stale timestamp, a wrong
secret and a repeated event id are all refused. It exits non-zero on failure.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

TOLERANCE_SECONDS = 300  # reject timestamps more than 5 minutes from our clock
SIGNATURE_HEADER = "X-CertForge-Signature-256"
EVENT_ID_HEADER = "X-CertForge-Event-Id"


class VerificationError(Exception):
    pass


def sign(secret: str, timestamp: int, body: bytes) -> str:
    """The value CertForge sends in X-CertForge-Signature-256."""
    mac = hmac.new(secret.encode("utf-8"), f"{timestamp}.".encode("ascii") + body, hashlib.sha256)
    return f"t={timestamp},v1={mac.hexdigest()}"


def verify(secret: str, body: bytes, header: str | None, now: float | None = None) -> int:
    """Check a signature header against the raw body. Returns the timestamp.

    ``body`` must be the exact bytes received; re-serialized JSON will not match.
    """
    if not header:
        raise VerificationError("missing signature header")
    parts: dict[str, str] = {}
    for item in header.split(","):
        key, sep, value = item.strip().partition("=")
        if sep:
            parts.setdefault(key, value)
    t, received = parts.get("t", ""), parts.get("v1", "")
    if not t.isdigit() or not received:
        raise VerificationError("malformed signature header")
    timestamp = int(t)
    now = time.time() if now is None else now
    if abs(now - timestamp) > TOLERANCE_SECONDS:
        raise VerificationError("timestamp outside the 5-minute window")
    expected = sign(secret, timestamp, body).split("v1=", 1)[1]
    if not hmac.compare_digest(expected, received):
        raise VerificationError("signature mismatch")
    return timestamp


class SeenEvents:
    """In-memory event-id dedupe. Use a database table in production: this
    forgets everything on restart and is not shared between processes."""

    def __init__(self, ttl_seconds: int = 7 * 24 * 3600):
        self._ttl = ttl_seconds
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def first_time(self, event_id: str) -> bool:
        now = time.time()
        with self._lock:
            for key in [k for k, at in self._seen.items() if now - at > self._ttl]:
                del self._seen[key]
            if event_id in self._seen:
                return False
            self._seen[event_id] = now
            return True

    def forget(self, event_id: str) -> None:
        """Undo first_time() when processing failed, so the retry is handled."""
        with self._lock:
            self._seen.pop(event_id, None)


def handle_event(event: dict) -> None:
    """Your business logic. Only batch.completed is sent today."""
    data = event.get("data", {})
    if event.get("event") == "batch.completed":
        print(
            f"batch {data.get('batch_id')} {data.get('status')}: "
            f"{data.get('succeeded')} rendered, {data.get('failed')} failed, "
            f"{data.get('delivered')} emailed, {data.get('delivery_failed')} email failures"
        )
    else:
        print(f"ignoring event {event.get('event')!r}")


def make_handler(secret: str, seen: SeenEvents):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length)
            try:
                verify(secret, body, self.headers.get(SIGNATURE_HEADER))
            except VerificationError as exc:
                return self._reply(401, {"error": str(exc)})

            event_id = self.headers.get(EVENT_ID_HEADER)
            if not event_id:
                return self._reply(400, {"error": "missing event id"})
            if not seen.first_time(event_id):
                # Already processed: answer 2xx so CertForge stops retrying.
                return self._reply(200, {"status": "duplicate"})

            try:
                handle_event(json.loads(body))
            except Exception as exc:  # let CertForge retry
                seen.forget(event_id)
                return self._reply(500, {"error": f"handler failed: {exc}"})
            return self._reply(200, {"status": "ok"})

        def _reply(self, code: int, payload: dict):
            out = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

    return Handler


def self_check() -> int:
    secret = "whsec_" + "0" * 32
    body = json.dumps(
        {
            "event": "batch.completed",
            "delivery_id": "00000000-0000-0000-0000-000000000001",
            "data": {"batch_id": "b1", "status": "completed", "succeeded": 3, "failed": 0,
                     "delivered": 3, "delivery_failed": 0, "completed_at": "2026-11-11T00:00:00+00:00"},
        }
    ).encode("utf-8")
    now = int(time.time())
    header = sign(secret, now, body)

    def refused(why: str, *args, **kwargs) -> None:
        try:
            verify(*args, **kwargs)
        except VerificationError:
            return
        raise AssertionError(f"accepted {why}")

    try:
        assert verify(secret, body, header) == now, "valid delivery was refused"
        refused("a tampered body", secret, body.replace(b'"succeeded": 3', b'"succeeded": 4'), header)
        refused("a stale timestamp", secret, body, sign(secret, now - TOLERANCE_SECONDS - 1, body))
        refused("a future timestamp", secret, body, sign(secret, now + TOLERANCE_SECONDS + 1, body))
        refused("the wrong secret", secret, body, sign("whsec_other", now, body))
        legacy = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        refused("a body-only signature", secret, body, f"t={now},v1={legacy}")
        refused("a missing header", secret, body, None)
        seen = SeenEvents()
        assert seen.first_time("evt-1") and not seen.first_time("evt-1"), "duplicate event accepted"
    except (AssertionError, VerificationError) as exc:
        print(f"self-check FAILED: {exc}")
        return 1
    print("self-check passed: valid accepted; tampered, stale, future, wrong-secret, "
          "body-only, unsigned and duplicate refused")
    return 0


def serve(port: int) -> None:
    secret = os.environ.get("CERTFORGE_WEBHOOK_SECRET")
    if not secret:
        sys.exit("Set CERTFORGE_WEBHOOK_SECRET to the whsec_... value returned when the endpoint was created.")
    server = HTTPServer(("0.0.0.0", port), make_handler(secret, SeenEvents()))
    print(f"Listening for CertForge webhooks on :{port}")
    server.serve_forever()


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--serve" in args:
        port = int(args[args.index("--port") + 1]) if "--port" in args else 8080
        serve(port)
    else:
        sys.exit(self_check())
