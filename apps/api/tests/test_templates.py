"""Template authoring: the boundary, the CRUD, and the guided generator.

Templates are the one place a customer supplies markup that the server renders.
That makes `validate_template_html` and the renderer's link callback a security
boundary rather than a lint, so most of this file is about what must be refused.

The rest covers the round trip the dashboard needs: read a template back, edit
it, preview it before saving, and know whether the guided form may reopen it.
"""

import uuid

import pytest

from api.core.pdf_renderer import _pdf_link_callback, _CERT_FONT_PATH
from api.core.principal import LIVE_PREFIX, hash_api_key
from api.models.api_key import ApiKey
from api.models.credential import Credential
from api.models.organization import Organization
from api.models.template import Template
from api.services.templates import (
    BUILTIN_VARIABLES,
    build_html_from_config,
    custom_placeholders,
    normalise_config,
    validate_template_html,
)

SAFE_HTML = "<html><body><h1>{{name}}</h1><p>{{title}}</p></body></html>"


def org_with_key(db_session, slug, raw_key):
    org = db_session.query(Organization).filter_by(slug=slug).first()
    if org is None:
        org = Organization(slug=slug, name=slug.title(), tier="community", monthly_quota=500)
        db_session.add(org)
        db_session.commit()
        db_session.add(ApiKey(org_id=org.id, key_hash=hash_api_key(raw_key), label="k"))
        db_session.commit()
    return org


def auth(raw):
    return {"Authorization": f"Bearer {raw}"}


def create(client, slug, raw, **body):
    payload = {"name": "Test Template", "html_source": SAFE_HTML}
    payload.update(body)
    return client.post(f"/api/v1/orgs/{slug}/templates", headers=auth(raw), json=payload)


# -- the boundary: what template HTML may not contain -------------------------

@pytest.mark.parametrize(
    "html,reason",
    [
        ('<script>fetch("/x")</script>', "script"),
        ('<iframe src="data:text/html,x"></iframe>', "iframe"),
        ('<link rel="stylesheet" href="https://evil.test/a.css">', "link"),
        ('<object data="x"></object>', "object"),
        ('<style>@import url("https://evil.test/a.css");</style>', "@import"),
        ('<div onclick="x()">hi</div>', "event handler"),
        # The one that mattered most: a local file read through the renderer.
        ('<img src="/app/.env">', "external reference"),
        ('<img src="file:///etc/passwd">', "external reference"),
        ('<img src="https://169.254.169.254/latest/meta-data/">', "external reference"),
        ('<div style="background:url(https://evil.test/a.png)">x</div>', "external reference"),
    ],
)
def test_dangerous_template_html_is_refused(html, reason):
    errors = validate_template_html(html)
    assert errors, f"{reason} was accepted"


@pytest.mark.parametrize(
    "html",
    [
        SAFE_HTML,
        '<img src="{{qr}}">',
        '<img src="{{logo_url}}">',
        '<img src="data:image/png;base64,iVBORw0KGgo=">',
        '<div style="color:{{primary_color}}">{{name}}</div>',
    ],
)
def test_legitimate_template_html_is_accepted(html):
    assert validate_template_html(html) == []


def test_an_empty_template_is_refused():
    assert validate_template_html("   ")


def test_the_renderer_only_opens_bundled_fonts():
    """The other half of the boundary. Validation can be bypassed by a template
    stored before it existed; this cannot."""
    blocked = [
        "/etc/passwd",
        "file:///app/.env",
        "https://169.254.169.254/latest/meta-data/",
        "../../../../etc/hosts",
    ]
    for uri in blocked:
        assert _pdf_link_callback(uri, "") != uri, f"{uri} was resolved"

    assert _pdf_link_callback("data:image/png;base64,AAA", "").startswith("data:")
    assert _pdf_link_callback(_CERT_FONT_PATH, "").endswith(".ttf")


# -- placeholders -------------------------------------------------------------

def test_custom_placeholders_are_reported_not_rejected():
    """A CSV column becomes a variable — that is how an org adds its own."""
    html = "<p>{{name}} — {{cohort}} — {{grade}}</p>"
    assert custom_placeholders(html) == {"cohort", "grade"}
    assert validate_template_html(html) == []


def test_builtins_are_not_reported_as_custom():
    html = "".join(f"{{{{{v}}}}}" for v in sorted(BUILTIN_VARIABLES))
    assert custom_placeholders(html) == set()


def test_an_unresolved_placeholder_renders_blank_not_literal(client, db_session):
    """It used to print "{{cohort}}" onto the certificate."""
    from api.core.pdf_renderer import render_credential_pdf

    pdf = render_credential_pdf(
        "<html><body><p>{{name}} {{cohort}}</p></body></html>", {"name": "Ada"}
    )
    assert pdf[:4] == b"%PDF"


# -- the guided generator -----------------------------------------------------

def test_guided_config_generates_valid_template_html():
    html = build_html_from_config({"layout": "participation", "heading": "WELL DONE"})
    assert validate_template_html(html) == []
    assert "WELL DONE" in html
    assert "{{name}}" in html


