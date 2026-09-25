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
    shown verbatim in the dashboard."""
    ok, message = email_mod.agentmail_deliver(
        to_email="ada@example.com", subject="s", text="t", html="<p>h</p>",
        link_hint="credential",
    )

    assert message == "Daily send limit exceeded. Share the credential link instead."
