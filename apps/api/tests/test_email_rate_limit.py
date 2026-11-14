"""A provider refusal must come back at once, not after the SDK has waited.

Production, 25 September 2026: AgentMail's daily send limit was spent, and one
single-issuance request took two minutes to answer. The SDK retries a 429 twice
by default and sleeps on `retry-after` between tries, capped at 60 seconds — so
a limit that resets in fourteen hours bought two one-minute sleeps, holding the
request and the machine's one shared vCPU, before failing exactly as it would
have on the first try.

These drive the real SDK client through an httpx mock transport rather than a
fake `send`, because the defect lives inside the SDK's HTTP layer: a mock of
`messages.send` would pass whether or not the retries were switched off.
"""

import httpx
import pytest
from agentmail import AgentMail

from api.core import email as email_mod

# The body and headers AgentMail returned in production, trimmed.
RATE_LIMITED_BODY = {
    "name": "RateLimitError",
    "code": "rate_limit_exceeded",
    "message": "Daily send limit exceeded",
    "limit": 100,
    "window": "daily",
}


@pytest.fixture
def sdk(monkeypatch):
    """A real AgentMail client whose every send is answered with a 429."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(
            429,
            headers={"retry-after": "52642", "ratelimit-reset": "52642"},
            json=RATE_LIMITED_BODY,
        )

    client = AgentMail(
        api_key="test-key",
        httpx_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    # Sleeps are recorded, not taken, so a regression fails in milliseconds
    # instead of hanging the suite for two minutes.
    slept = []
    monkeypatch.setattr(
        "agentmail.core.http_client.time.sleep", lambda s: slept.append(s)
    )
    monkeypatch.setattr(email_mod, "_agentmail_client", client)
    monkeypatch.setattr(email_mod, "_agentmail_inbox_cached", "inbox@example.com")
    return calls, slept


def test_a_rate_limited_send_is_tried_once_and_never_sleeps(sdk):
    calls, slept = sdk

    ok, message = email_mod.agentmail_deliver(
        to_email="ada@example.com", subject="s", text="t", html="<p>h</p>",
        link_hint="credential",
    )

    assert ok is False
    assert len(calls) == 1, f"SDK retried the send: {len(calls)} requests"
    assert slept == [], f"SDK slept before failing: {slept}"


def test_the_refusal_reads_as_a_sentence(sdk):
    """It used to read "Daily send limit exceeded Share the credential link
    instead." — the provider's message has no full stop, and that string is
    shown verbatim in the dashboard. A volume refusal no longer carries the
    "share the link" advice: delivery.py adds when it will send instead."""
    ok, message = email_mod.agentmail_deliver(
        to_email="ada@example.com", subject="s", text="t", html="<p>h</p>",
        link_hint="credential",
    )

    assert message == "Daily send limit exceeded."


def test_a_volume_refusal_is_classified_with_the_providers_wait(sdk):
    """The caller must be able to tell "try after the reset" from "this will
    never work". Both used to arrive as a bare False, and the credential paid
    an attempt for each. See docs/email-daily-cap-plan.md."""
    result = email_mod.agentmail_deliver(
        to_email="ada@example.com", subject="s", text="t", html="<p>h</p>",
        link_hint="credential",
    )

    assert result.kind == email_mod.SEND_RATE_LIMITED
    assert result.retry_after is not None
    assert result.retry_after.total_seconds() == 52642


def test_a_non_volume_refusal_still_reads_as_a_sentence(monkeypatch):
    """The "share the link" advice stays on refusals that will not recover."""
    def handler(request):
        return httpx.Response(422, json={"name": "ValidationError", "message": "Invalid recipient"})

    client = AgentMail(api_key="k", httpx_client=httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(email_mod, "_agentmail_client", client)
    monkeypatch.setattr(email_mod, "_agentmail_inbox_cached", "inbox@example.com")

    result = email_mod.agentmail_deliver(
        to_email="ada@example.com", subject="s", text="t", html="<p>h</p>",
        link_hint="credential",
    )

    assert result.kind == email_mod.SEND_FAILED
    assert result[1] == "Invalid recipient. Share the credential link instead."


@pytest.mark.parametrize("headers, expected", [
    ({"Retry-After": "120"}, 120),
    ({"retry-after": "Wed, 12 Nov 2026 00:00:00 GMT"}, 3600),
    ({"ratelimit-reset": "30"}, 30),
    ({"retry-after": "soon"}, None),
    ({}, None),
    (None, None),
])
def test_retry_after_parsing(headers, expected):
    from datetime import datetime, timezone
    now = datetime(2026, 11, 11, 23, 0, tzinfo=timezone.utc)
    got = email_mod.parse_retry_after(headers, now=now)
    assert (got.total_seconds() if got is not None else None) == expected
