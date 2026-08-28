"""The /api/v1 limiter: what it counts, and who it counts it against.

Quota bounds the month; this bounds the minute. The interesting part is not the
counting -- it is the bucket key, because every way of getting the key wrong is
a way for a caller to get free budget (rotate IPs, prepend a header) or for an
innocent caller to be throttled by a stranger sharing their NAT.

Nothing here sleeps. The limiter takes an injectable clock precisely so a
60-second window can be rolled forward in one line.
"""

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.core.rate_limit import (
    RateLimiter,
    bucket_key,
    client_ip,
    rate_limit,
)


class FakeClock:
    """A clock the test drives, so a window can be rolled without waiting."""

    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


LIVE_KEY_A = "cf_live_" + "a" * 24
LIVE_KEY_B = "cf_live_" + "b" * 24


def make_app(limiter: RateLimiter) -> FastAPI:
    """A throwaway app carrying only the limiter under test.

    Built here rather than by wiring a real route, because the /api/v1 routes
    belong to other work in flight. index.py's exception handler is attached so
    the 429 body is the one production would actually emit.
    """
    from api.index import http_exception_handler

    app = FastAPI()
    app.add_exception_handler(HTTPException, http_exception_handler)

    @app.get("/api/v1/guarded")
    def guarded(_=Depends(rate_limit(limiter=limiter))):
        return {"ok": True}

    return app


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def limiter(clock):
    return RateLimiter(limit=3, window=60, clock=clock)


@pytest.fixture
def app_client(limiter):
    with TestClient(make_app(limiter)) as c:
        yield c


def key_auth(raw: str) -> dict:
    return {"Authorization": f"Bearer {raw}"}


def forwarded(*chain: str) -> dict:
    """An X-Forwarded-For as it arrives at uvicorn, outermost hop last."""
    return {"X-Forwarded-For": ", ".join(chain)}


# -- counting ---------------------------------------------------------------


def test_requests_under_the_limit_pass(app_client):
    for _ in range(3):
        r = app_client.get("/api/v1/guarded", headers=key_auth(LIVE_KEY_A))
        assert r.status_code == 200, r.text


def test_the_request_over_the_limit_is_refused(app_client):
    for _ in range(3):
        assert app_client.get("/api/v1/guarded", headers=key_auth(LIVE_KEY_A)).status_code == 200

    r = app_client.get("/api/v1/guarded", headers=key_auth(LIVE_KEY_A))
    assert r.status_code == 429
    assert r.headers["X-RateLimit-Remaining"] == "0"
    # Retry-After is what a well-behaved client actually reads.
    assert int(r.headers["Retry-After"]) > 0


def test_remaining_counts_down_and_reports_the_window(app_client):
    seen = [
        app_client.get("/api/v1/guarded", headers=key_auth(LIVE_KEY_A)).headers["X-RateLimit-Remaining"]
        for _ in range(3)
    ]
    assert seen == ["2", "1", "0"]

    r = app_client.get("/api/v1/guarded", headers=key_auth(LIVE_KEY_B))
    assert r.headers["X-RateLimit-Limit"] == "3"
    assert 0 < int(r.headers["X-RateLimit-Reset"]) <= 60


def test_the_window_rolls(app_client, clock):
    for _ in range(3):
        assert app_client.get("/api/v1/guarded", headers=key_auth(LIVE_KEY_A)).status_code == 200
    assert app_client.get("/api/v1/guarded", headers=key_auth(LIVE_KEY_A)).status_code == 429

    # Still inside the window: the refusal stands.
    clock.advance(59)
    assert app_client.get("/api/v1/guarded", headers=key_auth(LIVE_KEY_A)).status_code == 429

    # Past it: the oldest hits have aged out and the budget is back.
    clock.advance(2)
    assert app_client.get("/api/v1/guarded", headers=key_auth(LIVE_KEY_A)).status_code == 200


def test_a_refused_request_does_not_extend_the_window(limiter, clock):
    for _ in range(3):
        assert limiter.check("k").allowed

    # A client that ignores Retry-After and hammers must not push its own
    # window forward, or it could never get back in.
    clock.advance(30)
    for _ in range(10):
        assert not limiter.check("k").allowed

    clock.advance(31)
    assert limiter.check("k").allowed