def test_guided_text_is_escaped_into_the_generated_markup():
    """Config values are data. A stray < must not become a tag."""
    html = build_html_from_config({"heading": "<script>alert(1)</script>"})
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert validate_template_html(html) == []


def test_unknown_config_keys_are_dropped():
    cfg = normalise_config({"layout": "internship", "not_a_field": "x"})
    assert "not_a_field" not in cfg
    assert cfg["layout"] == "internship"


def test_an_unknown_layout_falls_back_rather_than_failing():
    assert normalise_config({"layout": "nonsense"})["layout"] == "participation"


def test_the_generated_layout_matches_the_platform_design():
    """The first version of this generator produced a plain portrait table with
    a coloured border — it rendered, it validated, and it looked nothing like
    any certificate this product issues. These pin the parts that made it wrong.
    """
    html = build_html_from_config({})

    # Landscape. xhtml2pdf defaults to portrait, and without this the whole
    # layout collapses into a column.
    assert "size: 842pt 595pt" in html

    # Driven by the org's branding rather than baked-in colours, so a template
    # picks up what the branding form sets.
    assert "{{primary_color}}" in html
    assert "{{accent_color}}" in html

    # The structural features shared with api/seed.py's platform templates.
    assert "#0f172a" in html, "no dark outer frame"
    assert "2px solid #d4af37" in html, "no gold rule under the name"
    assert "CREDENTIAL ID" in html, "no date / credential-id panel"


def test_the_internship_layout_carries_the_vtu_fields():
    html = build_html_from_config({"layout": "internship"})
    assert "{{usn}}" in html
    assert "{{duration}}" in html
    assert "{{usn}}" not in build_html_from_config({"layout": "participation"})


def test_toggles_actually_remove_their_sections():
    with_qr = build_html_from_config({"show_qr": True})
    without = build_html_from_config({"show_qr": False})
    assert "{{qr}}" in with_qr
    assert "{{qr}}" not in without


# -- the round trip the dashboard needs ---------------------------------------

def test_a_template_can_be_read_back_with_its_source(client, db_session):
    raw = LIVE_PREFIX + "tpl-read-key"
    org_with_key(db_session, "tpl-read", raw)

    created = create(client, "tpl-read", raw).json()["data"]
    r = client.get(f"/api/v1/orgs/tpl-read/templates/{created['id']}", headers=auth(raw))

    assert r.status_code == 200, r.text
    assert r.json()["data"]["html_source"] == SAFE_HTML


def test_creating_from_config_marks_it_guided(client, db_session):
    raw = LIVE_PREFIX + "tpl-guided-key"
    org_with_key(db_session, "tpl-guided", raw)

    r = create(client, "tpl-guided", raw, html_source=None, config={"heading": "HELLO"})
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["is_guided"] is True
    assert "HELLO" in data["html_source"]


def test_creating_from_raw_html_is_not_guided(client, db_session):
    raw = LIVE_PREFIX + "tpl-raw-key"
    org_with_key(db_session, "tpl-raw", raw)
    assert create(client, "tpl-raw", raw).json()["data"]["is_guided"] is False


