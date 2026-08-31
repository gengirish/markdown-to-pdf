"""Reading a certificate design and proposing where its fields go.

An org uploads the certificate it already uses; this asks Claude where the
recipient's name, the title, the date and the QR code belong on it, and returns
a traced layout spec that services/templates.py can generate HTML from and the
dashboard canvas can edit.

**The model proposes, it does not decide.** Everything it returns is clamped by
`normalise_traced_config` and then corrected by a person dragging boxes. That is
why nonsense is clamped rather than rejected: a spec that is 20mm off is worth
more than an error message, because the next step was always going to be a human
looking at it.

The one thing that is not negotiable is the variable name. `variable` is a
closed enum here and re-checked after parsing, because an invented name like
`recipient_full_name` is not a builtin — it would become a custom CSV variable
and render blank on every credential, forever, with nothing raising. A field in
the wrong place is visible on screen; a field bound to nothing is not.

This is the only module that constructs an Anthropic client.
"""

from __future__ import annotations

import base64
import io
import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

from api.core.config import ANTHROPIC_API_KEY, VISION_AVAILABLE
from api.services.templates import KIND_TRACED, TRACED_VARIABLES

logger = logging.getLogger(__name__)

#: Claude downscales anything larger before it looks at it, so sending the
#: stored 2480px image is paying for pixels that get thrown away.
VISION_EDGE_PX = 1568

#: Adaptive thinking over an image can take most of a minute, and the SDK's
#: 10-minute default is far longer than anything in front of this will wait.
VISION_TIMEOUT_SEC = 90.0

MODEL = "claude-opus-5"


class VisionError(Exception):
    """Something went wrong that the caller must turn into a status code."""

    def __init__(self, message: str, code: int = 502):
        super().__init__(message)
        self.message = message
        self.code = code


def _require_sdk():
    """Import the Anthropic SDK, or say plainly that it is missing.

    Imported here rather than at module scope so the API boots without it — the
    rest of the template surface does not need a model. Without this the
    ImportError falls into the generic handler below and the caller is told the
    design could not be read, which sends whoever is debugging it looking at
    the image instead of at the deployment.
    """
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - the package is pinned
        raise VisionError(
            "Reading a design is unavailable: the Anthropic SDK is not installed.",
            code=503,
        ) from exc
    return anthropic


class LayoutField(BaseModel):
    variable: Literal[
        "name", "title", "date", "credential_id", "issuer_name", "qr",
        "logo_url", "footer_text",
    ]
    #: The literal text read off the design near this field ("Awarded to",
    #: "Date of issue"). Shown in the canvas so a person can tell which box is
    #: which without decoding variable names.
    label: str = Field("", max_length=80)
    x_mm: float
    y_mm: float
    w_mm: float
    h_mm: float
    font_pt: float
    #: "#rrggbb". Re-validated downstream — this lands inside a <style> block.
    color: str
    align: Literal["left", "center", "right"]
    bold: bool


class CertificateLayout(BaseModel):
    page_width_mm: float
    page_height_mm: float
    confidence: Literal["high", "medium", "low"]
    #: What the model was unsure about, shown to the person about to correct it.
    notes: str = Field("", max_length=500)
    fields: list[LayoutField]


PROMPT = """You are looking at a certificate design that an organization wants to
issue credentials with. Blank areas and ruled lines are where variable text goes.

Return where each field should be placed, in millimetres from the top-left of the
page, assuming the whole image is one page.

Place only the fields that this design has room for:
- name: the recipient's name, usually the largest text area, often above a rule
- title: what the certificate is for (the course, achievement or award)
- date: when it was issued
- credential_id: a short reference code; put it somewhere unobtrusive
- issuer_name: the issuing organization, ONLY if the design does not already
  print it — most designs do, and repeating it over the printed version is the
  most common way this goes wrong
- qr: a verification QR code, 20-30mm square, in a corner with clear space
- logo_url: the organization's logo, ONLY if there is an empty logo area
- footer_text: a small footer line, only if there is space for one

Rules:
- Never place a field over existing printed text or over a signature.
- A box should be as wide as the space allows, so a long name still fits.
- Match font size to the space: a name area 20mm tall suits roughly 30pt.
- Read colours off the design's own text so the fields look like they belong.
- If the design has no obvious place for a field, leave it out. Fewer, correct
  boxes are better than complete coverage.

Set confidence to "low" if the image is a photograph, is skewed, or you are
guessing at the layout. Say what you were unsure about in notes."""


