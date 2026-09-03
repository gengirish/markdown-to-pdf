"""Template artwork: the upload boundary, and the joins it creates.

A traced template is a customer's own certificate design with fields placed on
top of it. That introduces three things this codebase has never had — an
attacker-supplied binary, an object store, and a generated layout — and each
one joins to something that already works.

The upload tests are a boundary: everything a stranger can send arrives here.
The join tests are the ones that matter more, because each half of every pair
is independently correct and passes its own tests while the pair is broken.
"""

import io
import re
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from api.core.principal import hash_api_key
from api.models.api_key import ApiKey
from api.models.credential import Credential
from api.models.organization import Organization
from api.models.template import Template
from api.models.template_asset import TemplateAsset
from api.services import backgrounds
from api.services.templates import (
    BUILTIN_VARIABLES,
    DEFAULT_TRACED_CONFIG,
    build_html_from_config,
    normalise_config,
    normalise_traced_config,
    normalise_traced_field,
    validate_template_html,
)

def key_for(slug: str) -> str:
    """One API key per org. A key belongs to exactly one organization, so a
    shared literal collides on api_keys.key_hash the moment a test needs two."""
    return "cf_live_" + slug.replace("-", "_")


# ── fixtures ────────────────────────────────────────────────────────────────


class FakeStore:
    """An in-memory stand-in for R2. Records every call so a test can assert
    that a *rejected* upload never touched it — an upload that is refused but
    still writes the object is a leak that leaves no trace in the database."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.puts = 0
        self.fail_put = False

    def put(self, key, data, content_type):
        self.puts += 1
        if self.fail_put:
            from api.core.storage import StorageError

            raise StorageError("bucket unreachable")
        self.objects[key] = data

    def get(self, key):
        from api.core.storage import StorageError

        if key not in self.objects:
            raise StorageError("no such key")
        return self.objects[key]

    def delete(self, key):
        self.objects.pop(key, None)


@pytest.fixture
def store():
    fake = FakeStore()
    backgrounds.clear_cache()
    with (
        patch("api.routes.templates.put_object", fake.put),
        patch("api.routes.templates.storage_available", lambda: True),
        patch("api.core.storage.get_object", fake.get),
        patch("api.core.storage.delete_object", fake.delete),
        patch("api.core.storage.storage_available", lambda: True),
        patch("api.services.backgrounds.get_object", fake.get),
        patch("api.services.backgrounds.storage_available", lambda: True),
    ):
        yield fake
    backgrounds.clear_cache()


def an_org(db_session, slug: str) -> Organization:
    org = db_session.query(Organization).filter_by(slug=slug).first()
    if org is None:
        org = Organization(slug=slug, name=slug.title(), tier="community", monthly_quota=100)
        db_session.add(org)
        db_session.commit()
        db_session.add(
            ApiKey(org_id=org.id, key_hash=hash_api_key(key_for(slug)), label="k")
        )
        db_session.commit()
    return org


def auth(slug: str):
    return {"Authorization": f"Bearer {key_for(slug)}"}


def png_bytes(size=(600, 400), color=(240, 230, 210)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def jpeg_bytes(size=(600, 400)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (250, 245, 235)).save(buf, "JPEG", quality=85)
    return buf.getvalue()


def upload(client, slug, data, filename="design.png", mime="image/png"):
    return client.post(
        f"/api/v1/orgs/{slug}/template-assets",
        headers=auth(slug),
        files={"file": (filename, data, mime)},
    )


def pdf_page_count(pdf: bytes) -> int:
    # /Type /Pages is the page-tree node, not a page — the negative class is
    # what keeps this from counting it.
    return len(re.findall(rb"/Type\s*/Page[^s]", pdf))


# ── the upload boundary ─────────────────────────────────────────────────────


def test_a_real_image_is_stored_re_encoded(client: TestClient, db_session, store):
    an_org(db_session, "art-upload-org")

    res = upload(client, "art-upload-org", png_bytes())

    assert res.status_code == 201, res.text
    body = res.json()["data"]
    # A PNG went in; a JPEG is stored. Nothing a stranger sent us is what we
    # keep — that substitution is the security argument for the whole feature.
    assert body["mime"] == "image/jpeg"
    assert store.objects
    assert next(iter(store.objects.values())).startswith(b"\xff\xd8\xff")


#: Built lazily and keyed by name, never inlined into the parametrize list —
#: pytest puts the raw parameter value in the test id, and an 8 MB bytes
#: literal there makes the whole run unreadable and slow.
REJECTED_UPLOADS = {
    # Markup wearing an image's name. SVG can carry script, and accepting it
    # would break the claim that an uploaded image is inert.
    "svg": (lambda: b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>', "x.svg", 415),
    "text_renamed_jpg": (lambda: b"just some text, not an image" * 4, "x.jpg", 415),
    "empty": (lambda: b"", "x.png", 400),
    "over_8mb": (lambda: bytes.fromhex("ffd8ff") + bytes(8 * 1024 * 1024), "x.jpg", 413),
}


@pytest.mark.parametrize("name", sorted(REJECTED_UPLOADS))
def test_a_refused_upload_stores_nothing(client: TestClient, db_session, store, name):
    """Every rejection path, and in each one the object store must be untouched.

    A refusal that still wrote the object leaves bytes nobody can find through
    the API and nobody is accounted for in the org's allowance.
    """
    make_data, filename, status = REJECTED_UPLOADS[name]
    org = an_org(db_session, "art-reject-org")

    # Whether the decoder was ever reached. The magic-byte check exists to
    # refuse a non-image BEFORE Pillow opens it — an image decoder is a far
    # larger attack surface than a prefix comparison — and without this spy the
    # test passes either way, because Pillow also rejects the same files a
    # moment later with the same status.
    decoded = []
    real_open = Image.open

    with patch.object(
        Image, "open", lambda *a, **kw: (decoded.append(1), real_open(*a, **kw))[1]
    ):
        res = upload(client, "art-reject-org", make_data(), filename=filename)

    assert res.status_code == status, f"{name}: {res.text}"
    assert store.puts == 0
    assert db_session.query(TemplateAsset).filter_by(org_id=org.id).count() == 0
    if name in ("svg", "text_renamed_jpg", "over_8mb"):
        assert not decoded, f"{name} reached the image decoder"


def test_a_payload_appended_to_a_jpeg_does_not_survive(
    client: TestClient, db_session, store
):
    """The classic polyglot: a valid image with something else stapled on.

    Decoding and re-encoding is what drops it. Storing the upload verbatim would
    put an attacker-controlled trailer inside a PDF handed to third parties.
    """
    an_org(db_session, "art-polyglot-org")
    payload = b"<html><script>alert(1)</script></html>"

    res = upload(client, "art-polyglot-org", jpeg_bytes() + payload, "x.jpg", "image/jpeg")

    assert res.status_code == 201
    stored = next(iter(store.objects.values()))
    assert payload not in stored


def test_the_same_image_twice_is_one_asset(client: TestClient, db_session, store):
    """A double-clicked upload must not produce two rows. One asset per image is
    what makes "is this artwork still in use?" a decidable question."""
    org = an_org(db_session, "art-dedupe-org")
    data = png_bytes()

    first = upload(client, "art-dedupe-org", data)
    second = upload(client, "art-dedupe-org", data)

    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert db_session.query(TemplateAsset).filter_by(org_id=org.id).count() == 1
    assert store.puts == 1


def test_an_unreachable_bucket_leaves_no_row(client: TestClient, db_session, store):
    """A failed write must leave no row behind.

    The rollback is what guarantees this — the put happens inside the
    transaction, so raising rolls the insert back. (Writing the object first is
    intent, not the mechanism: this test passes with the two swapped, which is
    how the mechanism was identified.) What must never happen is a committed
    row naming an object that does not exist, because every render from it then
    fails later, elsewhere, for a reason nothing records.
    """
    org = an_org(db_session, "art-nobucket-org")
    store.fail_put = True

    res = upload(client, "art-nobucket-org", png_bytes())

    assert res.status_code == 502
    assert db_session.query(TemplateAsset).filter_by(org_id=org.id).count() == 0


def test_upload_is_refused_when_storage_is_not_configured(
    client: TestClient, db_session
):
    an_org(db_session, "art-nostorage-org")

    with patch("api.routes.templates.storage_available", lambda: False):
        res = upload(client, "art-nostorage-org", png_bytes())

    assert res.status_code == 503
    assert "storage" in res.json()["error"]["message"].lower()


def test_one_org_cannot_read_or_use_another_orgs_artwork(
    client: TestClient, db_session, store
):
    """404 rather than 403: a wrong-org id must not confirm the asset exists."""
    an_org(db_session, "art-owner-org")
    other = an_org(db_session, "art-thief-org")

    asset_id = upload(client, "art-owner-org", png_bytes()).json()["data"]["id"]
    thief = auth("art-thief-org")

    read = client.get(
        f"/api/v1/orgs/art-thief-org/template-assets/{asset_id}/image", headers=thief
    )
    assert read.status_code == 404

    bind = client.post(
        "/api/v1/orgs/art-thief-org/templates",
        headers=thief,
        json={
            "name": "Stolen",
            "config": DEFAULT_TRACED_CONFIG,
            "background_asset_id": asset_id,
        },
    )
    assert bind.status_code == 404
    assert db_session.query(Template).filter_by(org_id=other.id).count() == 0


def test_artwork_a_template_is_drawn_on_cannot_be_deleted(
    client: TestClient, db_session, store
):
    an_org(db_session, "art-inuse-org")
    asset_id = upload(client, "art-inuse-org", png_bytes()).json()["data"]["id"]
    client.post(
        "/api/v1/orgs/art-inuse-org/templates",
        headers=auth("art-inuse-org"),
        json={"name": "Traced", "config": DEFAULT_TRACED_CONFIG, "background_asset_id": asset_id},
    )

    res = client.delete(
        f"/api/v1/orgs/art-inuse-org/template-assets/{asset_id}",
        headers=auth("art-inuse-org"),
    )

    assert res.status_code == 409
    assert "template" in res.json()["error"]["message"].lower()


def test_the_asset_read_route_refuses_to_be_sniffed(
    client: TestClient, db_session, store
):
    """The bytes are ours, and the headers say so.

    This URL can be opened in a top-level tab on the API host. An explicit image
    content type plus nosniff is what stops a browser deciding it is HTML.
    """
    an_org(db_session, "art-headers-org")
    asset_id = upload(client, "art-headers-org", png_bytes()).json()["data"]["id"]

    res = client.get(
        f"/api/v1/orgs/art-headers-org/template-assets/{asset_id}/image",
        headers=auth("art-headers-org"),
    )

    assert res.status_code == 200
    assert res.headers["content-type"] == "image/jpeg"
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["cache-control"].startswith("private")


# ── the generator ───────────────────────────────────────────────────────────


def test_a_generated_traced_template_passes_the_validator():
    html = build_html_from_config(DEFAULT_TRACED_CONFIG, True)

    assert validate_template_html(html) == []
    assert 'url("{{background}}")' in html
    assert "@frame" in html


@pytest.mark.parametrize(
    "field",
    [
        {"variable": "name", "color": "red;} @import url(evil); .a{"},
        {"variable": "name", "align": '"><script>alert(1)</script>'},
        {"variable": 'qr" onerror="alert(1)'},
        {"variable": "name", "x_mm": float("nan"), "w_mm": float("inf")},
        {"variable": "name", "font_pt": ";background:url(http://evil)"},
        {"variable": "custom:cohort", "label": "<img src=x onerror=1>"},
    ],
)
def test_a_hostile_spec_cannot_escape_the_generated_css(field):
    """Every string in a traced spec is attacker-controlled the moment a
    customer uploads someone else's artwork and a model reads text off it.

    The generated HTML lands in a <style> block, where escaping does not help —
    only refusing the value does.
    """
    spec = {"kind": "traced", "fields": [field]}

    html = build_html_from_config(spec, True)

    assert validate_template_html(html) == []
    assert "@import" not in html
    assert "<script" not in html.lower()
    assert "onerror" not in html.lower()
    assert "http://evil" not in html
    assert "nan" not in html.lower()


def test_generated_html_is_validated_before_it_is_stored(
    client: TestClient, db_session, store
):
    """The write path validates what the generator produced, not only what a
    human typed.

    That was a safe omission while the generator was a fixed string with a few
    escaped fields. A traced spec carries customer-supplied colours, labels and
    coordinates, so the generator is now the code most likely to grow a bug
    that emits a URL — and a template that fetches one at render time is the
    hole core/pdf_renderer.py's link callback exists to close.

    The generator is stubbed here because a correct generator cannot exercise
    its own guard: with the real one, removing the check changes nothing
    observable, which is how this test came to exist.
    """
    an_org(db_session, "generated-validated-org")
    asset_id = upload(client, "generated-validated-org", png_bytes()).json()["data"]["id"]

    leaky = '<html><body><img src="http://evil.example/x.png">{{background}}</body></html>'
    with patch("api.routes.templates.build_html_from_config", lambda *a, **kw: leaky):
        res = client.post(
            "/api/v1/orgs/generated-validated-org/templates",
            headers=auth("generated-validated-org"),
            json={
                "name": "Leaky",
                "config": DEFAULT_TRACED_CONFIG,
                "background_asset_id": asset_id,
            },
        )

    assert res.status_code == 400
    assert "External reference" in res.json()["error"]["message"]
    assert db_session.query(Template).filter_by(name="Leaky").count() == 0


def test_an_unknown_variable_is_dropped_rather_than_bound():
    """The silent-blank failure, refused at the door.

    A field bound to `recipient_full_name` is not builtin, so it would become a
    custom CSV variable and render empty on every credential forever — and a
    blank space on a certificate looks like a design choice.
    """
    spec = {"kind": "traced", "fields": [{"variable": "recipient_full_name"}]}

    assert normalise_traced_config(spec)["fields"] == []


def test_a_centred_field_stays_centred_after_headroom():
    """Boxes get 15% width headroom so a long name does not overflow onto a
    second page. Adding it to the right only moves a centred field off centre,
    and the person who dragged it into place never touched it again."""
    spec = {
        "kind": "traced",
        "page_width_mm": 297.0,
        "page_height_mm": 210.0,
        "fields": [
            {
                "variable": "name",
                "x_mm": 40.0, "y_mm": 88.0, "w_mm": 217.0, "h_mm": 18.0,
                "font_pt": 30.0, "color": "#000000", "align": "center", "bold": False,
            }
        ],
    }

    html = build_html_from_config(spec, True)
    left, width = re.search(r"left: ([\d.]+)mm; top: [\d.]+mm; width: ([\d.]+)mm", html).groups()

    assert abs((float(left) + float(width) / 2) - 297.0 / 2) < 0.5


def test_a_guided_config_is_untouched_by_the_traced_branch():
    """Every template written before traced layouts existed must normalise
    exactly as it did. A config with no `kind` is guided, and silently routing
    one through the traced branch would rewrite its HTML on its next save."""
    before = normalise_config({"heading": "CERTIFICATE OF EXCELLENCE", "show_qr": False})

    assert before["layout"] == "participation"
    assert before["heading"] == "CERTIFICATE OF EXCELLENCE"
    assert before["show_qr"] is False
    assert "fields" not in before


def _renders_text(config: dict, name: str = "Ada Lovelace") -> bool:
    """Did the text actually make it into the PDF?

    Page count cannot answer this. When a frame is too short for its font,
    xhtml2pdf does not wrap, does not paginate and does not raise — it drops
    the field, and the document is still one page. The only reliable signal is
    that rendering WITH the text produces a different document from rendering
    without it; a dropped field makes the two identical.
    """
    from api.core.pdf_renderer import render_credential_pdf
    from api.services.templates import sample_variables

    html = build_html_from_config(config, False)

    def size(value: str) -> int:
        variables = sample_variables()
        variables.update(name=value, font_face="", display_font="Helvetica")
        return len(render_credential_pdf(html, variables))

    return size(name) > size("") + 40


def test_a_long_name_still_fits_on_one_page(store):
    """Frames clip, and text that does not fit is lost — either onto a second
    page or, worse, into nothing at all."""
    from api.core.pdf_renderer import render_credential_pdf
    from api.services.templates import sample_variables

    html = build_html_from_config(DEFAULT_TRACED_CONFIG, False)
    variables = sample_variables()
    variables["name"] = "Bartholomew Fitzgerald-Wintermute III"
    variables["font_face"] = ""
    variables["display_font"] = "Helvetica"

    assert pdf_page_count(render_credential_pdf(html, variables)) == 1
    # Page count alone passes while the name is missing entirely, which is how
    # this test used to give a clean bill of health to a blank certificate.
    assert _renders_text(DEFAULT_TRACED_CONFIG, "Bartholomew Fitzgerald-Wintermute III")


@pytest.mark.parametrize("font_pt", [8, 12, 20, 30, 48])
def test_a_box_too_small_for_its_font_never_empties_the_field(font_pt):
    """The worst failure this feature can produce, and the least visible one.

    Below roughly 0.5mm of box height per point, xhtml2pdf silently drops the
    text: no error, no second page, just blank paper where the recipient's name
    belongs. Nothing downstream notices — the canvas shows the box, the save
    succeeds, the PDF renders, and the certificate goes out nameless.

    So a box smaller than its font demands is grown, and if the page cannot
    spare the room the font shrinks instead. Asked-for-but-smaller is legible;
    absent is not.
    """
    config = {
        "kind": "traced",
        "page_width_mm": 297.0,
        "page_height_mm": 210.0,
        # Half the height this font needs — what a person gets by dragging a
        # corner in a bit too far.
        "fields": [
            {
                "variable": "name", "label": "n",
                "x_mm": 20.0, "y_mm": 20.0, "w_mm": 250.0,
                "h_mm": font_pt * 0.25,
                "font_pt": font_pt, "color": "#102a57",
                "align": "left", "bold": False,
            }
        ],
    }

    assert _renders_text(config), f"{font_pt}pt text vanished from its box"


def test_a_box_at_the_page_edge_shrinks_the_font_rather_than_the_text():
    """When the page cannot give the box the height its font needs."""
    field = normalise_traced_field(
        {"variable": "name", "font_pt": 30, "h_mm": 13, "w_mm": 200,
         "x_mm": 40, "y_mm": 205},
        297.0, 210.0,
    )

    assert field["h_mm"] <= 5.0
    assert field["font_pt"] < 30
    assert field["font_pt"] * 0.6 <= field["h_mm"] + 0.01


# ── the joins ───────────────────────────────────────────────────────────────


def test_every_builtin_variable_is_actually_produced(db_session):
    """JOIN 1 — the vocabulary and the builder.

    BUILTIN_VARIABLES says which names a template may use without a CSV column;
    build_render_variables is what supplies them. Each is correct alone. Add a
    name to the set and not to the builder and `_UNRESOLVED` blanks it: for
    `background` that means every certificate renders on a plain white page,
    and nothing raises anywhere.

    Asserted over the whole vocabulary rather than one key, so the next name
    added is covered on the day it appears.
    """
    from datetime import datetime, timezone

    from api.services.rendering import build_render_variables

    org = an_org(db_session, "join-vocab-org")
    cred = Credential(
        public_id="CF-2026-JOINVOC1",
        org_id=org.id,
        recipient_name="Ada",
        recipient_email="",
        title="Engines",
        metadata_={},
        hmac_signature="x",
        status="issued",
        issued_at=datetime.now(timezone.utc),
    )

    produced = set(build_render_variables(cred, org, None))

    missing = BUILTIN_VARIABLES - produced
    assert not missing, f"declared builtin but never produced: {sorted(missing)}"


def test_the_preview_builds_its_variables_the_same_way_issuance_does(db_session):
    """JOIN 1b — the preview and the render.

    A preview exists to predict the issued certificate, and it is the one
    surface where being subtly wrong is invisible: the author reads the PDF as
    the answer. This is JOIN 1 from the other side — sample_variables() is the
    second producer of the same vocabulary, so a name the builder supplies and
    the preview does not is a field that previews blank and issues filled, or
    the reverse.

    It was already broken. sample_variables() was a hand-written dict that
    omitted `font_face` and `display_font`, which the guided generator emits
    into every template it makes — so every guided preview dropped the display
    serif, `_UNRESOLVED` blanked the placeholders, and the PDF the author
    approved used a typeface no issued credential would ever use.

    Asserted over the whole produced vocabulary, not the two keys that were
    missing, so the next one added is covered the day it appears.
    """
    from datetime import datetime, timezone

    from api.services.rendering import build_render_variables
    from api.services.templates import sample_variables

    org = an_org(db_session, "join-preview-org")
    cred = Credential(
        public_id="CF-2026-JOINPRV1",
        org_id=org.id,
        recipient_name="Ada",
        recipient_email="",
        title="Engines",
        metadata_={},
        hmac_signature="x",
        status="issued",
        issued_at=datetime.now(timezone.utc),
    )

    issued = set(build_render_variables(cred, org, None))
    previewed = set(sample_variables(org))

    missing = issued - previewed
    assert not missing, f"issued with, but never previewed: {sorted(missing)}"

    # The bundled face specifically: it is the one whose absence renders as a
    # different-looking certificate rather than a missing field, which is why
    # it went unnoticed.
    assert sample_variables(org)["display_font"] == build_render_variables(
        cred, org, None
    )["display_font"]


def test_the_preview_previews_the_orgs_own_branding(db_session):
    """The route used to copy four branding keys onto the sample dict by hand.

    A copy list is a second place the org's fields are enumerated, so a field
    added to build_render_variables previews as the sample default while it
    issues as the org's — the author checks the colour and ships the wrong one.
    """
    from api.services.templates import sample_variables

    org = an_org(db_session, "join-brand-org")
    org.primary_color = "#112233"
    org.accent_color = "#445566"
    db_session.commit()

    variables = sample_variables(org)
    assert variables["primary_color"] == "#112233"
    assert variables["accent_color"] == "#445566"
    assert variables["issuer_name"] == org.name


def test_a_traced_preview_is_drawn_on_the_real_artwork(
    client: TestClient, db_session, store
):
    """JOIN — the preview route and the object store.

    A traced template raises exactly one question: do the fields land where the
    design has room for them. A preview rendered on a blank page answers a
    different question convincingly, and answers it with a 200.

    The comparison is against the same preview with no artwork, because a PDF
    that contains an image is not evidence on its own — the QR code is an image
    too.
    """
    an_org(db_session, "prev-traced")
    asset_id = upload(client, "prev-traced", png_bytes((1200, 850))).json()["data"]["id"]

    def preview(body):
        r = client.post(
            "/api/v1/orgs/prev-traced/templates/preview",
            headers=auth("prev-traced"),
            json=body,
        )
        assert r.status_code == 200, r.text
        assert r.content[:4] == b"%PDF"
        return r.content

    with_art = preview(
        {"config": DEFAULT_TRACED_CONFIG, "background_asset_id": asset_id}
    )
    without_art = preview({"config": DEFAULT_TRACED_CONFIG})

    assert store.objects, "the artwork was never read out of the store"
    assert len(with_art) > len(without_art), (
        "the preview with artwork is no larger than the one without — the "
        "background never reached the render"
    )


def _issue_one_traced_batch(client, db_session, store, slug, rows=1):
    """Upload artwork, bind a traced template, and run one batch through the
    worker. Returns (batch, recorded render variables, object-store reads)."""
    from api.core.worker import _process_batch_sync
    from api.models.credential import CredentialBatch

    org = an_org(db_session, slug)
    asset_id = upload(client, slug, png_bytes((1200, 850))).json()["data"]["id"]

    created = client.post(
        f"/api/v1/orgs/{slug}/templates",
        headers=auth(slug),
        json={
            "name": "Traced",
            "config": DEFAULT_TRACED_CONFIG,
            "background_asset_id": asset_id,
        },
    )
    assert created.status_code == 201, created.text

    csv = b"name,title,email\n" + b"".join(
        f"Person {i},Engines,\n".encode() for i in range(rows)
    )
    with patch("api.routes.studio.process_batch.defer_async", new=AsyncMock()):
        res = client.post(
            f"/api/v1/orgs/{slug}/credentials/bulk",
            headers=auth(slug),
            data={"template_id": created.json()["data"]["id"]},
            files={"file": ("p.csv", csv, "text/csv")},
        )
    assert res.status_code == 200, res.text

    batch = db_session.query(CredentialBatch).filter_by(org_id=org.id).first()

    # What the worker actually rendered with. Counting object-store reads is not
    # enough on its own: the batch resolves the artwork once up front, so a
    # worker that then renders every row without it still reads exactly once.
    rendered: list[dict] = []
    reads: list[str] = []
    real_render = None

    import api.core.worker as worker_mod

    real_render = worker_mod.render_credential_pdf

    def spy_render(html_source, variables):
        rendered.append(dict(variables))
        return real_render(html_source, variables)

    original_get = store.get
    backgrounds.clear_cache()
    with (
        patch.object(worker_mod, "render_credential_pdf", spy_render),
        patch(
            "api.services.backgrounds.get_object",
            lambda key: (reads.append(key), original_get(key))[1],
        ),
    ):
        _process_batch_sync(batch.id)

    db_session.expire_all()
    return batch, rendered, reads


def test_bulk_and_single_issue_render_the_same_background(
    client: TestClient, db_session, store
):
    """JOIN 2 — the two render paths.

    `template` reaches build_render_variables with a None default, so a caller
    that forgets it still works. Pass it in one path and not the other and a
    batch-issued credential carries its artwork while the *same credential*,
    fetched from the QR code printed on it, does not — or the reverse. Both
    halves pass their own tests.

    Asserted on both sides, because an earlier version of this test only looked
    at the single-issue PDF and stayed green while the worker rendered every
    credential on blank paper.
    """
    batch, rendered, _ = _issue_one_traced_batch(
        client, db_session, store, "join-render-org"
    )

    cred = db_session.query(Credential).filter_by(batch_id=batch.id).first()
    assert cred.status == "issued"

    # The worker's side.
    assert rendered, "the worker rendered nothing"
    for variables in rendered:
        assert variables.get("background", "").startswith("data:image/"), (
            "the bulk path rendered a traced credential with no artwork"
        )

    # The on-demand side — the one a scanned QR code reaches. A JPEG inside a
    # PDF is a DCTDecode stream.
    single = client.get(f"/credentials/{cred.public_id}/pdf")
    assert single.status_code == 200
    assert b"DCTDecode" in single.content


def test_a_batch_reads_the_artwork_once_even_with_a_cold_cache(
    client: TestClient, db_session, store
):
    """JOIN 3 — one image, one read, however many rows.

    The artwork is ~1 MB and every row of a batch renders the same template, so
    a per-credential fetch is N round trips for one picture. Two things prevent
    that: the worker hoists the resolve out of the loop, and services/
    backgrounds.py memoises by checksum.

    The memo is disabled here on purpose. With it on, this assertion passes
    whether or not the hoist exists, so it would not be testing the hoist at
    all — and the memo is the half that legitimately misses, on a cold worker
    or after an eviction.
    """
    import api.services.backgrounds as bg

    uncached = bg._fetch_data_uri.__wrapped__
    with patch.object(bg, "_fetch_data_uri", uncached):
        batch, rendered, reads = _issue_one_traced_batch(
            client, db_session, store, "join-cache-org", rows=4
        )

    assert (
        db_session.query(Credential).filter_by(batch_id=batch.id, status="issued").count()
        == 4
    )
    assert len(rendered) == 4
    for variables in rendered:
        assert variables.get("background", "").startswith("data:image/")
    assert len(reads) == 1, f"read the artwork {len(reads)} times for one batch"


def test_artwork_and_html_must_agree_that_there_is_artwork(
    client: TestClient, db_session, store
):
    """JOIN 4 — the binding and the markup.

    Two ways to disagree, both silent: an asset bound to a template whose HTML
    never draws it, and a traced config with no asset, which renders
    `background-image: url("")` on blank paper.
    """
    an_org(db_session, "join-binding-org")
    asset_id = upload(client, "join-binding-org", png_bytes()).json()["data"]["id"]

    bound_but_unused = client.post(
        "/api/v1/orgs/join-binding-org/templates",
        headers=auth("join-binding-org"),
        json={
            "name": "Unused",
            "html_source": "<html><body>{{name}}</body></html>",
            "background_asset_id": asset_id,
        },
    )
    assert bound_but_unused.status_code == 400
    assert "{{background}}" in bound_but_unused.json()["error"]["message"]

    traced_without_art = client.post(
        "/api/v1/orgs/join-binding-org/templates",
        headers=auth("join-binding-org"),
        json={"name": "Artless", "config": DEFAULT_TRACED_CONFIG},
    )
    assert traced_without_art.status_code == 400
    assert "upload" in traced_without_art.json()["error"]["message"].lower()


def test_a_missing_object_renders_without_artwork_rather_than_failing(
    client: TestClient, db_session, store
):
    """The credential is the thing that has to exist.

    If the object store is unreachable at render time, the certificate should
    come out without its background rather than not come out at all — a
    picture is not what makes a credential valid. The failure is logged, never
    swallowed silently into a blank success.
    """
    from api.core.pdf_renderer import render_credential_pdf
    from api.services.templates import sample_variables

    an_org(db_session, "join-missing-org")
    asset_id = upload(client, "join-missing-org", png_bytes()).json()["data"]["id"]
    asset = db_session.query(TemplateAsset).filter_by(id=uuid.UUID(asset_id)).first()
    store.objects.clear()
    backgrounds.clear_cache()

    template = Template(
        org_id=asset.org_id,
        name="Traced",
        html_source=build_html_from_config(DEFAULT_TRACED_CONFIG, True),
        config=normalise_traced_config(DEFAULT_TRACED_CONFIG),
        background_asset_id=asset.id,
        variables=[],
    )

    uri = backgrounds.background_data_uri(template)
    assert uri == ""

    variables = sample_variables()
    variables.update(font_face="", display_font="Helvetica", background=uri)
    assert pdf_page_count(render_credential_pdf(template.html_source, variables)) == 1


# ── the organization logo ───────────────────────────────────────────────────
#
# The defect these cover: the guided form's logo checkbox emitted
# <img src="{{logo_url}}">, build_render_variables filled it with the org's
# external logo_url, and _pdf_link_callback refuses every http(s) URI. So the
# logo could never render, for anyone, and nothing said so.
# See docs/TODOs/org-logo-never-renders-in-a-pdf.md.


def transparent_png_bytes(size=(300, 120)) -> bytes:
    """A logo shaped like a real one: a mark on a fully transparent ground."""
    buf = io.BytesIO()
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    for x in range(40, 260):
        for y in range(30, 90):
            image.putpixel((x, y), (14, 107, 88, 255))
    image.save(buf, "PNG")
    return buf.getvalue()


def upload_logo(client, slug, data, filename="logo.png", mime="image/png"):
    return client.post(
        f"/api/v1/orgs/{slug}/logo",
        headers=auth(slug),
        files={"file": (filename, data, mime)},
    )


def a_credential(db_session, org, public_id: str):
    cred = Credential(
        public_id=public_id,
        org_id=org.id,
        recipient_name="Ada Lovelace",
        recipient_email="ada@example.com",
        title="Analytical Engines",
        metadata_={},
        hmac_signature="x",
        status="issued",
    )
    db_session.add(cred)
    db_session.commit()
    return cred


def test_the_rendered_logo_url_is_a_data_uri_not_a_link(client, db_session, store):
    """The bug itself, stated directly.

    An http(s) URL here cannot render: the PDF renderer's link callback returns
    _BLOCKED for anything containing "://", by design, so the <img> resolved to
    nothing. Whatever build_render_variables puts in `logo_url` must be
    something the renderer can actually draw.
    """
    from api.services.rendering import build_render_variables

    org = an_org(db_session, "logo-datauri-org")
    org.logo_url = "https://cdn.example.com/acme.png"
    db_session.commit()

    upload_logo(client, "logo-datauri-org", transparent_png_bytes())
    db_session.refresh(org)

    cred = a_credential(db_session, org, "CF-2026-LOGODATA")
    variables = build_render_variables(cred, org)

    assert variables["logo_url"].startswith("data:image/")
    assert "://" not in variables["logo_url"]
    # The external URL is still on the org for the viewer to use; it just is
    # not what the renderer is handed.
    assert org.logo_url == "https://cdn.example.com/acme.png"


def test_an_org_without_an_uploaded_logo_renders_no_logo_rather_than_a_dead_link():
    """`logo_url` must not fall back to the external column. Returning it would
    put the exact <img src="https://..."> back that rendered as nothing."""
    from api.services.backgrounds import logo_data_uri

    class Org:
        slug = "no-upload"
        logo_asset_id = None
        logo_url = "https://cdn.example.com/acme.png"

    assert logo_data_uri(Org()) == ""


def test_the_logo_actually_reaches_the_pdf_bytes(client, db_session, store):
    """The guard the TODO asked for.

    A PDF that contains an image is not evidence it contains *this* image — the
    QR code is an image too, and a template renders one either way. So the same
    template is rendered twice, with the logo variable and without it, and the
    two documents must differ. Page count cannot detect this: both are one page.
    """
    from api.core.pdf_renderer import render_credential_pdf
    from api.services.rendering import build_render_variables

    org = an_org(db_session, "logo-inpdf-org")
    upload_logo(client, "logo-inpdf-org", transparent_png_bytes())
    db_session.refresh(org)

    cred = a_credential(db_session, org, "CF-2026-LOGOPDF1")

    html = build_html_from_config({"show_logo": True})
    assert "{{logo_url}}" in html, "the guided layout stopped emitting a logo slot"

    with_logo = dict(build_render_variables(cred, org))
    with_logo.update(font_face="", display_font="Helvetica", background="")
    without_logo = dict(with_logo, logo_url="")

    drawn = render_credential_pdf(html, with_logo)
    blank = render_credential_pdf(html, without_logo)

    assert pdf_page_count(drawn) == 1
    assert len(drawn) > len(blank), "the logo added nothing to the document"


def test_a_transparent_logo_is_not_flattened_onto_black(client, db_session, store):
    """The reason a logo cannot reuse the artwork encoder.

    `_reencode` calls convert("RGB"), which drops the alpha channel; a logo
    exported with a transparent ground then prints as a solid black rectangle
    on every certificate. That is worse than the bug being fixed — no logo is a
    disappointment, a black box is a ruined document.
    """
    an_org(db_session, "logo-alpha-org")

    res = upload_logo(client, "logo-alpha-org", transparent_png_bytes())
    assert res.status_code == 201
    body = res.json()["data"]

    assert body["mime"] == "image/png"

    asset = db_session.query(TemplateAsset).filter_by(id=uuid.UUID(body["id"])).first()
    image = Image.open(io.BytesIO(store.objects[asset.storage_key]))

    assert image.mode == "RGBA", "alpha did not survive the re-encode"
    # The corner was transparent in the upload and must still be.
    assert image.getpixel((0, 0))[3] == 0


def test_an_opaque_logo_is_stored_as_jpeg(client, db_session, store):
    """No alpha to keep, so take the smaller encoding."""
    an_org(db_session, "logo-opaque-org")

    body = upload_logo(
        client, "logo-opaque-org", jpeg_bytes(), "logo.jpg", "image/jpeg"
    ).json()["data"]

    assert body["mime"] == "image/jpeg"


def test_an_uploaded_logo_is_served_publicly(client, db_session, store):
    """The viewer, og:image and the Open Badges Profile all need a URL. The
    certificate embeds the same bytes as a data URI — one upload, two
    representations."""
    an_org(db_session, "logo-public-org")
    upload_logo(client, "logo-public-org", transparent_png_bytes())

    res = client.get("/orgs/logo-public-org/logo")

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("image/png")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert Image.open(io.BytesIO(res.content)).mode == "RGBA"


def test_the_public_logo_route_404s_without_an_upload(client, db_session, store):
    """A legacy external logo_url is somebody else's URL to serve, not ours."""
    org = an_org(db_session, "logo-none-org")
    org.logo_url = "https://cdn.example.com/acme.png"
    db_session.commit()

    assert client.get("/orgs/logo-none-org/logo").status_code == 404