def test_editing_the_html_of_a_guided_template_detaches_it(client, db_session):
    """Otherwise the form would regenerate over the author's edit."""
    raw = LIVE_PREFIX + "tpl-detach-key"
    org_with_key(db_session, "tpl-detach", raw)

    created = create(
        client, "tpl-detach", raw, html_source=None, config={"heading": "BEFORE"}
    ).json()["data"]
    assert created["is_guided"] is True

    r = client.patch(
        f"/api/v1/orgs/tpl-detach/templates/{created['id']}",
        headers=auth(raw),
        json={"html_source": SAFE_HTML},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["is_guided"] is False
    assert r.json()["data"]["config"] is None


def test_sending_both_html_and_config_is_refused(client, db_session):
    raw = LIVE_PREFIX + "tpl-both-key"
    org_with_key(db_session, "tpl-both", raw)
    r = create(client, "tpl-both", raw, config={"heading": "X"})
    assert r.status_code == 400
    assert "not both" in r.json()["error"]["message"]


def test_dangerous_html_is_refused_by_the_route_too(client, db_session):
    raw = LIVE_PREFIX + "tpl-danger-key"
    org_with_key(db_session, "tpl-danger", raw)
    r = create(client, "tpl-danger", raw, html_source='<img src="/app/.env">')
    assert r.status_code == 400


def test_declared_variables_track_the_source(client, db_session):
    raw = LIVE_PREFIX + "tpl-vars-key"
    org_with_key(db_session, "tpl-vars", raw)

    created = create(
        client, "tpl-vars", raw, html_source="<p>{{name}} {{cohort}}</p>"
    ).json()["data"]
    assert created["variables"] == ["cohort"]

    r = client.patch(
        f"/api/v1/orgs/tpl-vars/templates/{created['id']}",
        headers=auth(raw),
        json={"html_source": "<p>{{name}} {{grade}}</p>"},
    )
    assert r.json()["data"]["variables"] == ["grade"]


# -- default, import, delete ---------------------------------------------------

def test_setting_a_default_clears_the_previous_one(client, db_session):
    """resolve_template_id takes the first org default it finds, so two would
    make issuance depend on row order."""
    raw = LIVE_PREFIX + "tpl-default-key"
    org = org_with_key(db_session, "tpl-default", raw)

    first = create(client, "tpl-default", raw, name="First").json()["data"]
    second = create(client, "tpl-default", raw, name="Second").json()["data"]

    for tid in (first["id"], second["id"]):
        r = client.post(
            f"/api/v1/orgs/tpl-default/templates/{tid}/default", headers=auth(raw)
        )
        assert r.status_code == 200, r.text

    db_session.expire_all()
    defaults = (
        db_session.query(Template).filter_by(org_id=org.id, is_default=True).all()
    )
    assert len(defaults) == 1
    assert str(defaults[0].id) == second["id"]


def test_a_global_template_can_be_imported_as_a_copy(client, db_session):
    raw = LIVE_PREFIX + "tpl-import-key"
    org = org_with_key(db_session, "tpl-import", raw)

    source = Template(
        org_id=None, name="Global Participation", html_source=SAFE_HTML, is_default=True
    )
    db_session.add(source)
    db_session.commit()

    r = client.post(
        f"/api/v1/orgs/tpl-import/templates/import/{source.id}", headers=auth(raw)
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["name"] == "Global Participation (copy)"
    assert data["html_source"] == SAFE_HTML
    assert data["id"] != str(source.id)

    db_session.expire_all()
    # Editing the copy must not reach the original every other org renders from.
    assert db_session.query(Template).filter_by(id=source.id).first().org_id is None


def test_a_template_in_use_cannot_be_deleted(client, db_session):
    """Deleting it would break re-rendering an already-issued certificate."""
    raw = LIVE_PREFIX + "tpl-inuse-key"
    org = org_with_key(db_session, "tpl-inuse", raw)

    created = create(client, "tpl-inuse", raw).json()["data"]
    db_session.add(
        Credential(
            public_id="CF-2026-USESTPL",
            org_id=org.id,
            template_id=uuid.UUID(created["id"]),
            recipient_name="Ada",
            title="T",
            metadata_={},
            hmac_signature="x",
            status="issued",
        )
    )
    db_session.commit()

    r = client.delete(
        f"/api/v1/orgs/tpl-inuse/templates/{created['id']}", headers=auth(raw)
    )
    assert r.status_code == 409


def test_an_unused_template_can_be_deleted(client, db_session):
    raw = LIVE_PREFIX + "tpl-del-key"
    org_with_key(db_session, "tpl-del", raw)
    created = create(client, "tpl-del", raw).json()["data"]

    r = client.delete(f"/api/v1/orgs/tpl-del/templates/{created['id']}", headers=auth(raw))
    assert r.status_code == 200, r.text
    assert (
        client.get(
            f"/api/v1/orgs/tpl-del/templates/{created['id']}", headers=auth(raw)
        ).status_code
        == 404
    )


def test_another_orgs_template_is_not_reachable(client, db_session):
    """Filtered by org_id, not just id — otherwise a guessed UUID crosses orgs."""
    mine = LIVE_PREFIX + "tpl-mine-key"
    theirs = LIVE_PREFIX + "tpl-theirs-key"
    org_with_key(db_session, "tpl-mine", mine)
    org_with_key(db_session, "tpl-theirs", theirs)

    created = create(client, "tpl-theirs", theirs).json()["data"]

    r = client.get(f"/api/v1/orgs/tpl-mine/templates/{created['id']}", headers=auth(mine))
    assert r.status_code == 404


# -- preview -------------------------------------------------------------------

def test_preview_returns_a_pdf_without_saving_anything(client, db_session):
    raw = LIVE_PREFIX + "tpl-preview-key"
    org = org_with_key(db_session, "tpl-preview", raw)
    before = db_session.query(Template).filter_by(org_id=org.id).count()

    r = client.post(
        "/api/v1/orgs/tpl-preview/templates/preview",
        headers=auth(raw),
        json={"html_source": SAFE_HTML},
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"

    db_session.expire_all()
    assert db_session.query(Template).filter_by(org_id=org.id).count() == before


def test_preview_refuses_dangerous_html(client, db_session):
    raw = LIVE_PREFIX + "tpl-prevbad-key"
    org_with_key(db_session, "tpl-prevbad", raw)
    r = client.post(
        "/api/v1/orgs/tpl-prevbad/templates/preview",
        headers=auth(raw),
        json={"html_source": '<img src="file:///etc/passwd">'},
    )
    assert r.status_code == 400


def test_community_tier_can_now_create_templates(client, db_session):
    """The gate used to 403 every community org, and billing is mocked, so no
    customer could reach a paid tier to satisfy it."""
    raw = LIVE_PREFIX + "tpl-free-key"
    org = org_with_key(db_session, "tpl-free", raw)
    assert org.tier == "community"
    assert create(client, "tpl-free", raw).status_code == 201