def test_a_non_positive_limit_disables_rather_than_closes(clock):
    off = RateLimiter(limit=0, window=60, clock=clock)
    for _ in range(50):
        assert off.check("k").allowed


def test_reset_clears_one_named_bucket_without_touching_the_others(limiter):
    for _ in range(3):
        limiter.check("a")
        limiter.check("b")
    assert not limiter.check("a").allowed
    assert not limiter.check("b").allowed

    limiter.reset("a")
    assert limiter.check("a").allowed
    # b was not named, so b is still exhausted.
    assert not limiter.check("b").allowed


def test_reset_with_no_argument_clears_every_bucket(limiter):
    for _ in range(3):
        limiter.check("a")
        limiter.check("b")
    assert not limiter.check("a").allowed

    limiter.reset()
    assert limiter.check("a").allowed
    assert limiter.check("b").allowed


# -- who the budget is charged to -------------------------------------------


def test_two_api_keys_get_separate_buckets(app_client):
    for _ in range(3):
        assert app_client.get("/api/v1/guarded", headers=key_auth(LIVE_KEY_A)).status_code == 200
    assert app_client.get("/api/v1/guarded", headers=key_auth(LIVE_KEY_A)).status_code == 429

    # A second key holder must not inherit the first one's exhaustion.
    r = app_client.get("/api/v1/guarded", headers=key_auth(LIVE_KEY_B))
    assert r.status_code == 200
    assert r.headers["X-RateLimit-Remaining"] == "2"


def test_one_key_from_two_ips_shares_one_bucket(app_client):
    """Rotating IPs must not buy more budget."""
    for i in range(3):
        r = app_client.get(
            "/api/v1/guarded",
            headers={**key_auth(LIVE_KEY_A), **forwarded(f"10.0.0.{i}", "vercel-edge")},
        )
        assert r.status_code == 200

    r = app_client.get(
        "/api/v1/guarded",
        headers={**key_auth(LIVE_KEY_A), **forwarded("10.0.0.99", "vercel-edge")},
    )
    assert r.status_code == 429


def test_one_ip_with_two_keys_does_not_throttle_a_stranger(app_client):
    """Two key holders behind one NAT are independent."""
    shared = forwarded("203.0.113.7", "vercel-edge")
    for _ in range(3):
        assert (
            app_client.get("/api/v1/guarded", headers={**key_auth(LIVE_KEY_A), **shared}).status_code
            == 200
        )
    assert (
        app_client.get("/api/v1/guarded", headers={**key_auth(LIVE_KEY_A), **shared}).status_code == 429
    )
    assert (
        app_client.get("/api/v1/guarded", headers={**key_auth(LIVE_KEY_B), **shared}).status_code == 200
    )


def test_a_clerk_user_is_keyed_by_user_id_not_by_token(monkeypatch):
    """Session tokens rotate on refresh; the bucket must not rotate with them."""
    from dataclasses import dataclass

    import api.core.auth as auth

    @dataclass
    class FakeUser:
        clerk_user_id: str

    def fake_optional_user(request):
        token = request.headers.get("Authorization", "")[7:]
        # Two different tokens, same human.
        return FakeUser(clerk_user_id="user_alice" if token.startswith("jwt_alice") else "user_bob")

    monkeypatch.setattr(auth, "get_optional_user", fake_optional_user)

    clock = FakeClock()
    limiter = RateLimiter(limit=2, window=60, clock=clock)
    with TestClient(make_app(limiter)) as c:
        assert c.get("/api/v1/guarded", headers=key_auth("jwt_alice_first")).status_code == 200
        assert c.get("/api/v1/guarded", headers=key_auth("jwt_alice_refreshed")).status_code == 200
        # Third call for the same human, whichever token she presents.
        assert c.get("/api/v1/guarded", headers=key_auth("jwt_alice_third")).status_code == 429
        # A different human still has her own budget.
        assert c.get("/api/v1/guarded", headers=key_auth("jwt_bob")).status_code == 200


def test_an_anonymous_caller_falls_back_to_ip(app_client):
    a = forwarded("198.51.100.1", "vercel-edge")
    b = forwarded("198.51.100.2", "vercel-edge")

    for _ in range(3):
        assert app_client.get("/api/v1/guarded", headers=a).status_code == 200
    assert app_client.get("/api/v1/guarded", headers=a).status_code == 429
    # A different anonymous caller is a different bucket.
    assert app_client.get("/api/v1/guarded", headers=b).status_code == 200


