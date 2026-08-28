"""template_id resolution on single issuance, and the on-demand PDF endpoint.

Single-issue credentials never rendered a PDF at all before this — there was no
route for it, and the viewer's "Download PDF" button pointed at cred.pdf_url, a
column nothing has ever populated. These tests are the proof both now work.
"""

import uuid

import pytest

from api.core.principal import LIVE_PREFIX, hash_api_key
from api.models.api_key import ApiKey
from api.models.organization import Organization
from api.models.template import Template

SIMPLE_HTML = """<!DOCTYPE html>
<html><body>
<h1>{{name}}</h1>
<p>{{title}}</p>
<p>{{date}} - {{credential_id}}</p>
<p>{{issuer_name}}</p>
<img src="{{qr}}" />
</body></html>"""


def org_with_key(db_session, slug, raw_key, quota=50):
    org = Organization(slug=slug, name=slug.title(), tier="community", monthly_quota=quota)
    db_session.add(org)
    db_session.commit()
    db_session.add(ApiKey(org_id=org.id, key_hash=hash_api_key(raw_key), label="k"))
    db_session.commit()
    return org


def make_template(db_session, org_id=None, name="T", is_default=False):
    tpl = Template(
        org_id=org_id,
        name=name,
        html_source=SIMPLE_HTML,
        variables=["name", "title", "date", "credential_id", "qr", "issuer_name"],
        is_default=is_default,
    )
    db_session.add(tpl)
    db_session.commit()
    return tpl


def auth(raw):
    return {"Authorization": f"Bearer {raw}"}


def issue(client, slug, raw, **extra):
    payload = {"recipient_name": "Ada Lovelace", "title": "Analytical Engines", **extra}
    return client.post(f"/api/v1/orgs/{slug}/credentials", headers=auth(raw), json=payload)


# -- template_id on single issuance ------------------------------------------

def test_issuing_with_an_explicit_template_id_stores_and_returns_it(client, db_session):
    raw = LIVE_PREFIX + "tpl-key"
    org = org_with_key(db_session, "templated", raw)
    tpl = make_template(db_session, org_id=org.id, name="Custom")

    r = issue(client, "templated", raw, template_id=str(tpl.id))
    assert r.status_code == 201, r.text
    public_id = r.json()["data"]["id"]

    from api.models.credential import Credential

    row = db_session.query(Credential).filter_by(public_id=public_id).one()
    assert row.template_id == tpl.id


def test_a_template_id_from_another_org_is_rejected(client, db_session):
    raw = LIVE_PREFIX + "other-org-tpl-key"
    org_with_key(db_session, "borrower", raw)
    other_org = Organization(slug="owner-org", name="Owner Org", tier="community")
    db_session.add(other_org)
    db_session.commit()
    theirs = make_template(db_session, org_id=other_org.id, name="Theirs")

    r = issue(client, "borrower", raw, template_id=str(theirs.id))
    assert r.status_code == 404


def test_a_malformed_template_id_is_400_not_500(client, db_session):
    raw = LIVE_PREFIX + "bad-uuid-key"
    org_with_key(db_session, "badid", raw)

    r = issue(client, "badid", raw, template_id="not-a-uuid")
    assert r.status_code == 400


def test_no_template_id_resolves_a_default_and_is_verifiable(client, db_session):
    raw = LIVE_PREFIX + "default-tpl-key"
    org = org_with_key(db_session, "defaulted", raw)
    make_template(db_session, org_id=org.id, name="Org Default", is_default=True)

    r = issue(client, "defaulted", raw)
    assert r.status_code == 201, r.text
    public_id = r.json()["data"]["id"]

    v = client.get(f"/api/v1/verify/{public_id}")
    assert v.status_code == 200


def test_an_unknown_template_id_is_404(client, db_session):
    raw = LIVE_PREFIX + "unknown-tpl-key"
    org_with_key(db_session, "unknowntpl", raw)

    r = issue(client, "unknowntpl", raw, template_id=str(uuid.uuid4()))
    assert r.status_code == 404


# -- pdf_url in the issue response -------------------------------------------

def test_pdf_url_is_present_and_correctly_shaped(client, db_session):
    raw = LIVE_PREFIX + "pdfurl-key"
    org_with_key(db_session, "pdfurled", raw)

    r = issue(client, "pdfurled", raw)
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["pdf_url"].endswith(f"/credentials/{data['id']}/pdf")
    assert data["pdf_url"].startswith("http")


# -- GET /credentials/{public_id}/pdf ----------------------------------------

def test_pdf_endpoint_returns_a_pdf_for_a_live_credential(client, db_session):
    raw = LIVE_PREFIX + "pdfrender-key"
    org = org_with_key(db_session, "renderable", raw)
    # Org-scoped, not global: the global fallback is exercised elsewhere, and
    # a global default created here would leak into every later test's
    # resolve_template_id() lookup since these tests share one database.
    make_template(db_session, org_id=org.id, name="Org Default", is_default=True)

    public_id = issue(client, "renderable", raw).json()["data"]["id"]

    r = client.get(f"/credentials/{public_id}/pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_pdf_endpoint_404s_for_a_revoked_credential(client, db_session):
    raw = LIVE_PREFIX + "pdfrevoke-key"
    org = org_with_key(db_session, "pdfrevoked", raw)
    make_template(db_session, org_id=org.id, name="Org Default 2", is_default=True)

    public_id = issue(client, "pdfrevoked", raw).json()["data"]["id"]
    client.post(f"/api/v1/orgs/pdfrevoked/credentials/{public_id}/revoke", headers=auth(raw))

    r = client.get(f"/credentials/{public_id}/pdf")
    assert r.status_code == 404


def test_pdf_endpoint_404s_for_an_unknown_credential(client, db_session):
    r = client.get("/credentials/CF-2026-NOTREAL/pdf")
    assert r.status_code == 404


def test_pdf_endpoint_404s_when_no_template_can_be_resolved(client, db_session):
    """No global default seeded and no org default: nothing to render with."""
    raw = LIVE_PREFIX + "notemplate-key"
    org_with_key(db_session, "notemplated", raw)

    public_id = issue(client, "notemplated", raw).json()["data"]["id"]

    r = client.get(f"/credentials/{public_id}/pdf")
    assert r.status_code == 404