def test_the_viewer_and_the_certificate_show_the_same_logo(client, db_session, store):
    """An org with both an upload and a legacy URL must not show one mark on
    the page and print a different one on the document."""
    from api.routes.verify import public_logo_url

    org = an_org(db_session, "logo-agree-org")
    org.logo_url = "https://cdn.example.com/old-mark.png"
    db_session.commit()
    upload_logo(client, "logo-agree-org", transparent_png_bytes())
    db_session.refresh(org)

    assert public_logo_url(org).endswith("/orgs/logo-agree-org/logo")
    assert "old-mark" not in public_logo_url(org)


def test_the_logo_asset_cannot_be_deleted_while_it_is_the_logo(
    client, db_session, store
):
    """The RESTRICT foreign key would refuse this anyway — as a 500 raised from
    inside the commit, which tells the caller nothing about what to do."""
    an_org(db_session, "logo-delete-org")
    asset_id = upload_logo(client, "logo-delete-org", transparent_png_bytes()).json()[
        "data"
    ]["id"]

    res = client.delete(
        f"/api/v1/orgs/logo-delete-org/template-assets/{asset_id}",
        headers=auth("logo-delete-org"),
    )

    assert res.status_code == 409
    assert "logo" in res.json()["error"]["message"].lower()


def test_removing_the_logo_keeps_the_image(client, db_session, store):
    """Clearing the pointer is reversible; deleting bytes a template may also be
    drawn on is a separate decision."""
    org = an_org(db_session, "logo-remove-org")
    asset_id = upload_logo(client, "logo-remove-org", transparent_png_bytes()).json()[
        "data"
    ]["id"]

    res = client.delete(
        "/api/v1/orgs/logo-remove-org/logo", headers=auth("logo-remove-org")
    )

    assert res.status_code == 200
    assert res.json()["data"]["removed"] is True
    db_session.refresh(org)
    assert org.logo_asset_id is None
    assert (
        db_session.query(TemplateAsset).filter_by(id=uuid.UUID(asset_id)).first()
        is not None
    )


