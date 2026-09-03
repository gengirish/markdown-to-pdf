"""Authoring certificate templates: validation, and the guided generator.

Two ways in, one stored artefact. A template is always `html_source` — that is
what `render_credential_pdf` consumes and the only thing issuance reads. The
guided form is a generator on top of it: a `config` dict that produces
`html_source`, kept on the row so the form can be reopened.

The moment someone hand-edits the HTML, `config` is dropped. Regenerating from a
stale config would silently discard their edit, and keeping both would mean two
descriptions of one certificate that quietly disagree — the failure this
codebase produces more than any other.

Template HTML is customer-supplied and goes straight into a PDF renderer, so
`validate_template_html` is a real boundary and not a lint. It rejects rather
than sanitises: silently stripping a tag leaves the author staring at a
certificate missing something they wrote, with nothing saying why.
"""

from __future__ import annotations

import re
from typing import Any

#: Variables issuance always supplies. Kept in step with
#: services/rendering.py's build_render_variables — a name here that it does not
#: produce renders blank, which is exactly the silent-empty-field problem.
BUILTIN_VARIABLES = frozenset({
    "name",
    "title",
    "date",
    "credential_id",
    "qr",
    "issuer_name",
    "logo_url",
    "primary_color",
    "accent_color",
    "footer_text",
    # The bundled display face. font_face is injected as raw CSS, display_font
    # is the family name to reference in a font-family declaration.
    "font_face",
    "display_font",
    # A traced template's artwork, as a data: URI. Listed here so
    # custom_placeholders() does not report it and tell the author it has to
    # come from their CSV. build_render_variables must produce it — a name in
    # this set that it does not supply renders blank, which for a background
    # means a plain white certificate and no error anywhere.
    "background",
})

MAX_HTML_BYTES = 256 * 1024

_PLACEHOLDER = re.compile(r"\{\{\s*([\w.-]+)\s*\}\}")

#: Tags with no place in a certificate and a real cost in a renderer that
#: resolves URLs. <link> and <style>'s @import can pull remote CSS; the rest
#: either execute or embed.
#:
#: <meta> is deliberately NOT here. Banning it rejects `<meta charset="utf-8">`,
#: which every well-formed document carries and which xhtml2pdf reads — so the
#: rule refused valid templates, including the ones this module generates, in
#: exchange for no security at all. http-equiv="refresh" is inert in a PDF.
_FORBIDDEN_TAGS = ("script", "iframe", "object", "embed", "link", "base", "form")

#: on* attributes. Inert in xhtml2pdf, but template HTML is also the thing a
#: future preview might render in a browser, and this is cheap to refuse now.
_EVENT_ATTR = re.compile(r"<[^>]*\son[a-z]+\s*=", re.IGNORECASE)

#: url(...) and src/href values. A template may only reference a data: URI or a
#: {{placeholder}} that resolves to one.
_URL_VALUE = re.compile(
    r"""(?:src|href)\s*=\s*["']([^"']*)["']|url\(\s*["']?([^"')]*)["']?\s*\)""",
    re.IGNORECASE,
)


def extract_placeholders(html: str) -> set[str]:
    return {match.group(1) for match in _PLACEHOLDER.finditer(html)}


def custom_placeholders(html: str) -> set[str]:
    """Placeholders that are not built in, so they must come from metadata.

    Not an error. A CSV column becomes a variable, which is how an org adds
    "cohort" or "grade". But a row without that key renders blank, so the API
    reports them back and the UI says where they have to come from.
    """
    return extract_placeholders(html) - BUILTIN_VARIABLES


