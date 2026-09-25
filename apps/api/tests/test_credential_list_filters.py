"""The credential list's search and filters, and resending a credential's email.

Written for the dashboard's Credentials tab (CF-04), which had a list of six
rows and no way to find the seventh. Every filter narrows `total` too — the
"N total" beside a filtered list has to describe that list.
"""

import uuid
from unittest.mock import patch

from api.core.principal import LIVE_PREFIX, TEST_PREFIX, hash_api_key
from api.models.api_key import ApiKey
from api.models.credential import Credential
from api.models.organization import Organization
from api.models.template import Template
from api.services.delivery import MAX_DELIVERY_ATTEMPTS

SEND = "api.services.delivery.agentmail_deliver"
LIVE = LIVE_PREFIX + "filters-live"
TEST = TEST_PREFIX + "filters-test"


def make_org(db_session, slug=None):
    slug = slug or f"filters-{uuid.uuid4().hex[:8]}"
    org = Organization(slug=slug, name=slug.title(), tier="community", credential_quota_override=500)
    db_session.add(org)
    db_session.commit()
    for raw in (LIVE + slug, TEST + slug):
        db_session.add(ApiKey(org_id=org.id, key_hash=hash_api_key(raw), label=raw))
    db_session.commit()
    return slug


def auth(raw):
    return {"Authorization": f"Bearer {raw}"}


def issue(client, slug, raw, **body):
    payload = {"recipient_name": "Ada Lovelace", "title": "Analytical Engines"}
    payload.update(body)
    r = client.post(f"/api/v1/orgs/{slug}/credentials", headers=auth(raw), json=payload)
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def listing(client, slug, **params):
    r = client.get(f"/api/v1/orgs/{slug}/credentials", headers=auth(LIVE + slug), params=params)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def ids(page):
    return {item["id"] for item in page["items"]}


# -- search ------------------------------------------------------------------

def test_search_matches_name_email_and_title_case_insensitively(client, db_session):
    slug = make_org(db_session)
    a = issue(client, slug, LIVE + slug, recipient_name="Grace Hopper")
    b = issue(client, slug, LIVE + slug, recipient_email="linus@example.com")
    c = issue(client, slug, LIVE + slug, title="Compilers 101")

    assert ids(listing(client, slug, q="grace")) == {a}
    assert ids(listing(client, slug, q="LINUS@")) == {b}
    assert ids(listing(client, slug, q="compilers")) == {c}
    page = listing(client, slug, q="compilers")
    assert page["total"] == 1


def test_search_treats_like_wildcards_as_text(client, db_session):
    """An unescaped `%` matches everything, so "100%" would find every row."""
    slug = make_org(db_session)
    literal = issue(client, slug, LIVE + slug, title="Scored 100% on the exam")
    issue(client, slug, LIVE + slug, title="Scored 1000 on the exam")
    issue(client, slug, LIVE + slug, title="snake_case workshop")
    other = issue(client, slug, LIVE + slug, title="snakeXcase workshop")

    assert ids(listing(client, slug, q="100%")) == {literal}
    assert other not in ids(listing(client, slug, q="snake_case"))


# -- filters -----------------------------------------------------------------

def test_delivery_status_filter_finds_failed_emails(client, db_session):
    slug = make_org(db_session)
    with patch(SEND, return_value=(False, "AgentMail rejected the request (403)")):
        failed = issue(client, slug, LIVE + slug,
                       recipient_email="ada@example.com", send_email=True)
    issue(client, slug, LIVE + slug)  # not_requested

    page = listing(client, slug, delivery_status="failed")
    assert ids(page) == {failed}
    assert page["total"] == 1