def test_an_unverifiable_token_is_treated_as_anonymous(app_client, monkeypatch):
    """A flood of bad credentials must not be free, and must not be per-token."""
    import api.core.auth as auth

    monkeypatch.setattr(auth, "get_optional_user", lambda request: None)

    ip = forwarded("198.51.100.9", "vercel-edge")
    for i in range(3):
        assert (
            app_client.get("/api/v1/guarded", headers={**key_auth(f"garbage_{i}"), **ip}).status_code
            == 200
        )
    # Same IP, yet another junk token: still the same bucket.
    assert (
        app_client.get("/api/v1/guarded", headers={**key_auth("garbage_9"), **ip}).status_code == 429
    )


# -- the spoofing guard legacy explicitly carries ---------------------------


def test_prepending_x_forwarded_for_does_not_escape_the_bucket(app_client):
    """A caller can only *prepend* to X-Forwarded-For; entries are appended by
    each hop it passes through. Counting from the right means the entries a
    caller injects sit ahead of the one we read, so they buy nothing."""
    honest = forwarded("192.0.2.50", "vercel-edge")
    for _ in range(3):
        assert app_client.get("/api/v1/guarded", headers=honest).status_code == 200
    assert app_client.get("/api/v1/guarded", headers=honest).status_code == 429

    # The same caller now injects a header before its request leaves. Vercel
    # and Fly still append what they saw, so the real client is still the 2nd
    # entry from the right -- and the bucket is still exhausted.
    spoofed = forwarded("1.1.1.1", "2.2.2.2", "192.0.2.50", "vercel-edge")
    assert app_client.get("/api/v1/guarded", headers=spoofed).status_code == 429


def test_client_ip_reads_the_hop_before_the_edge():
    """Unit-level statement of the same rule, independent of the buckets."""
    from fastapi import Request

    app = FastAPI()

    @app.get("/ip")
    def ip(request: Request):
        return {"ip": client_ip(request)}

    with TestClient(app) as c:
        assert c.get("/ip", headers=forwarded("203.0.113.5", "edge")).json()["ip"] == "203.0.113.5"
        # A caller-injected prefix does not move the entry we read.
        assert (
            c.get("/ip", headers=forwarded("evil", "203.0.113.5", "edge")).json()["ip"]
            == "203.0.113.5"
        )
        # A chain shorter than the configured hop count must not index past the
        # start -- a request that reached Fly directly still resolves.
        assert c.get("/ip", headers=forwarded("203.0.113.5")).json()["ip"] == "203.0.113.5"
        # No header at all: the socket peer.
        assert c.get("/ip").json()["ip"] == "testclient"


# -- the response shape -----------------------------------------------------


def test_a_refusal_renders_the_v1_envelope(app_client):
    for _ in range(3):
        app_client.get("/api/v1/guarded", headers=key_auth(LIVE_KEY_A))

    r = app_client.get("/api/v1/guarded", headers=key_auth(LIVE_KEY_A))
    assert r.status_code == 429
    body = r.json()
    assert body["success"] is False
    # The label core/envelope.py has carried since it was written.
    assert body["error"]["type"] == "rate_limit_exceeded"
    assert body["error"]["code"] == 429


def test_success_carries_the_self_pacing_headers(app_client):
    r = app_client.get("/api/v1/guarded", headers=key_auth(LIVE_KEY_A))
    assert r.status_code == 200
    assert r.headers["X-RateLimit-Limit"] == "3"
    assert r.headers["X-RateLimit-Remaining"] == "2"
    assert int(r.headers["X-RateLimit-Reset"]) > 0
    # Retry-After belongs on a refusal only.
    assert "Retry-After" not in r.headers


def test_an_upstream_resolved_principal_wins(app_client):
    """If something ahead of us already resolved the caller, believe it."""
    import uuid

    from fastapi import Request

    from api.core.principal import Principal

    app = FastAPI()

    key_id = uuid.uuid4()

    @app.get("/k")
    def k(request: Request):
        request.state.principal = Principal(kind="api_key", org_id=uuid.uuid4(), api_key_id=key_id)
        return {"key": bucket_key(request)}

    with TestClient(app) as c:
        assert c.get("/k", headers=key_auth(LIVE_KEY_A)).json()["key"] == f"key-id:{key_id}"
