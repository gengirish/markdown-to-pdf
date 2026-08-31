"""Reading a certificate design: what happens when the model answers badly.

The model proposes a layout and a person corrects it on a canvas, so a wrong
answer is not a failure — it is the normal case the canvas exists for. What
must never happen is a wrong answer that *cannot be seen*: a field bound to a
name nothing supplies renders blank on every credential, and a blank space on a
certificate reads as a design choice rather than a fault.

Nothing here touches the network. Every test stubs the client, which means these
prove the handling and not the model.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.models.template import Template
from api.models.usage import UsageLedger
from api.services.templates import validate_template_html
from api.services.vision import CertificateLayout, _to_traced_config

# Sibling module, not a package import: tests/ has no __init__.py, and pytest's
# prepend import mode puts that directory on sys.path. Reused rather than
# duplicated because the `store` fixture's patch targets are the part most
# likely to drift if there were two copies.
from test_template_assets import (  # noqa: E402
    an_org,
    auth,
    png_bytes,
    store,  # noqa: F401 - fixture, used by argument name
    upload,
)


def a_layout(**overrides) -> dict:
    base = {
        "page_width_mm": 297.0,
        "page_height_mm": 210.0,
        "confidence": "high",
        "notes": "",
        "fields": [
            {
                "variable": "name",
                "label": "Awarded to",
                "x_mm": 40.0, "y_mm": 88.0, "w_mm": 217.0, "h_mm": 18.0,
                "font_pt": 30.0, "color": "#1a202c", "align": "center", "bold": False,
            },
            {
                "variable": "qr",
                "label": "Verify",
                "x_mm": 242.0, "y_mm": 158.0, "w_mm": 26.0, "h_mm": 26.0,
                "font_pt": 8.0, "color": "#000000", "align": "center", "bold": False,
            },
        ],
    }
    base.update(overrides)
    return base


class FakeResponse:
    def __init__(self, layout: dict, stop_reason: str = "end_turn", category=None):
        self.parsed_output = CertificateLayout.model_validate(layout)
        self.stop_reason = stop_reason
        self.stop_details = SimpleNamespace(category=category) if category else None


class RefusedResponse:
    """A refusal carries no layout. Reading one raises here, so a caller that
    reaches for the content before checking stop_reason fails loudly rather
    than failing later for an unrelated-looking reason."""

    stop_reason = "refusal"

    def __init__(self, category: str = "cyber"):
        self.stop_details = SimpleNamespace(category=category)

    @property
    def parsed_output(self):
        raise AssertionError("read the content of a refused response")


def stub_vision(response=None, raises=None):
    """Patch read_layout's transport, leaving its clamping and checks in place.

    Deliberately not a patch of read_layout itself: the parsing, the refusal
    check and the field re-validation are what these tests are about.
    """

    class FakeMessages:
        def parse(self, **kwargs):
            if raises is not None:
                raise raises
            return response

    class FakeClient:
        def with_options(self, **kwargs):
            return SimpleNamespace(messages=FakeMessages())

    return patch("anthropic.Anthropic", lambda **kwargs: FakeClient())


def from_image(client, slug, asset_id, name="Imported"):
    return client.post(
        f"/api/v1/orgs/{slug}/templates/from-image",
        headers=auth(slug),
        json={"asset_id": asset_id, "name": name},
    )


@pytest.fixture(autouse=True)
def vision_key():
    """A key has to look present, or every route here answers 503 first."""
    with (
        patch("api.services.vision.VISION_AVAILABLE", True),
        patch("api.services.vision.ANTHROPIC_API_KEY", "sk-ant-test"),
    ):
        yield


def setup(client, db_session, slug):
    an_org(db_session, slug)
    return upload(client, slug, png_bytes((1200, 850))).json()["data"]["id"]


# ── the happy path ──────────────────────────────────────────────────────────


def test_a_read_design_becomes_a_usable_template(client: TestClient, db_session, store):
    asset_id = setup(client, db_session, "vision-happy-org")

    with stub_vision(FakeResponse(a_layout())):
        res = from_image(client, "vision-happy-org", asset_id)

    assert res.status_code == 201, res.text
    body = res.json()["data"]
    assert body["background_asset_id"] == asset_id
    assert body["needs_review"] is False
    # The template it produced is a real one, not a draft: it renders and it
    # passes the same validator a hand-written template does.
    assert validate_template_html(body["html_source"]) == []
    assert "{{background}}" in body["html_source"]
    assert "{{name}}" in body["html_source"]


# ── a bad answer ────────────────────────────────────────────────────────────


def test_a_nonsense_layout_is_clamped_rather_than_refused(
    client: TestClient, db_session, store
):
    """Impossible coordinates are the model guessing badly, not an outage.

    Refusing would throw away the parts it got right and leave the person with
    nothing to correct. Everything here is clamped onto the page instead, which
    is exactly what the canvas then shows them.
    """
    # A SQUARE design on purpose. With A4-shaped artwork this test cannot tell
    # "derived the page from the image" from "fell back to the A4 default",
    # because the two answers are the same numbers.
    an_org(db_session, "vision-nonsense-org")
    asset_id = upload(
        client, "vision-nonsense-org", png_bytes((1000, 1000))
    ).json()["data"]["id"]
    layout = a_layout(
        page_width_mm=0.0,
        page_height_mm=0.0,
        fields=[
            {
                "variable": "name", "label": "n",
                "x_mm": -500.0, "y_mm": 9000.0, "w_mm": -3.0, "h_mm": 0.0,
                "font_pt": 900.0, "color": "not a colour", "align": "center",
                "bold": False,
            }
        ],
    )

    with stub_vision(FakeResponse(layout)):
        res = from_image(client, "vision-nonsense-org", asset_id)

    assert res.status_code == 201, res.text
    config = res.json()["data"]["config"]
    field = config["fields"][0]

    # Page size came from the artwork's own aspect ratio, because the image is
    # ground truth about its shape and the model's answer was not a page. The
    # square artwork is what makes this distinguishable from the A4 fallback.
    assert 100 <= config["page_width_mm"] <= 450
    assert 100 <= config["page_height_mm"] <= 450
    assert abs(config["page_width_mm"] - config["page_height_mm"]) < 1.0, (
        "page shape ignored the artwork and fell back to A4"
    )
    assert 0 <= field["x_mm"] <= config["page_width_mm"]
    assert 0 <= field["y_mm"] <= config["page_height_mm"]
    assert field["w_mm"] > 0 and field["h_mm"] > 0
    assert field["font_pt"] <= 96
    assert field["color"] == "#1a202c"
    assert validate_template_html(res.json()["data"]["html_source"]) == []


def test_low_confidence_is_reported_rather_than_hidden(
    client: TestClient, db_session, store
):
    """The model saying "I was guessing" has to reach the person.

    A low-confidence layout that looks the same as a confident one is how a
    recipient's name ends up printed over a signature.
    """
    asset_id = setup(client, db_session, "vision-unsure-org")
    layout = a_layout(confidence="low", notes="The image is a photograph and skewed.")

    with stub_vision(FakeResponse(layout)):
        res = from_image(client, "vision-unsure-org", asset_id)

    body = res.json()["data"]
    assert body["needs_review"] is True
    assert body["confidence"] == "low"
    assert "skewed" in body["notes"]


def test_an_empty_layout_still_needs_review(client: TestClient, db_session, store):
    asset_id = setup(client, db_session, "vision-empty-org")

    with stub_vision(FakeResponse(a_layout(fields=[]))):
        res = from_image(client, "vision-empty-org", asset_id)

    assert res.status_code == 201
    assert res.json()["data"]["needs_review"] is True


def test_a_duplicate_binding_is_dropped_and_reported():
    """Two boxes bound to {{name}} print the recipient twice, which reads as a
    rendering bug to whoever receives the certificate."""
    layout = CertificateLayout.model_validate(
        a_layout(
            fields=[
                a_layout()["fields"][0],
                {**a_layout()["fields"][0], "y_mm": 120.0},
            ]
        )
    )

    result = _to_traced_config(layout, 1.4)

    assert len(result["config"]["fields"]) == 1
    assert result["dropped_fields"] == ["name"]


def test_an_invented_variable_cannot_reach_a_template():
    """The failure the closed enum exists for.

    `recipient_full_name` is not builtin, so it would be treated as a CSV
    column and render blank on every credential forever — the one error a
    person cannot see on the canvas, because a blank box looks like an empty
    box.
    """
    layout = CertificateLayout.model_validate(a_layout())
    # Past the schema, as a model returning something new would arrive.
    layout.fields[0].variable = "recipient_full_name"

    result = _to_traced_config(layout, 1.4)

    assert [f["variable"] for f in result["config"]["fields"]] == ["qr"]
    assert result["dropped_fields"] == ["recipient_full_name"]


# ── failures of the call itself ─────────────────────────────────────────────


def test_a_refusal_is_reported_without_reading_the_content(
    client: TestClient, db_session, store
):
    """On a refusal there is no layout in the response. Reading it anyway
    raises something unrelated to what actually happened, which is why
    stop_reason is checked first."""
    asset_id = setup(client, db_session, "vision-refusal-org")

    with stub_vision(RefusedResponse()):
        res = from_image(client, "vision-refusal-org", asset_id, name="Refused")

    assert res.status_code == 422
    # Named uniquely: "Imported" is this file's default and other tests here
    # create one, so counting that would pass or fail on run order.
    assert db_session.query(Template).filter_by(name="Refused").count() == 0


def test_an_api_failure_writes_no_template(client: TestClient, db_session, store):
    import anthropic

    asset_id = setup(client, db_session, "vision-apifail-org")
    error = anthropic.APIStatusError(
        "rate limited",
        response=SimpleNamespace(status_code=429, headers={}, text="", request=None),
        body=None,
    )

    with stub_vision(raises=error):
        res = from_image(client, "vision-apifail-org", asset_id, name="Never")

    assert res.status_code == 502
    assert db_session.query(Template).filter_by(name="Never").count() == 0


def test_without_a_key_the_route_says_so_rather_than_failing_oddly(
    client: TestClient, db_session, store
):
    asset_id = setup(client, db_session, "vision-nokey-org")

    with patch("api.services.vision.VISION_AVAILABLE", False):
        res = from_image(client, "vision-nokey-org", asset_id)

    assert res.status_code == 503
    assert "key" in res.json()["error"]["message"].lower()


def test_a_missing_sdk_says_so_rather_than_blaming_the_image(
    client: TestClient, db_session, store
):
    """The Anthropic package is imported lazily so the API boots without it.

    Left to the generic handler, an ImportError becomes "the design could not
    be read" — which sends whoever is debugging it to look at the image instead
    of at the deployment. This is the one dependency failure that looks exactly
    like a content failure.
    """
    from api.services.vision import VisionError, _require_sdk

    asset_id = setup(client, db_session, "vision-nosdk-org")

    with patch("builtins.__import__", side_effect=ImportError("no anthropic")):
        with pytest.raises(VisionError) as raised:
            _require_sdk()

    assert raised.value.code == 503
    assert "not installed" in raised.value.message
    assert asset_id


def test_another_orgs_artwork_cannot_be_read(client: TestClient, db_session, store):
    an_org(db_session, "vision-owner-org")
    an_org(db_session, "vision-other-org")
    asset_id = upload(client, "vision-owner-org", png_bytes()).json()["data"]["id"]

    with stub_vision(FakeResponse(a_layout())):
        res = from_image(client, "vision-other-org", asset_id)

    assert res.status_code == 404


# ── the meter ───────────────────────────────────────────────────────────────


def test_design_reading_is_metered_per_org(client: TestClient, db_session, store):
    """Every call is a paid API request, billing is mocked, and the template
    tier gate was removed because nobody could reach a paid tier — so without
    this counter anyone who can create an org can run up an Anthropic bill."""
    org = an_org(db_session, "vision-meter-org")
    asset_id = upload(client, "vision-meter-org", png_bytes()).json()["data"]["id"]

    with (
        patch("api.routes.templates.VISION_IMPORTS_PER_MONTH", 2),
        stub_vision(FakeResponse(a_layout())),
    ):
        first = from_image(client, "vision-meter-org", asset_id, name="One")
        second = from_image(client, "vision-meter-org", asset_id, name="Two")
        third = from_image(client, "vision-meter-org", asset_id, name="Three")

    assert first.status_code == 201
    assert first.json()["data"]["imports_remaining"] == 1
    assert second.status_code == 201
    assert third.status_code == 429

    ledger = (
        db_session.query(UsageLedger)
        .filter_by(org_id=org.id, period=UsageLedger.current_period())
        .first()
    )
    assert ledger.vision_imports == 2
    assert db_session.query(Template).filter_by(name="Three").count() == 0


def test_a_failed_call_still_counts_against_the_meter(
    client: TestClient, db_session, store
):
    """Metered before the call, not after.

    A counter that only counts successes is one an error loop walks straight
    past — and a call that reached the model cost money whether or not its
    answer arrived.
    """
    import anthropic

    org = an_org(db_session, "vision-failmeter-org")
    asset_id = upload(client, "vision-failmeter-org", png_bytes()).json()["data"]["id"]
    error = anthropic.APIStatusError(
        "boom",
        response=SimpleNamespace(status_code=500, headers={}, text="", request=None),
        body=None,
    )

    with stub_vision(raises=error):
        assert from_image(client, "vision-failmeter-org", asset_id).status_code == 502

    ledger = (
        db_session.query(UsageLedger)
        .filter_by(org_id=org.id, period=UsageLedger.current_period())
        .first()
    )
    assert ledger.vision_imports == 1


def test_the_credential_quota_is_not_touched_by_a_design_reading(
    client: TestClient, db_session, store
):
    """Two meters, two units. Charging a design reading against a certificate
    allowance would make "quota exceeded" mean two different things."""
    org = an_org(db_session, "vision-quota-org")
    asset_id = upload(client, "vision-quota-org", png_bytes()).json()["data"]["id"]

    with stub_vision(FakeResponse(a_layout())):
        assert from_image(client, "vision-quota-org", asset_id).status_code == 201

    ledger = (
        db_session.query(UsageLedger)
        .filter_by(org_id=org.id, period=UsageLedger.current_period())
        .first()
    )
    assert ledger.credentials_issued == 0
    assert ledger.vision_imports == 1


def test_the_image_sent_to_the_model_is_smaller_than_the_one_stored():
    """Claude downscales anything over 1568px before it looks at it, so sending
    the stored 2480px image is paying for pixels that get thrown away."""
    import io

    from PIL import Image

    from api.services.vision import VISION_EDGE_PX, _prepare_image
    import base64

    buf = io.BytesIO()
    Image.new("RGB", (2480, 1754), (250, 245, 235)).save(buf, "JPEG")

    encoded, ratio = _prepare_image(buf.getvalue())
    sent = Image.open(io.BytesIO(base64.b64decode(encoded)))

    assert max(sent.size) <= VISION_EDGE_PX
    assert abs(ratio - 2480 / 1754) < 0.01