def test_template_and_batch_filters(client, db_session):
    slug = make_org(db_session)
    org_id = db_session.query(Organization).filter_by(slug=slug).one().id
    templates = []
    for name in ("Workshop", "Internship"):
        tpl = Template(org_id=org_id, name=name, html_source="<p>{{name}}</p>", variables=[])
        db_session.add(tpl)
        db_session.commit()
        templates.append(str(tpl.id))

    a = issue(client, slug, LIVE + slug, template_id=templates[0])
    b = issue(client, slug, LIVE + slug, template_id=templates[1])

    page = listing(client, slug, template_id=templates[0])
    assert ids(page) == {a}
    assert page["items"][0]["template_id"] == templates[0]
    assert ids(listing(client, slug, template_id=templates[1])) == {b}

    assert listing(client, slug, batch_id="00000000-0000-0000-0000-000000000000")["total"] == 0
    r = client.get(f"/api/v1/orgs/{slug}/credentials", headers=auth(LIVE + slug),
                   params={"template_id": "not-a-uuid"})
    assert r.status_code == 400


def test_test_credentials_are_labelled_and_filterable(client, db_session):
    slug = make_org(db_session)
    live = issue(client, slug, LIVE + slug)
    test = issue(client, slug, TEST + slug)

    everything = listing(client, slug)
    flags = {item["id"]: item["is_test"] for item in everything["items"]}
    assert flags == {live: False, test: True}

    assert ids(listing(client, slug, test="only")) == {test}
    excluded = listing(client, slug, test="exclude")
    assert ids(excluded) == {live}
    assert excluded["total"] == 1


# -- resend ------------------------------------------------------------------

def resend(client, slug, public_id, raw=None):
    return client.post(
        f"/api/v1/orgs/{slug}/credentials/{public_id}/resend",
        headers=auth(raw or LIVE + slug),
    )


def test_resend_emails_a_sent_credential_again_and_counts_the_attempt(client, db_session):
    slug = make_org(db_session)
    with patch(SEND, return_value=(True, "ok")):
        public_id = issue(client, slug, LIVE + slug,
                          recipient_email="ada@example.com", send_email=True)
    with patch(SEND, return_value=(True, "ok")) as send:
        r = resend(client, slug, public_id)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["sent"] is True
    assert data["delivery"]["status"] == "sent"
    assert data["delivery"]["attempts"] == 2
    send.assert_called_once()


def test_resend_reports_a_provider_refusal_as_not_sent(client, db_session):
    slug = make_org(db_session)
    public_id = issue(client, slug, LIVE + slug, recipient_email="ada@example.com")
    with patch(SEND, return_value=(False, "AgentMail inbox not found")):
        r = resend(client, slug, public_id)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["sent"] is False
    assert data["delivery"]["error"] == "AgentMail inbox not found"


def test_resend_refuses_what_it_must_not_send(client, db_session):
    slug = make_org(db_session)
    no_address = issue(client, slug, LIVE + slug)
    test = issue(client, slug, TEST + slug, recipient_email="real@example.com")
    revoked = issue(client, slug, LIVE + slug, recipient_email="ada@example.com")
    assert client.post(f"/api/v1/orgs/{slug}/credentials/{revoked}/revoke",
                       headers=auth(LIVE + slug)).status_code == 200

    with patch(SEND, return_value=(True, "ok")) as send:
        for public_id in (no_address, test, revoked):
            assert resend(client, slug, public_id).status_code == 409, public_id
        assert resend(client, slug, "CF-NOPE").status_code == 404
    send.assert_not_called()


def test_resend_stops_at_the_attempt_ceiling(client, db_session):
    """Without a ceiling this endpoint mails one person on a loop."""
    slug = make_org(db_session)
    public_id = issue(client, slug, LIVE + slug, recipient_email="ada@example.com")
    with patch(SEND, return_value=(True, "ok")) as send:
        for _ in range(MAX_DELIVERY_ATTEMPTS):
            assert resend(client, slug, public_id).status_code == 200
        assert resend(client, slug, public_id).status_code == 409
    assert send.call_count == MAX_DELIVERY_ATTEMPTS


def test_resend_is_scoped_to_the_callers_org(client, db_session):
    slug = make_org(db_session)
    other = make_org(db_session)
    public_id = issue(client, slug, LIVE + slug, recipient_email="ada@example.com")
    with patch(SEND, return_value=(True, "ok")) as send:
        r = resend(client, other, public_id)
    assert r.status_code == 404
    send.assert_not_called()