def _prepare_image(raw: bytes) -> tuple[str, float]:
    """Downscale for the API call. Returns (base64, width/height)."""
    from PIL import Image

    image = Image.open(io.BytesIO(raw))
    ratio = image.width / image.height if image.height else 1.0
    image = image.convert("RGB")
    image.thumbnail((VISION_EDGE_PX, VISION_EDGE_PX), Image.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=80, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii"), ratio


def read_layout(image_bytes: bytes) -> dict[str, Any]:
    """Ask Claude where the fields go. Returns a traced config, plus review flags.

    Never raises for a bad *answer* — only for a failed call. A layout that is
    wrong is the canvas's problem, and the canvas can fix it; a layout that was
    never produced is this function's problem.
    """
    if not VISION_AVAILABLE:
        raise VisionError(
            "Reading a design is not available: no Anthropic API key is configured.",
            code=503,
        )

    anthropic = _require_sdk()

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    encoded, aspect_ratio = _prepare_image(image_bytes)

    try:
        response = client.with_options(
            timeout=VISION_TIMEOUT_SEC, max_retries=1
        ).messages.parse(
            model=MODEL,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            output_format=CertificateLayout,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": encoded,
                            },
                        },
                        {"type": "text", "text": PROMPT},
                    ],
                }
            ],
        )
    except anthropic.APITimeoutError as exc:
        raise VisionError("Reading the design timed out. Try again.", code=504) from exc
    except anthropic.APIStatusError as exc:
        logger.warning("Vision call failed with %s", exc.status_code)
        raise VisionError(
            "The design could not be read right now. Try again shortly.", code=502
        ) from exc
    except Exception as exc:  # noqa: BLE001 - the caller needs a status, not a traceback
        logger.exception("Vision call failed")
        raise VisionError("The design could not be read.", code=502) from exc

    # Checked before .content is touched: on a refusal there is no layout in
    # there, and reading it would raise something unrelated to what happened.
    if response.stop_reason == "refusal":
        category = getattr(response.stop_details, "category", None)
        logger.warning("Vision call refused (category=%s)", category)
        raise VisionError(
            "That image could not be processed. Place the fields manually instead.",
            code=422,
        )

    layout = response.parsed_output
    return _to_traced_config(layout, aspect_ratio)


def _to_traced_config(
    layout: CertificateLayout, aspect_ratio: float
) -> dict[str, Any]:
    """Turn a model answer into a traced config, clamping what is implausible."""
    seen: set[str] = set()
    fields: list[dict[str, Any]] = []
    dropped: list[str] = []

    for field in layout.fields:
        # The enum already refuses an invented name, and this says so again
        # against the list the generator actually reads. Two copies of one
        # vocabulary is exactly the drift this re-check exists to catch.
        if field.variable not in TRACED_VARIABLES:
            dropped.append(field.variable)
            continue
        if field.variable in seen:
            dropped.append(field.variable)
            continue
        seen.add(field.variable)
        fields.append(field.model_dump())

    config = {
        "kind": KIND_TRACED,
        "page_width_mm": layout.page_width_mm,
        "page_height_mm": layout.page_height_mm,
        # The artwork's own shape is ground truth; the model's page size is a
        # guess. normalise_traced_config prefers this whenever the guess is
        # outside the range a page can be.
        "aspect_ratio": aspect_ratio,
        "fields": fields,
    }

    return {
        "config": config,
        # A low-confidence layout is still worth creating — but saying so is the
        # difference between a person checking every box and a person trusting
        # a name printed in the wrong place.
        "needs_review": layout.confidence == "low" or not fields,
        "confidence": layout.confidence,
        "notes": layout.notes,
        "dropped_fields": dropped,
    }
