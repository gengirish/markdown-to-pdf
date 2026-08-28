"""Email delivery, and the record it leaves.

The defect these cover is not "email was broken". It is that the system could
not say what had happened. The first production batch issued three credentials,
no email arrived, AgentMail was healthy, and the send branch demonstrably ran —
and nothing in the database could distinguish

    (a) recipient_email was empty, so the send was skipped silently, from
    (b) the send ran and the provider rejected it.

Both wrote nothing. So the assertion that matters most in this file is not that
a send succeeds; it is that (a) and (b) are never again the same row.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from api.core.principal import LIVE_PREFIX, TEST_PREFIX, hash_api_key
from api.models.api_key import ApiKey
from api.models.credential import (
    DELIVERY_FAILED,
    DELIVERY_UNKNOWN,
    NOT_REQUESTED,
    SENT,
    Credential,
)
from api.models.organization import Organization
from api.services.delivery import (
    MAX_DELIVERY_ATTEMPTS,
    deliver_credential_email,
    delivery_state,
    may_retry,
)

SEND = "api.services.delivery.agentmail_deliver"


def org_with_key(db_session, slug, raw_key, quota=500):
    org = db_session.query(Organization).filter_by(slug=slug).first()
    if org:
        return org
    org = Organization(slug=slug, name=slug.title(), tier="community", monthly_quota=quota)
    db_session.add(org)
    db_session.commit()
    db_session.add(ApiKey(org_id=org.id, key_hash=hash_api_key(raw_key), label="k"))
    db_session.commit()
    return org


def issue(client, slug, raw, **body):
    payload = {"recipient_name": "Ada Lovelace", "title": "Analytical Engines"}
    payload.update(body)
    return client.post(
        f"/api/v1/orgs/{slug}/credentials",
        headers={"Authorization": f"Bearer {raw}"},
        json=payload,
    )


def fetch(db_session, public_id):
    return db_session.query(Credential).filter_by(public_id=public_id).first()


# -- the distinction the whole change exists for ------------------------------

def test_a_skipped_send_and_a_failed_send_are_not_the_same_row(client, db_session):
    """The exact ambiguity that made the first incident unanswerable."""
    raw = LIVE_PREFIX + "distinguish-key"
    org_with_key(db_session, "distinguish", raw)

    # (a) nothing was asked of us
    skipped = issue(client, "distinguish", raw).json()["data"]

    # (b) we asked, and the provider said no
    with patch(SEND, return_value=(False, "AgentMail rejected the request (403)")):
        failed = issue(
            client, "distinguish", raw,
            recipient_email="ada@example.com", send_email=True,
        ).json()["data"]

    a = fetch(db_session, skipped["id"])
    b = fetch(db_session, failed["id"])

    assert a.delivery_status == NOT_REQUESTED
    assert b.delivery_status == DELIVERY_FAILED
    assert a.delivery_status != b.delivery_status

    # And each says why, without anyone reading a log.
    assert "send_email" in a.delivery_error
    assert "403" in b.delivery_error


# -- what each outcome records ------------------------------------------------

def test_a_successful_send_is_recorded_with_a_timestamp(client, db_session):
    raw = LIVE_PREFIX + "sent-key"
    org_with_key(db_session, "sent-org", raw)

    before = datetime.now(timezone.utc) - timedelta(seconds=1)
    with patch(SEND, return_value=(True, "")) as send:
        r = issue(
            client, "sent-org", raw,
            recipient_email="ada@example.com", send_email=True,
        )
    assert send.call_count == 1

    cred = fetch(db_session, r.json()["data"]["id"])
    assert cred.delivery_status == SENT
    assert cred.delivery_error is None
    assert cred.delivery_attempts == 1
    # SQLite drops tzinfo on read where Postgres keeps it, so the test database
    # hands back a naive datetime. Normalised here rather than weakened to a
    # not-None check: the point is that a real timestamp was written.
    assert cred.delivered_at is not None
    stamped = cred.delivered_at
    if stamped.tzinfo is None:
        stamped = stamped.replace(tzinfo=timezone.utc)
    assert stamped >= before


def test_a_failed_send_keeps_the_providers_own_words(client, db_session):
    raw = LIVE_PREFIX + "failed-key"
    org_with_key(db_session, "failed-org", raw)

    with patch(SEND, return_value=(False, "AgentMail inbox not found")):
        r = issue(
            client, "failed-org", raw,
            recipient_email="ada@example.com", send_email=True,
        )

    cred = fetch(db_session, r.json()["data"]["id"])
    assert cred.delivery_status == DELIVERY_FAILED
    # A boolean would not answer a support ticket. The message does.
    assert cred.delivery_error == "AgentMail inbox not found"
    assert cred.delivered_at is None
    assert cred.delivery_attempts == 1


def test_an_address_less_credential_records_why_no_send_happened(client, db_session):
    """send_email was asked for, but there is nobody to send to."""
    raw = LIVE_PREFIX + "noaddr-key"
    org_with_key(db_session, "noaddr-org", raw)

    with patch(SEND) as send:
        r = issue(client, "noaddr-org", raw, send_email=True)
    send.assert_not_called()

    cred = fetch(db_session, r.json()["data"]["id"])
    assert cred.delivery_status == NOT_REQUESTED
    assert "No recipient email" in cred.delivery_error


def test_an_unexpected_exception_is_recorded_not_raised(db_session):
    """A delivery failure must not lose a credential that issued correctly."""
    cred = Credential(
        public_id="CF-2026-BOOM", org_id=org_with_key(db_session, "boom-org", LIVE_PREFIX + "b").id,
        recipient_name="Ada", recipient_email="ada@example.com",
        title="T", metadata_={}, hmac_signature="x", status="issued",
    )
    with patch(SEND, side_effect=RuntimeError("connection reset")):
        assert deliver_credential_email(cred) is False

    assert cred.delivery_status == DELIVERY_FAILED
    assert "connection reset" in cred.delivery_error


# -- a test key must not reach a real person ----------------------------------

def test_a_test_key_never_sends_even_when_asked(client, db_session):
    """`is_test` always documented "nothing is emailed". Until send_email
    existed that was vacuously true; now it has to actually hold."""
    raw = TEST_PREFIX + "delivery-sandbox-key"
    org_with_key(db_session, "delivery-sandbox-org", raw)

    with patch(SEND) as send:
        r = issue(
            client, "delivery-sandbox-org", raw,
            recipient_email="real.person@example.com", send_email=True,
        )
    send.assert_not_called()

    cred = fetch(db_session, r.json()["data"]["id"])
    assert cred.delivery_status == NOT_REQUESTED
    assert "cf_test_" in cred.delivery_error


# -- retry policy -------------------------------------------------------------

@pytest.mark.parametrize(
    "status,attempts,expected",
    [
        (DELIVERY_FAILED, 1, True),
        (DELIVERY_FAILED, MAX_DELIVERY_ATTEMPTS - 1, True),
        (DELIVERY_FAILED, MAX_DELIVERY_ATTEMPTS, False),
        (SENT, 1, False),
        (NOT_REQUESTED, 0, False),
        # The one that would mail people served months ago.
        (DELIVERY_UNKNOWN, 0, False),
    ],
)
def test_only_bounded_failures_are_retried(status, attempts, expected):
    cred = Credential(
        public_id="CF-2026-RETRY", recipient_name="A", title="T",
        metadata_={}, hmac_signature="x",
        delivery_status=status, delivery_attempts=attempts,
    )
    assert may_retry(cred) is expected


def test_a_backfilled_row_is_never_treated_as_delivered_or_failed():
    """`unknown` means no record exists — it must not be read either way."""
    cred = Credential(
        public_id="CF-2026-OLD", recipient_name="A", title="T",
        metadata_={}, hmac_signature="x",
        delivery_status=DELIVERY_UNKNOWN, delivery_attempts=0,
    )
    state = delivery_state(cred)
    assert state["status"] == DELIVERY_UNKNOWN
    assert state["delivered_at"] is None
    assert state["may_retry"] is False


# -- the API surface ----------------------------------------------------------

def test_issuing_returns_the_delivery_outcome(client, db_session):
    raw = LIVE_PREFIX + "resp-key"
    org_with_key(db_session, "resp-org", raw)

    with patch(SEND, return_value=(True, "")):
        r = issue(
            client, "resp-org", raw,
            recipient_email="ada@example.com", send_email=True,
        )
    delivery = r.json()["data"]["delivery"]
    assert delivery["status"] == SENT
    assert delivery["delivered_at"] is not None
    assert delivery["attempts"] == 1


def test_fetching_a_credential_answers_did_they_get_the_email(client, db_session):
    """Support must be able to answer this from the API, not from a Fly log
    buffer that holds about a hundred lines."""
    raw = LIVE_PREFIX + "get-key"
    org_with_key(db_session, "get-org", raw)

    with patch(SEND, return_value=(False, "AgentMail rejected the request (403)")):
        issued = issue(
            client, "get-org", raw,
            recipient_email="ada@example.com", send_email=True,
        ).json()["data"]

    r = client.get(
        f"/api/v1/orgs/get-org/credentials/{issued['id']}",
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert r.status_code == 200
    delivery = r.json()["data"]["delivery"]
    assert delivery["status"] == DELIVERY_FAILED
    assert "403" in delivery["error"]
    assert delivery["may_retry"] is True


def test_omitting_send_email_keeps_the_old_behaviour(client, db_session):
    """Every caller written before send_email existed must be unaffected."""
    raw = LIVE_PREFIX + "compat-key"
    org_with_key(db_session, "compat-org", raw)

    with patch(SEND) as send:
        r = issue(client, "compat-org", raw, recipient_email="ada@example.com")
    send.assert_not_called()
    assert r.status_code == 201
    assert r.json()["data"]["delivery"]["status"] == NOT_REQUESTED


def test_the_credential_list_flags_delivery_per_row(client, db_session):
    """The list is where someone notices a batch went undelivered.

    Only the status, not the whole delivery object — the list flags which rows
    need attention and the detail route explains why.
    """
    raw = LIVE_PREFIX + "list-delivery-key"
    org_with_key(db_session, "list-delivery", raw)

    with patch(SEND, return_value=(False, "AgentMail rejected the request (403)")):
        issue(client, "list-delivery", raw,
              recipient_email="ada@example.com", send_email=True)
    issue(client, "list-delivery", raw)  # no delivery asked for

    r = client.get(
        "/api/v1/orgs/list-delivery/credentials",
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert r.status_code == 200, r.text
    statuses = {item["delivery_status"] for item in r.json()["data"]["items"]}
    assert statuses == {DELIVERY_FAILED, NOT_REQUESTED}


# -- the message itself --------------------------------------------------------
#
# The first version of this was four lines of bare HTML. It delivered fine, and
# looked nothing like the branded certificate email the legacy product sends —
# nothing here asserted otherwise, which is why it shipped.

def _sample_credential(db_session, **kw):
    org = org_with_key(db_session, "email-shape", LIVE_PREFIX + "email-shape-key")
    cred = Credential(
        public_id="CF-2026-EMAILTST",
        org_id=org.id,
        recipient_name=kw.get("recipient_name", "Ada Lovelace"),
        recipient_email="ada@example.com",
        title=kw.get("title", "Analytical Engines"),
        metadata_={},
        hmac_signature="x",
        status="issued",
        issued_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
    )
    return cred, org


def test_the_email_carries_the_branded_layout(db_session):
    from api.services.delivery import build_credential_email

    cred, org = _sample_credential(db_session)
    subject, text, html = build_credential_email(cred, "https://example.test/v/1", org)

    assert subject == "Your credential for Analytical Engines"
    for marker in (
        "Verified &amp; Authentic",
        "This Credential is Awarded To",
        "View Your Credential",
        "Download PDF",
        "Credential ID",
        "Ada Lovelace",
        "Analytical Engines",
    ):
        assert marker in html, f"the email lost {marker!r}"

    # Both links, so a recipient whose client blocks the button still has a way.
    assert "https://example.test/v/1" in html
    assert "/pdf" in html
    assert "https://example.test/v/1" in text


def test_the_email_uses_the_organizations_branding(db_session):
    from api.services.delivery import build_credential_email

    cred, org = _sample_credential(db_session)
    org.primary_color = "#123456"
    org.accent_color = "#abcdef"
    org.footer_text = "Issued by the Analytical Society"

    _, _, html = build_credential_email(cred, "https://example.test/v/1", org)
    assert "#123456" in html
    assert "#abcdef" in html
    assert "Issued by the Analytical Society" in html


def test_the_email_can_be_rebuilt_without_the_org(db_session):
    """The retry task loads a row, not a request context. An email that cannot
    be rebuilt from the credential alone can never be retried."""
    from api.services.delivery import build_credential_email

    cred, _ = _sample_credential(db_session)
    _, _, html = build_credential_email(cred, "https://example.test/v/1", None)
    assert "Ada Lovelace" in html
    assert "#d4af37" in html, "no fallback accent"


def test_recipient_names_are_escaped_into_the_email(db_session):
    """Names arrive from customer CSVs and this markup lands in a mail client."""
    from api.services.delivery import build_credential_email

    cred, org = _sample_credential(db_session, recipient_name="<script>alert(1)</script>")
    _, _, html = build_credential_email(cred, "https://example.test/v/1", org)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