def test_the_org_json_tells_the_dashboard_it_has_a_printable_logo(
    client, db_session, store
):
    """The join, asserted from the side that consumes it.

    The branding card decides between "Upload a logo" and "Replace" on
    `logo_asset_id`, and shows a warning about a link that cannot be printed
    when there is only `logo_url`. If the API stops emitting the field, both
    halves still work on their own: the upload succeeds, the certificate prints
    the logo, and the dashboard shows "Upload a logo" forever with no way to see
    that anything is there. That is the failure this repository keeps producing.
    """
    an_org(db_session, "logo-json-org")

    before = client.get(
        "/api/v1/orgs/logo-json-org", headers=auth("logo-json-org")
    ).json()["data"]
    assert "logo_asset_id" in before, "the dashboard reads a field the API omits"
    assert before["logo_asset_id"] is None

    upload_logo(client, "logo-json-org", transparent_png_bytes())

    after = client.get(
        "/api/v1/orgs/logo-json-org", headers=auth("logo-json-org")
    ).json()["data"]
    assert after["logo_asset_id"] is not None


def test_the_public_logo_route_is_not_shadowed_by_the_issuer_profile(
    client, db_session, store
):
    """`/orgs/{slug}` and `/orgs/{slug}/logo` are neighbours on the same public
    router. If the profile route ever grew a catch-all path parameter it would
    swallow this one, and the logo would start returning an HTML page that an
    <img> renders as nothing."""
    an_org(db_session, "logo-shadow-org")
    upload_logo(client, "logo-shadow-org", transparent_png_bytes())

    logo = client.get("/orgs/logo-shadow-org/logo")
    profile = client.get(
        "/orgs/logo-shadow-org", headers={"accept": "application/json"}
    )

    assert logo.headers["content-type"].startswith("image/")
    assert profile.headers["content-type"].startswith("application/ld+json")
    # The profile points at the logo route, so a badge consumer that
    # dereferences `image` gets the same bytes the certificate prints.
    assert profile.json()["image"].endswith("/orgs/logo-shadow-org/logo")
