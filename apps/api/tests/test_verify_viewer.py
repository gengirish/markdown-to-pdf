"""Regression tests for the CertForge credential viewer and badge export."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.core.config import CERTFORGE_WEB_URL
from api.core.crypto import hmac_sign
from api.models.credential import Credential
from api.models.organization import Organization

XSS = "<script>alert(1)</script>"


def _issue_credential(
    db_session: Session,
    public_id: str,
    *,
    slug: str,
    name: str = "Alice",
    title: str = "Advanced Widgetry",
    pdf_url: str | None = None,
    status: str = "issued",
) -> Credential:
    """Insert an org and one credential straight into the test database.

    Goes around the API because the bulk-issue route needs a paid tier, a
    template and the background worker; none of that is what these tests are
    about.
    """
    org_id = uuid.uuid4()
    db_session.add(Organization(id=org_id, name="Viewer Org", slug=slug))
    cred = Credential(
        public_id=public_id,
        org_id=org_id,
        recipient_name=name,
        recipient_email="alice@example.com",
        title=title,
        metadata_={},
        pdf_url=pdf_url,
        hmac_signature=hmac_sign(public_id),
        status=status,
    )
    db_session.add(cred)
    db_session.commit()
    return cred


def test_recipient_name_and_title_are_not_injected_as_html(
    client: TestClient, db_session
):
    """The viewer interpolated CSV-supplied fields into HTML unescaped.

    Recipient names and titles come from customer uploads, so a name of
    `<script>alert(1)</script>` executed for everyone who opened the public
    verification page.
    """
    _issue_credential(
        db_session,
        "CF-2026-XSSNAME1",
        slug="xss-name-org",
        name=XSS,
        title=XSS,
    )

    res = client.get("/verify/CF-2026-XSSNAME1")

    assert res.status_code == 200
    assert "<script>alert(1)</script>" not in res.text
    # The value is still shown, just as text rather than as markup.
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in res.text


def test_viewer_has_no_link_to_the_nonexistent_download_route(
    client: TestClient, db_session
):
    """The Download PDF button pointed at /api/v1/verify/{id}/download, a 404."""
    _issue_credential(db_session, "CF-2026-NOPDF001", slug="no-pdf-org")

    res = client.get("/verify/CF-2026-NOPDF001")

    assert res.status_code == 200
    assert "/download" not in res.text
    assert "Download PDF" not in res.text


def test_viewer_links_the_stored_pdf_when_the_credential_has_one(
    client: TestClient, db_session
):
    """A credential that does have a rendered PDF still offers it."""
    _issue_credential(
        db_session,
        "CF-2026-HASPDF01",
        slug="has-pdf-org",
        pdf_url="https://cdn.example.com/certs/haspdf01.pdf",
    )

    res = client.get("/verify/CF-2026-HASPDF01")

    assert res.status_code == 200
    assert 'href="https://cdn.example.com/certs/haspdf01.pdf"' in res.text
    assert "Download PDF" in res.text


def test_javascript_scheme_in_pdf_url_is_not_rendered_as_a_link(
    client: TestClient, db_session
):
    """Escaping alone leaves a `javascript:` href intact, so the scheme is checked."""
    _issue_credential(
        db_session,
        "CF-2026-JSHREF01",
        slug="js-href-org",
        pdf_url="javascript:alert(1)",
    )

    res = client.get("/verify/CF-2026-JSHREF01")

    assert res.status_code == 200
    assert "javascript:" not in res.text


def test_badge_urls_point_at_certforge_not_the_legacy_certificate_host(
    client: TestClient, db_session
):
    """Issuer and achievement IDs were hardcoded to certs.intelliforge.tech.

    badge.json only serves DB-backed CertForge credentials, and the achievement
    ID additionally pointed at /api/v1/credentials/{id}, which does not exist.
    """
    _issue_credential(db_session, "CF-2026-BADGE001", slug="badge-org")

    res = client.get("/credentials/CF-2026-BADGE001/badge.json")

    assert res.status_code == 200
    body = res.json()

    assert body["issuer"]["id"] == f"{CERTFORGE_WEB_URL}/orgs/badge-org"
    assert (
        body["credentialSubject"]["achievement"]["id"]
        == f"{CERTFORGE_WEB_URL}/verify/CF-2026-BADGE001"
    )
    assert "certs.intelliforge.tech" not in res.text
    assert "/api/v1/credentials/" not in res.text


def test_revoked_credential_viewer_does_not_leak_the_recipient(
    client: TestClient, db_session
):
    """A revoked credential must not render the card at all."""
    _issue_credential(
        db_session,
        "CF-2026-REVOKED1",
        slug="revoked-org",
        name="Mallory",
        status="revoked",
    )

    res = client.get("/verify/CF-2026-REVOKED1")

    assert res.status_code == 404
    assert "Mallory" not in res.text
