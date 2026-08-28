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
    """Generate template HTML from guided settings."""
    cfg = normalise_config(config)

    logo = (
        '<tr><td align="center" style="padding-bottom:18px;">'
        '<img src="{{logo_url}}" style="height:56px;"/></td></tr>'
        if cfg["show_logo"]
        else ""
    )

    qr = (
        '<tr><td align="center" style="padding-top:26px;">'
        '<img src="{{qr}}" style="width:96px;height:96px;"/>'
        '<div style="font-size:8pt;color:#64748b;padding-top:6px;">'
        "Verify: {{credential_id}}</div></td></tr>"
        if cfg["show_qr"]
        else ""
    )

    footer = (
        '<tr><td align="center" style="padding-top:22px;font-size:8pt;color:#64748b;">'
        "{{footer_text}}</td></tr>"
        if cfg["show_footer"]
        else ""
    )

    signature = ""
    if cfg["signature_name"]:
        signature = (
            '<tr><td align="center" style="padding-top:34px;">'
            '<div style="border-top:1px solid #94a3b8;width:220px;margin:0 auto;"></div>'
            f'<div style="padding-top:6px;font-size:10pt;">{_esc(cfg["signature_name"])}</div>'
            f'<div style="font-size:8pt;color:#64748b;">{_esc(cfg["signature_title"])}</div>'
            "</td></tr>"
        )

    # The internship layout carries the USN/duration line the VTU workflow
    # needs; the others leave it out rather than print an empty row.
    detail = ""
    if cfg["layout"] == "internship":
        detail = (
            '<tr><td align="center" style="padding-top:10px;font-size:10pt;color:#334155;">'
            "USN {{usn}} · {{duration}}</td></tr>"
        )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/></head>
<body style="margin:0;padding:0;font-family:Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0"
       style="border:10px solid {{{{primary_color}}}};padding:44px 40px;">
  {logo}
  <tr><td align="center"
      style="font-size:22pt;letter-spacing:2px;color:{{{{primary_color}}}};">
      {_esc(cfg["heading"])}</td></tr>
  <tr><td align="center" style="padding-top:26px;font-size:11pt;color:#475569;">
      {_esc(cfg["body"])}</td></tr>
  <tr><td align="center" style="padding-top:10px;font-size:26pt;color:#0f172a;">
      {{{{name}}}}</td></tr>
  <tr><td align="center" style="padding-top:14px;font-size:11pt;color:#475569;">
      {_esc(cfg["closing"])}</td></tr>
  <tr><td align="center" style="padding-top:8px;font-size:15pt;color:{{{{accent_color}}}};">
      {{{{title}}}}</td></tr>
  {detail}
  <tr><td align="center" style="padding-top:18px;font-size:10pt;color:#64748b;">
      {{{{date}}}}</td></tr>
  {signature}
  {qr}
  {footer}
</table>
</body></html>"""


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
