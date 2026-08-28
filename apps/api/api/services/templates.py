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


def normalise_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Fill in what the caller left out, and drop what we do not know.

    Unknown keys are discarded rather than stored: a config that carries fields
    the generator ignores looks like it is doing something and is not.
    """
    merged = dict(DEFAULT_CONFIG)
    for key, value in (config or {}).items():
        if key in DEFAULT_CONFIG:
            merged[key] = value
    if merged["layout"] not in LAYOUTS:
        merged["layout"] = DEFAULT_CONFIG["layout"]
    return merged


def _esc(value: Any) -> str:
    """Escape config text for the generated markup.

    The author is trusted to the extent that they could write raw HTML anyway —
    but their input here is *data*, and treating it as markup would let a stray
    `<` silently break the layout.
    """
    import html as html_mod

    return html_mod.escape(str(value or ""))


def build_html_from_config(config: dict[str, Any]) -> str:
    """Generate template HTML from guided settings.

    Built in the same design language as the seeded platform templates
    (api/seed.py) — which are themselves the CertForge port of the legacy
    certificate: landscape 842x595pt, dark outer frame, white inner card, a
    header band in the org's primary colour, a gold rule under the recipient
    name, a date/credential-ID panel, and a footer band.

    The first version of this generated a plain portrait table with a coloured
    border. It rendered, it validated, and it looked nothing like any
    certificate this product has ever issued — which is worse than not shipping
    a guided form at all, because the output carries the customer's brand.

    Markup is deliberately nested tables with inline styles. xhtml2pdf supports
    no flex and no grid, and `@page size` is what makes it landscape; a template
    that forgets it renders portrait and the layout collapses.
    """
    cfg = normalise_config(config)

    logo = (
        '<tr><td align="center" style="padding-bottom:10pt;">'
        '<img src="{{logo_url}}" height="34" /></td></tr>'
        if cfg["show_logo"]
        else ""
    )

    signature = ""
    if cfg["signature_name"]:
        signature = (
            '<table width="100%" cellspacing="0" cellpadding="0" style="padding-top:14pt;">'
            '<tr><td align="center">'
            '<table align="center" cellspacing="0" cellpadding="0" width="200">'
            '<tr><td style="border-top:1px solid #a0aec0;font-size:1pt;">&nbsp;</td></tr>'
            f'<tr><td align="center" style="font-size:10pt;color:#2d3748;padding-top:4pt;">{_esc(cfg["signature_name"])}</td></tr>'
            f'<tr><td align="center" style="font-size:7pt;letter-spacing:1pt;color:#a0aec0;">{_esc(cfg["signature_title"])}</td></tr>'
            "</table></td></tr></table>"
        )

    qr = (
        '<table width="100%" cellspacing="0" cellpadding="0" style="padding-top:16pt;">'
        '<tr><td align="center">'
        '<table align="center" cellspacing="0" cellpadding="0"><tr>'
        '<td style="padding-right:12pt;vertical-align:middle;">'
        '<img src="{{qr}}" width="70" height="70" /></td>'
        '<td style="vertical-align:middle;text-align:left;">'
        '<table cellspacing="0" cellpadding="0"><tr><td style="font-size:9pt;font-weight:bold;color:#2d3748;">'
        "Scan to Verify</td></tr></table>"
        '<table cellspacing="0" cellpadding="0"><tr><td style="font-size:7pt;color:#a0aec0;">'
        "This QR code links to the permanent<br/>verification page.</td></tr></table>"
        "</td></tr></table></td></tr></table>"
        if cfg["show_qr"]
        else ""
    )

    footer = (
        '<table width="100%" style="background-color:#f8fafc;border-top:1px solid #edf2f7;">'
        '<tr><td align="center" style="padding:10pt 40pt;font-size:7pt;color:#a0aec0;">'
        "{{footer_text}}</td></tr></table>"
        if cfg["show_footer"]
        else ""
    )

    # The internship layout carries the USN and duration the VTU workflow needs.
    # The others leave the row out rather than print empty labels.
    detail = ""
    if cfg["layout"] == "internship":
        detail = (
            '<table width="100%" cellspacing="0" cellpadding="0">'
            '<tr><td align="center" style="font-size:10pt;color:#4a5568;padding-bottom:12pt;">'
            "USN {{usn}} &nbsp;&middot;&nbsp; {{duration}}</td></tr></table>"
        )

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
@page {{ size: 842pt 595pt; margin: 0; }}
body {{ font-family: Helvetica, Arial, sans-serif; color: #2d3748; margin: 0; padding: 0; }}
table {{ border-collapse: collapse; }}
td {{ padding: 0; }}
</style>
</head>
<body>
<table width="100%" height="100%" style="background-color: #0f172a;">
<tr><td style="padding: 24pt 32pt;">
<table width="100%" style="background-color: #ffffff;">
<tr><td>

    <table width="100%" style="background-color: {{{{primary_color}}}};">
    <tr><td style="padding: 26pt 40pt 22pt;" align="center">
        <table width="100%" cellspacing="0" cellpadding="0">
            {logo}
            <tr><td align="center" style="font-size: 8pt; letter-spacing: 4pt; color: {{{{accent_color}}}}; font-weight: bold; padding-bottom: 4pt;">
                {{{{issuer_name}}}}
            </td></tr>
            <tr><td align="center" style="font-size: 9pt; letter-spacing: 3pt; color: #d4af37; font-weight: bold; padding-top: 8pt;">
                {_esc(cfg["heading"])}
            </td></tr>
        </table>
    </td></tr>
    </table>

    <table width="100%">
    <tr><td style="padding: 26pt 50pt 18pt;" align="center">

        <table width="100%" cellspacing="0" cellpadding="0">
            <tr><td align="center" style="font-size: 8pt; letter-spacing: 3pt; color: #a0aec0; padding-bottom: 6pt;">
                {_esc(cfg["body"])}
            </td></tr>
            <tr><td align="center" style="font-size: 34pt; font-weight: bold; color: #1a202c; padding: 4pt 0 2pt;">
                {{{{name}}}}
            </td></tr>
        </table>

        <table width="60%" align="center"><tr><td style="border-top: 2px solid #d4af37; font-size: 1pt;">&nbsp;</td></tr></table>

        <table width="100%" cellspacing="0" cellpadding="0">
            <tr><td align="center" style="font-size: 9pt; color: #718096; padding-top: 12pt;">
                {_esc(cfg["closing"])}
            </td></tr>
            <tr><td align="center" style="font-size: 16pt; font-weight: bold; color: {{{{primary_color}}}}; padding: 6pt 0 16pt;">
                {{{{title}}}}
            </td></tr>
        </table>

        {detail}

        <table width="85%" align="center" cellspacing="0" cellpadding="0" style="border-top: 1px solid #edf2f7; border-bottom: 1px solid #edf2f7;">
            <tr>
                <td width="50%" align="center" style="padding: 12pt 8pt;">
                    <table cellspacing="0" cellpadding="0">
                    <tr><td align="center" style="font-size: 11pt; color: #2d3748; font-weight: bold;">{{{{date}}}}</td></tr>
                    <tr><td align="center" style="font-size: 6pt; letter-spacing: 2pt; color: #a0aec0; padding-top: 3pt;">DATE</td></tr>
                    </table>
                </td>
                <td width="50%" align="center" style="padding: 12pt 8pt; border-left: 1px solid #edf2f7;">
                    <table cellspacing="0" cellpadding="0">
                    <tr><td align="center" style="font-size: 11pt; color: #2d3748; font-weight: bold;">{{{{credential_id}}}}</td></tr>
                    <tr><td align="center" style="font-size: 6pt; letter-spacing: 2pt; color: #a0aec0; padding-top: 3pt;">CREDENTIAL ID</td></tr>
                    </table>
                </td>
            </tr>
        </table>

        {signature}
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

def sample_variables() -> dict[str, str]:
    """Stand-in values for previewing a template before anything is issued.

    Obviously fake on purpose. A preview that says "Ada Lovelace" cannot be
    mistaken for a real credential if it is downloaded and forwarded.
    """
    from api.core.qr import generate_qr_data_uri

    return {
        "name": "Ada Lovelace",
        "title": "Analytical Engines",
        "date": "1 January 2026",
        "credential_id": "CF-2026-SAMPLE1",
        "qr": generate_qr_data_uri("https://example.invalid/verify/CF-2026-SAMPLE1"),
        "issuer_name": "Sample Organization",
        "logo_url": "",
        "primary_color": "#1e293b",
        "accent_color": "#d4af37",
        "footer_text": "Preview — not a real credential",
        "usn": "1XX00XX000",
        "duration": "4 weeks",
    }
