"""Regression tests for the CertForge credential viewer and badge export."""

import json
import re
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.core.config import CERT_BRAND_NAME, CERTFORGE_API_URL, CERTFORGE_WEB_URL
from api.core.crypto import hmac_sign
from api.models.credential import Credential
from api.models.organization import Organization

XSS = "<script>alert(1)</script>"


def _meta(page: str, attr: str, value: str) -> str | None:
    """Pull one meta tag's content out of the rendered page.

    Deliberately not a substring check: a test that only asserts `og:title`
    appears somewhere in the text passes on an empty tag, which is exactly the
    bug this file exists to catch — an unfurl with no title.
    """
    m = re.search(
        rf'<meta (?:property|name)="{re.escape(attr)}:{re.escape(value)}" content="([^"]*)"',
        page,
    )
    return m.group(1) if m else None


def _og(page: str, name: str) -> str | None:
    return _meta(page, "og", name)


def _json_ld(page: str) -> dict:
    m = re.search(
        r'<script type="application/ld\+json">(.*?)</script>', page, re.DOTALL
    )
    assert m, "the viewer emitted no JSON-LD block"
    return json.loads(m.group(1))


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


def test_viewer_links_the_pdf_endpoint_not_the_nonexistent_download_route(
    client: TestClient, db_session
):
    """The Download PDF button used to point at /api/v1/verify/{id}/download, a
    404, because it read cred.pdf_url — a column nothing has ever populated.
    It now always links the on-demand PDF endpoint, since every DB-backed
    credential can be rendered from its template at any time.
    """
    _issue_credential(db_session, "CF-2026-NOPDF001", slug="no-pdf-org")

    res = client.get("/verify/CF-2026-NOPDF001")

    assert res.status_code == 200
    assert "/download" not in res.text
    assert "Download PDF" in res.text
    assert 'href="https://api.certforge.intelliforge.tech/credentials/CF-2026-NOPDF001/pdf"' in res.text


def test_viewer_ignores_the_unused_pdf_url_column(
    client: TestClient, db_session
):
    """pdf_url is a legacy column nothing writes to; the viewer must not trust
    it even when a row happens to have one set — the link is always the
    computed PDF endpoint.
    """
    _issue_credential(
        db_session,
        "CF-2026-HASPDF01",
        slug="has-pdf-org",
        pdf_url="https://cdn.example.com/certs/haspdf01.pdf",
    )

    res = client.get("/verify/CF-2026-HASPDF01")

    assert res.status_code == 200
    assert "cdn.example.com" not in res.text
    assert 'href="https://api.certforge.intelliforge.tech/credentials/CF-2026-HASPDF01/pdf"' in res.text
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


def _org_branded(db_session, public_id: str, slug: str, **org_kwargs) -> None:
    """An org with branding set, plus one credential issued by it."""
    org_id = uuid.uuid4()
    db_session.add(
        Organization(id=org_id, name="Acme Academy", slug=slug, **org_kwargs)
    )
    db_session.add(
        Credential(
            public_id=public_id,
            org_id=org_id,
            recipient_name="Alice Nguyen",
            recipient_email="alice@example.com",
            title="Advanced Widgetry",
            metadata_={},
            hmac_signature=hmac_sign(public_id),
            status="issued",
        )
    )
    db_session.commit()


def test_viewer_carries_open_graph_tags_so_shares_unfurl(client, db_session):
    """A credential shared to LinkedIn or WhatsApp used to unfurl as a bare URL.

    The CertForge viewer carried none of the metadata the legacy viewers do, so
    a crawler found no title, description or image.
    """
    _issue_credential(db_session, "CF-2026-OGTAGS01", slug="viewer-og-tags-org")

    body = client.get("/verify/CF-2026-OGTAGS01").text

    assert _og(body, "title"), "og:title missing or empty"
    assert "Alice" in _og(body, "title")
    assert "Advanced Widgetry" in _og(body, "title")

    assert _og(body, "description"), "og:description missing or empty"
    assert "Advanced Widgetry" in _og(body, "description")

    assert _og(body, "type")
    assert _og(body, "url") == f"{CERTFORGE_WEB_URL}/verify/CF-2026-OGTAGS01"
    assert _og(body, "image"), "og:image missing or empty"

    assert _meta(body, "twitter", "card"), "twitter:card missing or empty"
    assert _meta(body, "twitter", "title")

    description = re.search(r'<meta name="description" content="([^"]+)"', body)
    assert description, "no <meta name=description>"
    assert "Alice" in description.group(1)