def validate_template_html(html: str) -> list[str]:
    """Every reason this HTML may not be stored, or an empty list."""
    errors: list[str] = []

    if not html or not html.strip():
        errors.append("Template HTML is empty.")
        return errors

    if len(html.encode("utf-8")) > MAX_HTML_BYTES:
        errors.append(f"Template HTML exceeds {MAX_HTML_BYTES // 1024} KB.")

    lowered = html.lower()
    for tag in _FORBIDDEN_TAGS:
        if re.search(rf"<\s*{tag}\b", lowered):
            errors.append(
                f"<{tag}> is not allowed in a certificate template."
            )

    if _EVENT_ATTR.search(html):
        errors.append("Event handler attributes (onclick, onload, …) are not allowed.")

    if "@import" in lowered:
        errors.append("@import is not allowed — it would fetch a stylesheet at render time.")

    for match in _URL_VALUE.finditer(html):
        value = (match.group(1) or match.group(2) or "").strip()
        if not value:
            continue
        if value.startswith("data:"):
            continue
        # A placeholder is fine: {{qr}} and {{logo_url}} resolve to data URIs or
        # to a URL the org set on its own profile, neither of which the template
        # author controls at render time.
        if _PLACEHOLDER.fullmatch(value):
            continue
        errors.append(
            f"External reference {value!r} is not allowed. Images must be a data: URI "
            f"or a placeholder such as {{{{qr}}}} or {{{{logo_url}}}}."
        )

    return errors


# -- the guided generator -----------------------------------------------------

#: Base layouts the guided form offers. Body copy is deliberately short: this
#: generates xhtml2pdf-safe markup — tables and inline styles, no flex, no grid,
#: which is the only CSS subset the renderer supports.
LAYOUTS = ("participation", "internship", "appreciation")

DEFAULT_CONFIG: dict[str, Any] = {
    "layout": "participation",
    "heading": "CERTIFICATE OF PARTICIPATION",
    "body": "This is to certify that",
    "closing": "has successfully participated in",
    "signature_name": "",
    "signature_title": "",
    "show_qr": True,
    "show_logo": True,
    "show_footer": True,
}


#: Which generator a config drives. Absent means "guided", so every config
#: written before traced templates existed normalises byte-identically — that
#: is pinned by a test, because a silent change here would rewrite the HTML of
#: every guided template on its next save.
KIND_GUIDED = "guided"
KIND_TRACED = "traced"
KINDS = (KIND_GUIDED, KIND_TRACED)


def config_kind(config: dict[str, Any] | None) -> str:
    kind = (config or {}).get("kind", KIND_GUIDED)
    return kind if kind in KINDS else KIND_GUIDED


def normalise_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Fill in what the caller left out, and drop what we do not know.

    Unknown keys are discarded rather than stored: a config that carries fields
    the generator ignores looks like it is doing something and is not.

    Dispatches on `kind`. A traced config must NOT go through the guided branch
    below — it merges against a flat DEFAULT_CONFIG and drops everything else,
    so a traced spec would come out the other side as an empty guided form with
    no error raised anywhere.
    """
    if config_kind(config) == KIND_TRACED:
        return normalise_traced_config(config)

    merged = dict(DEFAULT_CONFIG)
    for key, value in (config or {}).items():
        if key in DEFAULT_CONFIG:
            merged[key] = value
    if merged["layout"] not in LAYOUTS:
        merged["layout"] = DEFAULT_CONFIG["layout"]
    return merged


# -- the traced generator (a template drawn on uploaded artwork) ---------------
#
# A traced template is the customer's own certificate design with fields placed
# on top of it. The design is an uploaded image that arrives at render time as
# {{background}}; the fields are @frame blocks, which is how xhtml2pdf does
# absolute positioning. Everything here is generated, so the output passes
# validate_template_html by construction — and is validated anyway, because the
# generator is the code most likely to grow a bug that emits a URL.

#: What a traced field may be bound to. A CLOSED set, deliberately: an open
#: string means a vision model returning "recipient_full_name" produces a field
#: that is not builtin, so it becomes a custom CSV variable and renders blank on
#: every credential forever with nothing raising. Anything else must declare
#: itself a `custom:` binding, which the UI reports as needing a CSV column.
TRACED_VARIABLES = (
    "name",
    "title",
    "date",
    "credential_id",
    "issuer_name",
    "qr",
    "logo_url",
    "footer_text",
)

#: Rendered as an <img> rather than as text.
TRACED_IMAGE_VARIABLES = ("qr", "logo_url")

MAX_TRACED_FIELDS = 12

#: Page dimensions outside this are not a page. A spec that says 0x0 or 5000mm
#: gets overridden by the artwork's own aspect ratio instead.
MIN_PAGE_MM = 100.0
MAX_PAGE_MM = 450.0

MIN_FONT_PT = 4.0
MAX_FONT_PT = 96.0

#: Millimetres of box height needed per point of font size.
#:
#: MEASURED, not guessed. Below roughly 0.5mm/pt xhtml2pdf does not wrap the
#: text, does not push it to a second page and does not raise — it drops the
#: field entirely, leaving blank paper where the recipient's name should be.
#: The threshold was swept from 8pt to 60pt and sat between 0.475 and 0.562;
#: 0.6 keeps margin across that whole range.
#:
#: This is the worst failure this feature can produce, because it is invisible
#: at every stage before the certificate is in someone's hands: the canvas
#: shows the box, the save succeeds, the PDF renders, and the name is missing.
MIN_HEIGHT_MM_PER_PT = 0.6

_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_CUSTOM_VAR = re.compile(r"^custom:([a-z0-9][a-z0-9_-]{0,39})$")

#: A4 landscape with the fields where a certificate usually puts them. This is
#: what an upload produces before anyone has dragged anything, and before the
#: vision model exists it is the only traced layout there is.
DEFAULT_TRACED_CONFIG: dict[str, Any] = {
    "kind": "traced",
    "page_width_mm": 297.0,
    "page_height_mm": 210.0,
    "fields": [
        {
            "variable": "name",
            "label": "Recipient",
            "x_mm": 40.0, "y_mm": 88.0, "w_mm": 217.0, "h_mm": 18.0,
            "font_pt": 30.0, "color": "#1a202c", "align": "center", "bold": False,
        },
        {
            "variable": "title",
            "label": "Achievement",
            "x_mm": 50.0, "y_mm": 112.0, "w_mm": 197.0, "h_mm": 12.0,
            "font_pt": 15.0, "color": "#2d3748", "align": "center", "bold": False,
        },
        {
            "variable": "date",
            "label": "Date",
            "x_mm": 40.0, "y_mm": 168.0, "w_mm": 70.0, "h_mm": 8.0,
            "font_pt": 10.0, "color": "#4a5568", "align": "left", "bold": False,
        },
        {
            "variable": "credential_id",
            "label": "Credential ID",
            "x_mm": 40.0, "y_mm": 178.0, "w_mm": 70.0, "h_mm": 6.0,
            "font_pt": 8.0, "color": "#718096", "align": "left", "bold": False,
        },
        {
            "variable": "qr",
            "label": "Verification QR",
            "x_mm": 242.0, "y_mm": 158.0, "w_mm": 26.0, "h_mm": 26.0,
            "font_pt": 8.0, "color": "#000000", "align": "center", "bold": False,
        },
    ],
}


def _finite(value: Any, fallback: float) -> float:
    """A float that is safe to interpolate into CSS.

    NaN and inf format as "nan"/"inf", which xhtml2pdf reads as a zero-sized
    frame — a field that silently does not render. Both are exactly what a
    hand-edited JSON body, or a vision model, can produce.
    """
    try:
        out = float(value)
    except (TypeError, ValueError):
        return fallback
    if out != out or out in (float("inf"), float("-inf")):
        return fallback
    return out


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalise_traced_field(
    field: Any, page_w: float, page_h: float
) -> "dict[str, Any] | None":
    """One field, clamped onto the page. None when it cannot be salvaged.

    Clamps rather than rejects, on purpose: the canvas exists so a person can
    correct a bad guess, and a template that refuses to save because one box is
    5mm off the edge helps nobody. What it will not do is accept an unknown
    variable name — that is the one error a human cannot see on screen, because
    a misbound field renders blank rather than wrong.
    """
    if not isinstance(field, dict):
        return None

    raw_var = str(field.get("variable", "")).strip()
    if raw_var in TRACED_VARIABLES or _CUSTOM_VAR.match(raw_var):
        variable = raw_var
    else:
        return None

    font_pt = _clamp(_finite(field.get("font_pt"), 12.0), MIN_FONT_PT, MAX_FONT_PT)

    w = _finite(field.get("w_mm"), 0.0)
    h = _finite(field.get("h_mm"), 0.0)
    # A zero or negative box is a negative-dimension frame, which xhtml2pdf
    # warns about and then does not draw. Size it from the font instead.
    if w <= 0:
        w = min(page_w, 80.0)
    if h <= 0:
        h = font_pt * MIN_HEIGHT_MM_PER_PT

    x = _clamp(_finite(field.get("x_mm"), 0.0), 0.0, max(0.0, page_w - 1))
    y = _clamp(_finite(field.get("y_mm"), 0.0), 0.0, max(0.0, page_h - 1))
    w = _clamp(w, 1.0, page_w - x)

    # Grown to whatever this font needs, THEN clamped to the page. A person
    # dragging a box smaller than its text gets a box that quietly grows back,
    # which is visible; the alternative is a field that renders as nothing.
    h = _clamp(max(h, font_pt * MIN_HEIGHT_MM_PER_PT), 1.0, page_h - y)

    # If the page cannot spare that height — a box near the bottom edge — the
    # font gives way instead. Between "smaller than asked for" and "absent",
    # smaller is the only one the recipient can still read.
    affordable_pt = h / MIN_HEIGHT_MM_PER_PT
    if font_pt > affordable_pt:
        font_pt = max(MIN_FONT_PT, affordable_pt)

    color = str(field.get("color", "")).strip()
    if not _COLOR.match(color):
        color = "#1a202c"

    align = str(field.get("align", "")).strip().lower()
    if align not in ("left", "center", "right"):
        align = "left"

    return {
        "variable": variable,
        "label": str(field.get("label", "") or variable)[:80],
        "x_mm": round(x, 2),
        "y_mm": round(y, 2),
        "w_mm": round(w, 2),
        "h_mm": round(h, 2),
        "font_pt": round(font_pt, 2),
        "color": color.lower(),
        "align": align,
        "bold": bool(field.get("bold", False)),
    }


def normalise_traced_config(config: "dict[str, Any] | None") -> dict[str, Any]:
    """Clamp a traced spec into something that can be rendered.

    `aspect_ratio`, when given, is the artwork's own width/height, and it wins
    over an implausible page size: the image is ground truth about its own
    shape, while a page size is a guess by whatever produced the spec.
    """
    cfg = config or {}

    page_w = _finite(cfg.get("page_width_mm"), DEFAULT_TRACED_CONFIG["page_width_mm"])
    page_h = _finite(cfg.get("page_height_mm"), DEFAULT_TRACED_CONFIG["page_height_mm"])
    if not (MIN_PAGE_MM <= page_w <= MAX_PAGE_MM and MIN_PAGE_MM <= page_h <= MAX_PAGE_MM):
        ratio = _finite(cfg.get("aspect_ratio"), 0.0)
        if ratio > 0:
            # The longer edge becomes A4's 297mm, so the page matches the art.
            page_w, page_h = (297.0, 297.0 / ratio) if ratio >= 1 else (297.0 * ratio, 297.0)
            page_w = _clamp(page_w, MIN_PAGE_MM, MAX_PAGE_MM)
            page_h = _clamp(page_h, MIN_PAGE_MM, MAX_PAGE_MM)
        else:
            page_w = DEFAULT_TRACED_CONFIG["page_width_mm"]
            page_h = DEFAULT_TRACED_CONFIG["page_height_mm"]

    raw_fields = cfg.get("fields")
    if not isinstance(raw_fields, list):
        raw_fields = DEFAULT_TRACED_CONFIG["fields"]

    fields: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_fields:
        field = normalise_traced_field(raw, page_w, page_h)
        if field is None:
            continue
        # One box per variable. Two {{name}} frames print the recipient twice,
        # which reads as a rendering bug to whoever receives the certificate.
        if field["variable"] in seen:
            continue
        seen.add(field["variable"])
        fields.append(field)
        if len(fields) >= MAX_TRACED_FIELDS:
            break

    return {
        "kind": KIND_TRACED,
        "page_width_mm": round(page_w, 2),
        "page_height_mm": round(page_h, 2),
        "fields": fields,
    }


def build_traced_html(config: dict[str, Any], has_background: bool) -> str:
    """Generate background + @frame HTML from a traced spec.

    @frame is xhtml2pdf's absolute positioning: each one names a
    `-pdf-frame-content` id and the matching element in the body is drawn
    there. Frames CLIP — a name wider than its box flows onto a second page —
    which is why every box gets width headroom before it is drawn.
    """
    cfg = normalise_traced_config(config)
    page_w, page_h = cfg["page_width_mm"], cfg["page_height_mm"]

    background_rule = ""
    if has_background:
        # Substituted in at render time and never stored here: at ~940 KB as a
        # data URI the artwork does not fit inside MAX_HTML_BYTES.
        background_rule = '  background-image: url("{{background}}");\n'

    frames: list[str] = []
    bodies: list[str] = []
    for index, field in enumerate(cfg["fields"]):
        # 15% headroom, because a long recipient name in a snug frame is the
        # single most common way a fixed-geometry layout breaks in the field —
        # and it breaks by pushing the text onto a blank second page.
        #
        # Which SIDE the headroom is added to follows the alignment, or the
        # headroom moves the text. A centred box grown only to the right is no
        # longer centred on the artwork it was placed against, and the person
        # who dragged it into place never touched it.
        x, y = field["x_mm"], field["y_mm"]
        extra = field["w_mm"] * 0.15
        if field["align"] == "center":
            x = max(0.0, x - extra / 2)
        elif field["align"] == "right":
            x = max(0.0, x - extra)
        width = min(field["w_mm"] + extra, page_w - x)
        height = min(field["h_mm"] * 1.15, page_h - y)
        frames.append(
            f'  @frame f{index} {{ -pdf-frame-content: c{index};'
            f' left: {round(x, 2)}mm; top: {y}mm;'
            f' width: {round(width, 2)}mm; height: {round(height, 2)}mm; }}'
        )

        variable = field["variable"]
        placeholder = "{{" + variable.replace("custom:", "") + "}}"

        if variable in TRACED_IMAGE_VARIABLES:
            # Width only: a QR is square and a logo should keep its own
            # proportions rather than be stretched to the box.
            px = max(1, round(width * 3.78))
            bodies.append(
                f'<div id="c{index}" style="text-align:{field["align"]};">'
                f'<img src="{placeholder}" width="{px}" /></div>'
            )
            continue

        weight = "font-weight:bold;" if field["bold"] else ""
        bodies.append(
            f'<div id="c{index}" style="font-size:{field["font_pt"]}pt;'
            f'color:{field["color"]};text-align:{field["align"]};{weight}'
            f'font-family:{TRACED_FONT_FAMILY};">{placeholder}</div>'
        )

    return TRACED_SHELL.format(
        page_width=page_w,
        page_height=page_h,
        background=background_rule,
        frames="\n".join(frames),
        body="\n".join(bodies),
    )


#: A traced template deliberately does NOT pull in the bundled display serif.
#:
#: The artwork carries the customer's typography; our brand face is the wrong
#: default on someone else's design. And the @font-face block that would load
#: it is the known Windows failure documented in CLAUDE.md — xhtml2pdf copies
#: the TTF to a temporary file reportlab cannot reopen, so every render raises
#: there while working in Docker. Dropping the block instead of keeping it makes
#: local rendering work, and it avoids the worse outcome: declaring
#: `font-family: GaramondPDF` with no @font-face, which renders Helvetica
#: silently while the template claims otherwise.
#:
#: A per-field font from a small allowlist is the honest way to offer a choice
#: here later.
TRACED_FONT_FAMILY = "Helvetica, Arial, sans-serif"

#: Braces are doubled where they must survive .format() into CSS.
TRACED_SHELL = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
@page {{
  size: {page_width}mm {page_height}mm;
  margin: 0;
{background}{frames}
}}
body {{ font-family: Helvetica, Arial, sans-serif; margin: 0; padding: 0; }}
div {{ margin: 0; padding: 0; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def _esc(value: Any) -> str:
    """Escape config text for the generated markup.

    The author is trusted to the extent that they could write raw HTML anyway —
    but their input here is *data*, and treating it as markup would let a stray
    `<` silently break the layout.
    """
    import html as html_mod

    return html_mod.escape(str(value or ""))


def build_html_from_config(
    config: dict[str, Any], has_background: bool = False
) -> str:
    """Generate template HTML from a config — guided settings or a traced spec.

    `has_background` is whether the template has artwork behind it, NOT which
    artwork. The asset id lives on Template.background_asset_id and nowhere
    else: keeping it here as well would be two records of one fact that can
    disagree, which is what the module docstring above is about.

    The guided generator, from here down:

    Ported from the legacy participation certificate
    (api/certificate_templates.py CERTIFICATE_PARTICIPATION_HTML) rather than
    approximated a third time. Two earlier attempts invented a layout — a plain
    portrait box, then a landscape one missing every distinguishing feature —
    and neither looked like the certificate this product is known for.

    What the legacy design does that a generic table does not:

      - a navy header band carrying the issuer in gold small caps, the brand in
        a large display serif, and the certificate kind inside a gold-bordered
        pill
      - a green "Verified & Authentic" badge beneath it
      - the recipient in 34pt display serif over a gold rule
      - a two-column date / credential-ID panel under 6pt labels
      - a signature rule, the QR block, and a footer band

    The display serif arrives through {{font_face}} and {{display_font}} — the
    bundled EB Garamond, the same face legacy uses. Without them this renders in
    Helvetica and stops looking like the same product.

    Nested tables with inline styles because that is xhtml2pdf's whole CSS
    subset, and `@page size` is what makes it landscape.
    """
    if config_kind(config) == KIND_TRACED:
        return build_traced_html(config, has_background)

    cfg = normalise_config(config)

    logo = (
        '<tr><td align="center" style="text-align:center;padding-bottom:8pt;">'
        '<img src="{{logo_url}}" height="30" /></td></tr>'
        if cfg["show_logo"]
        else ""
    )

    verified = (
        '<table width="100%" cellspacing="0" cellpadding="0">'
        '<tr><td align="center" style="text-align:center;padding-bottom:18pt;">'
        '<table align="center" cellspacing="0" cellpadding="0" style="border:1px solid #68d391;">'
        '<tr><td align="center" style="padding:4pt 14pt;font-size:8pt;color:#276749;'
        'font-weight:bold;background-color:#f0fff4;text-align:center;">'
        "&#10003; &nbsp; Verified &amp; Authentic"
        "</td></tr></table></td></tr></table>"
    )

    signature = ""
    if cfg["signature_name"]:
        signature = (
            '<table width="100%" cellspacing="0" cellpadding="0">'
            '<tr><td align="center" style="text-align:center;padding-top:6pt;">'
            '<table align="center" cellspacing="0" cellpadding="0" width="230">'
            '<tr><td align="center" style="text-align:center;font-size:17pt;'
            'color:#1a202c;font-family:{{display_font}};padding-bottom:2pt;">'
            + _esc(cfg["signature_name"])
            + "</td></tr>"
            '<tr><td style="border-top:1px solid #cbd5e0;font-size:1pt;">&nbsp;</td></tr>'
            '<tr><td align="center" style="text-align:center;font-size:7pt;'
            'letter-spacing:1pt;color:#a0aec0;padding-top:4pt;">'
            + _esc(cfg["signature_title"]).upper()
            + "</td></tr></table></td></tr></table>"
        )

    qr = (
        '<table width="100%" cellspacing="0" cellpadding="0">'
        '<tr><td align="center" style="text-align:center;">'
        '<table align="center" cellspacing="0" cellpadding="0"><tr>'
        '<td style="padding-right:12pt;vertical-align:middle;">'
        '<img src="{{qr}}" width="70" height="70" /></td>'
        '<td style="vertical-align:middle;text-align:left;">'
        '<table cellspacing="0" cellpadding="0"><tr><td style="font-size:9pt;'
        'font-weight:bold;color:#2d3748;padding-bottom:2pt;">Scan to Verify</td></tr></table>'
        '<table cellspacing="0" cellpadding="0"><tr><td style="font-size:7pt;'
        'color:#a0aec0;line-height:1.5;">This QR code links to this certificate&#39;s'
        "<br/>permanent verification page.</td></tr></table>"
        "</td></tr></table></td></tr></table>"
        if cfg["show_qr"]
        else ""
    )

    footer = (
        '<table width="100%" cellspacing="0" cellpadding="0" '
        'style="background-color:#f8fafc;border-top:1px solid #edf2f7;">'
        '<tr><td align="center" style="padding:10pt 40pt;text-align:center;'
        'font-size:7pt;color:#a0aec0;">{{footer_text}}</td></tr></table>'
        if cfg["show_footer"]
        else ""
    )

    detail = ""
    if cfg["layout"] == "internship":
        detail = (
            '<table width="100%" cellspacing="0" cellpadding="0">'
            '<tr><td align="center" style="text-align:center;font-size:10pt;'
            'color:#4a5568;padding-bottom:14pt;">'
            "USN {{usn}} &nbsp;&middot;&nbsp; {{duration}}</td></tr></table>"
        )

    return TEMPLATE_SHELL.format(
        font_face="{{font_face}}",
        primary="{{primary_color}}",
        accent="{{accent_color}}",
        issuer="{{issuer_name}}",
        display="{{display_font}}",
        name="{{name}}",
        title="{{title}}",
        date="{{date}}",
        credential_id="{{credential_id}}",
        logo=logo,
        heading=_esc(cfg["heading"]),
        verified=verified,
        awarded=_esc(cfg["body"]).upper(),
        closing=_esc(cfg["closing"]),
        detail=detail,
        signature=signature,
        qr=qr,
        footer=footer,
    )


#: The layout itself, kept out of the function so the markup reads as markup.
#: Braces are doubled where they must survive .format() into CSS.
#:
#: The issuing organization's name appears in exactly ONE row. There used to be
#: a small letterspaced eyebrow above the display line carrying the same value,
#: so every guided certificate printed the company name twice, stacked. A beta
#: user reported it on a certificate she issued to herself; no test caught it,
#: because the assertions all ask whether a placeholder is present and it was —
#: twice. Note that this string is .format()ed, so a comment written *inside*
#: the markup cannot mention a field name without reintroducing the bug.
TEMPLATE_SHELL = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
{font_face}
@page {{ size: 842pt 595pt; margin: 0; }}
body {{ font-family: Helvetica, Arial, sans-serif; color: #2d3748; margin: 0; padding: 0; }}
table {{ border-collapse: collapse; }}
td {{ padding: 0; }}
</style>
</head>
<body>

<table width="100%" height="100%" style="background-color: #0f0f23;">
<tr><td style="padding: 24pt 32pt;">

<table width="100%" style="background-color: #ffffff;">
<tr><td>

    <table width="100%" style="background-color: {primary};">
    <tr><td style="padding: 30pt 40pt 26pt;">
        <table width="100%" cellspacing="0" cellpadding="0">
            {logo}
            <tr><td align="center" style="font-size: 25pt; font-weight: bold; color: #ffffff; padding: 6pt 0 12pt; text-align: center; font-family: {display};">
                {issuer}
            </td></tr>
            <tr><td align="center" style="text-align: center; padding: 0;">
                <table align="center" cellspacing="0" cellpadding="0" style="border: 2px solid {accent};">
                <tr><td align="center" style="padding: 6pt 30pt; font-size: 9pt; letter-spacing: 3pt; color: {accent}; font-weight: bold; text-align: center;">
                    {heading}
                </td></tr>
                </table>
            </td></tr>
        </table>
    </td></tr>
    </table>

    <table width="100%">
    <tr><td style="padding: 28pt 50pt 20pt;">

        {verified}

        <table width="100%" cellspacing="0" cellpadding="0">
            <tr><td align="center" style="text-align: center; font-size: 8pt; letter-spacing: 3pt; color: #a0aec0; padding-bottom: 6pt;">
                {awarded}
            </td></tr>
            <tr><td align="center" style="text-align: center; font-size: 34pt; font-weight: bold; color: #1a202c; padding: 4pt 0 2pt; font-family: {display};">
                {name}
            </td></tr>
        </table>

        <table width="60%" align="center" cellspacing="0" cellpadding="0"><tr>
            <td style="border-top: 2px solid #d4af37; font-size: 1pt;">&nbsp;</td>
        </tr></table>

        <table width="100%" cellspacing="0" cellpadding="0">
            <tr><td align="center" style="text-align: center; font-size: 9pt; color: #718096; padding-top: 12pt;">
                {closing}
            </td></tr>
            <tr><td align="center" style="text-align: center; font-size: 16pt; font-weight: bold; color: #553c9a; padding: 4pt 0 20pt; font-family: {display};">
                {title}
            </td></tr>
        </table>

        {detail}

        <table width="85%" align="center" cellspacing="0" cellpadding="0" style="border-top: 1px solid #edf2f7; border-bottom: 1px solid #edf2f7;">
            <tr>
                <td width="50%" align="center" style="padding: 12pt 8pt;">
                    <table cellspacing="0" cellpadding="0">
                    <tr><td align="center" style="font-size: 11pt; color: #2d3748; font-weight: bold;">{date}</td></tr>
                    <tr><td align="center" style="font-size: 6pt; letter-spacing: 2pt; color: #a0aec0; padding-top: 3pt;">DATE</td></tr>
                    </table>
                </td>
                <td width="50%" align="center" style="padding: 12pt 8pt; border-left: 1px solid #edf2f7;">
                    <table cellspacing="0" cellpadding="0">
                    <tr><td align="center" style="font-size: 11pt; color: #2d3748; font-weight: bold;">{credential_id}</td></tr>
                    <tr><td align="center" style="font-size: 6pt; letter-spacing: 2pt; color: #a0aec0; padding-top: 3pt;">CREDENTIAL ID</td></tr>
                    </table>
                </td>
            </tr>
        </table>

        <table width="100%"><tr><td style="font-size: 8pt;">&nbsp;</td></tr></table>
        {signature}
        <table width="100%"><tr><td style="font-size: 8pt;">&nbsp;</td></tr></table>
        {qr}

    </td></tr>
    </table>

    {footer}

</td></tr>
</table>

</td></tr>
</table>

</body>
</html>"""