def test_og_image_is_a_fetchable_url_not_a_data_uri(client, db_session):
    """Crawlers fetch og:image over HTTP, so a data: URI is invisible to them.

    With no org logo the tag points at the credential's QR PNG endpoint, and
    that endpoint has to actually serve an image: an og:image naming a URL
    nobody serves is the same broken-link failure as a badge issuer.id that
    404s.
    """
    _issue_credential(db_session, "CF-2026-OGIMAGE1", slug="viewer-og-image-org")

    image = _og(client.get("/verify/CF-2026-OGIMAGE1").text, "image")
    assert image == f"{CERTFORGE_API_URL}/credentials/CF-2026-OGIMAGE1/qr.png"

    png = client.get("/credentials/CF-2026-OGIMAGE1/qr.png")
    assert png.status_code == 200
    assert png.headers["content-type"] == "image/png"
    assert png.content.startswith(b"\x89PNG")


def test_qr_png_is_not_served_for_a_revoked_credential(client, db_session):
    """The og:image endpoint must not outlive the credential it depicts."""
    _issue_credential(
        db_session, "CF-2026-QRREVOK1", slug="viewer-qr-revoked-org", status="revoked"
    )

    assert client.get("/credentials/CF-2026-QRREVOK1/qr.png").status_code == 404


def test_viewer_emits_schema_org_json_ld(client, db_session):
    """The legacy viewers carry EducationalOccupationalCredential JSON-LD; the
    CertForge one carried nothing, so a search engine saw an unlabelled page."""
    _org_branded(db_session, "CF-2026-JSONLD01", "viewer-json-ld-org")

    doc = _json_ld(client.get("/verify/CF-2026-JSONLD01").text)

    assert doc["@type"] == "EducationalOccupationalCredential"
    assert doc["identifier"] == "CF-2026-JSONLD01"
    assert doc["url"] == f"{CERTFORGE_WEB_URL}/verify/CF-2026-JSONLD01"
    assert doc["recognizedBy"]["name"] == "Acme Academy"
    assert doc["awardedTo"]["name"] == "Alice Nguyen"
    assert doc["name"] == "Advanced Widgetry"


def test_json_ld_cannot_be_broken_out_of_by_a_recipient_name(client, db_session):
    """html.escape does nothing inside a <script> block.

    A recipient named `</script><script>alert(1)</script>` would close the
    JSON-LD element and start executing, so the payload escapes < > and & as
    \\uXXXX instead. `_json_ld_script` in index.py does not do this, which is
    why the CertForge one is a separate implementation.
    """
    _issue_credential(
        db_session,
        "CF-2026-LDBREAK1",
        slug="viewer-ld-break-org",
        name="</script><script>alert(1)</script>",
    )

    body = client.get("/verify/CF-2026-LDBREAK1").text

    assert "</script><script>alert(1)</script>" not in body
    # Still parses, and still carries the name as data.
    assert "alert(1)" in _json_ld(body)["awardedTo"]["name"]


def test_viewer_offers_a_linkedin_share_link(client, db_session):
    """Sharing is the point of the port: the legacy viewers have the button and
    the CertForge card had no share action at all."""
    _issue_credential(db_session, "CF-2026-SHARE001", slug="viewer-share-org")

    body = client.get("/verify/CF-2026-SHARE001").text

    assert "Share on LinkedIn" in body
    href = re.search(r'href="(https://www\.linkedin\.com/sharing[^"]*)"', body)
    assert href, "no LinkedIn share link"
    # The share URL must carry this credential's page, not the bare host.
    assert "CF-2026-SHARE001" in href.group(1)


def test_viewer_shows_the_verification_qr(client, db_session):
    _issue_credential(db_session, "CF-2026-QRCODE01", slug="viewer-qr-code-org")

    body = client.get("/verify/CF-2026-QRCODE01").text

    assert "data:image/png;base64," in body
    assert "Scan to Verify" in body


def test_viewer_renders_the_issuing_org_not_the_legacy_single_tenant_brand(
    client, db_session
):
    """CertForge is multi-tenant. Carrying the legacy CERT_* env branding across
    would print IntelliForge Learning on every customer's credential."""
    _org_branded(
        db_session,
        "CF-2026-BRANDED1",
        "viewer-branded-org",
        primary_color="#123456",
        accent_color="#abcdef",
        logo_url="https://cdn.example.com/acme.png",
        footer_text="Issued by Acme Academy",
    )

    body = client.get("/verify/CF-2026-BRANDED1").text

    assert "Acme Academy" in body
    assert CERT_BRAND_NAME not in body
    assert "#123456" in body
    assert "#abcdef" in body
    assert "https://cdn.example.com/acme.png" in body
    assert "Issued by Acme Academy" in body


def test_org_colors_cannot_inject_css(client, db_session):
    """Colours land inside a <style> block, where escaping is no defence, so a
    value is used only when it matches a colour; otherwise the default stands."""
    _org_branded(
        db_session,
        "CF-2026-CSSINJ01",
        "viewer-css-inject-org",
        primary_color="#fff;} body{background:url(https://evil.example/x)} .x{",
        accent_color="red",
    )

    body = client.get("/verify/CF-2026-CSSINJ01").text

    assert "evil.example" not in body
    assert "--cf-primary:#1e293b" in body
    assert "--cf-accent:red" in body


def test_a_javascript_logo_url_is_not_rendered(client, db_session):
    """org.logo_url is customer-supplied and becomes both an <img src> and the
    og:image, so it gets the same scheme check the PDF link gets."""
    _org_branded(
        db_session,
        "CF-2026-JSLOGO01",
        "viewer-js-logo-org",
        logo_url="javascript:alert(1)",
    )

    body = client.get("/verify/CF-2026-JSLOGO01").text

    assert "javascript:" not in body
    # Falls back to the QR endpoint rather than emitting an unusable og:image.
    assert _og(body, "image").endswith("/qr.png")


def test_the_page_does_not_say_verified_credential_twice(client, db_session):
    """The header carried an eyebrow line above the org name, and the caller
    filled it with the literal "Verified Credential" for any org that had a
    name — which is every real org. The badge two rows below says the same
    words, so the page printed them twice, stacked.

    Reported by a beta user against her own credential before any test caught
    it. Counted, not merely searched for: a substring assertion passes on both
    one occurrence and two, which is the whole failure.
    """
    _issue_credential(db_session, "CF-2026-DUPBADGE", slug="dup-badge-org")

    body = client.get("/verify/CF-2026-DUPBADGE").text
    card = body[body.index('class="card-header"') : body.index('class="card-body"')]

    assert card.lower().count("verified credential") == 1


def test_the_org_name_appears_once_in_the_header(client, db_session):
    """The same shape as the tagline bug, guarded separately: the header must
    not print the issuing organization's name more than once."""
    _issue_credential(db_session, "CF-2026-DUPNAME1", slug="dup-name-org")

    body = client.get("/verify/CF-2026-DUPNAME1").text
    card = body[body.index('class="card-header"') : body.index('class="card-body"')]

    assert card.count("Viewer Org") == 1


def test_the_issued_date_is_readable_not_an_iso_timestamp(client, db_session):
    """The viewer interpolated issued_at raw, so the page a QR code lands on
    showed `2026-09-03T08:13:00.145119+00:00` under ISSUED — microseconds and
    UTC offset included. The PDF has always formatted the same value.
    """
    cred = _issue_credential(db_session, "CF-2026-ISODATE1", slug="iso-date-org")

    body = client.get("/verify/CF-2026-ISODATE1").text
    # The value paired with the "Issued" label specifically. Scanning the whole
    # meta block would be a weaker test: the credential ID sits in it too and
    # legitimately contains the letter T.
    shown = re.search(
        r'<div class="meta-val">([^<]*)</div>\s*<div class="meta-lbl">Issued</div>',
        body,
    )
    assert shown, "no Issued row in the viewer"

    assert shown.group(1).strip() == cred.issued_at.strftime("%B %d, %Y")
    assert "T" not in shown.group(1)
    assert ":" not in shown.group(1)


def test_the_machine_readable_date_stays_iso_8601(client, db_session):
    """Formatting the visible date must not reach `dateCreated`. It is a
    schema.org field consumers parse; a prettified date there is not a date.
    """
    cred = _issue_credential(db_session, "CF-2026-ISOMACH1", slug="iso-machine-org")

    payload = _json_ld(client.get("/verify/CF-2026-ISOMACH1").text)

    assert payload["dateCreated"].startswith(cred.issued_at.strftime("%Y-%m-%d"))
    assert "T" in payload["dateCreated"]


def test_an_unparseable_issue_date_does_not_break_the_page():
    """A verification page that 500s over date formatting is worse than one
    showing an ugly string, so the helper falls back rather than raising."""
    from api.viewer_templates import format_issued_date

    assert format_issued_date("not a date") == "not a date"
    assert format_issued_date("") == ""
    assert format_issued_date(None) == ""
    assert format_issued_date("2026-09-03T08:13:00.145119+00:00") == "September 03, 2026"
    assert format_issued_date("2026-09-03T08:13:00Z") == "September 03, 2026"