# -- preview ------------------------------------------------------------------

def sample_variables(org=None, background: str = "") -> dict[str, str]:
    """Stand-in values for previewing a template before anything is issued.

    Built by `build_render_variables` against a stand-in credential, not by a
    dict written out here. That is the whole point: a preview exists to predict
    the render, so a preview assembled by its own code path is a preview that
    can be wrong in exactly the way nobody checks. It already was — this
    function used to omit `font_face` and `display_font`, which the guided
    generator emits into every template it produces, so every guided preview
    silently dropped the display serif and showed a typeface the issued
    certificate would never use. `render_credential_pdf` blanks unresolved
    placeholders, so there was no error anywhere.

    `org` is the real organization when one is in scope, so branding previews as
    it will issue. `background` is the artwork data URI, or "" for none.

    Two deliberate divergences from a real render, both about not producing
    something mistakable for a credential:

      - the recipient is obviously fictional, and
      - the footer says so. It is the one branding field the author does not
        get to see previewed, and that is the trade.
    """
    from datetime import datetime, timezone

    from api.models.credential import Credential
    from api.models.organization import Organization
    from api.services.rendering import build_render_variables

    sample_org = org if org is not None else Organization(name="Sample Organization")
    cred = Credential(
        public_id="CF-2026-SAMPLE1",
        recipient_name="Ada Lovelace",
        title="Analytical Engines",
        issued_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    # background is passed explicitly (never None) so build_render_variables
    # does not try to resolve one off a template row the preview does not have.
    variables = build_render_variables(cred, sample_org, None, background)
    variables["footer_text"] = "Preview — not a real credential"

    # Not builtins: stand-ins for the custom placeholders the shipped guided
    # layouts offer, so an author previewing one sees a filled field rather
    # than the blank an unresolved placeholder renders as.
    variables["usn"] = "1XX00XX000"
    variables["duration"] = "4 weeks"
    return variables
