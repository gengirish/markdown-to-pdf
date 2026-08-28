"""
PDF rendering module for CertForge.

Uses xhtml2pdf to render HTML templates into PDF bytes.
Supports both legacy certificate payloads and new DB-backed Templates.
"""

import html as html_mod
import logging
import os
import re
from io import BytesIO

from xhtml2pdf import pisa

from api.appreciation_assets import (
    appreciation_header_html_from_branding,
    appreciation_header_stripe_html,
    appreciation_host_strip_from_branding,
    appreciation_pdf_accent_rail,
    appreciation_pdf_sidebar_stripes,
    appreciation_pdf_tricolor_footer,
    appreciation_sport_seal_html,
)
from api.certificate_templates import (
    CERTIFICATE_APPRECIATION_HTML,
    CERTIFICATE_INTERNSHIP_VTU_HTML,
    CERTIFICATE_PARTICIPATION_HTML,
)
from api.core.qr import generate_qr_data_uri
from api.core.legacy_tokens import legacy_cert_id, is_internship_payload, is_appreciation_payload

logger = logging.getLogger(__name__)

#: A {{placeholder}} left over after substitution.
_UNRESOLVED = re.compile(r"\{\{\s*[\w.-]+\s*\}\}")

# ── Font Loading ───────────────────────────────────────────────────────────

_CERT_FONT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts", "EBGaramond-SemiBold.ttf")
_CERT_DISPLAY_FONT_FAMILY = "GaramondPDF"
_CERT_FONT_AVAILABLE = os.path.exists(_CERT_FONT_PATH)

if _CERT_FONT_AVAILABLE:
    try:
        from reportlab.pdfbase import pdfmetrics as _pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont as _RLTTFont

        _pdfmetrics.registerFont(_RLTTFont(_CERT_DISPLAY_FONT_FAMILY, _CERT_FONT_PATH))
    except Exception as e:
        logger.warning(f"Certificate display font registration failed: {e}")
        _CERT_FONT_AVAILABLE = False


def _participation_font_face() -> str:
    if not _CERT_FONT_AVAILABLE:
        return ""
    url = _CERT_FONT_PATH.replace("\\", "/")
    return (
        f"@font-face {{ font-family: {_CERT_DISPLAY_FONT_FAMILY}; font-weight: normal;"
        f' src: url("{url}"); }}'
        f"@font-face {{ font-family: {_CERT_DISPLAY_FONT_FAMILY}; font-weight: bold;"
        f' src: url("{url}"); }}'
    )


#: The only directory a template may pull a file from. Everything else a
#: template needs must arrive as a data: URI.
_ASSET_ROOT = os.path.realpath(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")
)


#: Returned for anything not allowed. Inside the asset root so it can never
#: escape it, and nonexistent so nothing is ever opened.
_BLOCKED = os.path.join(_ASSET_ROOT, "__blocked__")


def _pdf_link_callback(uri: str, rel: str) -> str:
    """Resolve the bundled fonts, and nothing else.

    This used to return any local path that happened to exist. Since orgs can
    upload their own template HTML, that made `<img src="/app/.env">` a file
    read: xhtml2pdf would open the path and embed the bytes in a PDF the
    uploader then downloads. `file://` worked too.

    Now a path resolves only if it sits inside the bundled fonts directory,
    compared after realpath so `fonts/../../.env` cannot climb out.

    Everything else returns _BLOCKED — a path inside that directory which does
    not exist — rather than the original URI. Handing the URI back is not safe:
    xhtml2pdf falls back to fetching http(s) itself, so a template could make
    the server request an internal address and embed the response. A
    nonexistent local path cannot be fetched or read, so the element simply
    does not render.

    NOTE: this is the CertForge renderer only. The legacy surface has its own
    copy at index.py:1352 and is frozen; do not "fix" that one to match.
    """
    if uri.startswith("data:"):
        return uri

    path = uri[7:] if uri.startswith("file://") else uri
    if "://" in path:
        # http(s) and friends: never fetch on a template author's behalf.
        return _BLOCKED

    try:
        resolved = os.path.realpath(path)
        # commonpath raises on Windows when the paths sit on different drives,
        # which is itself a definitive "outside the asset root".
        inside = os.path.commonpath([resolved, _ASSET_ROOT]) == _ASSET_ROOT
    except (OSError, ValueError):
        return _BLOCKED

    return resolved if inside and os.path.isfile(resolved) else _BLOCKED


# ── New Credential Rendering ───────────────────────────────────────────────

def render_credential_pdf(html_source: str, variables: dict) -> bytes:
    """Render a new-style certificate PDF from a Template and variables.

    Replaces {{key}} with HTML-escaped values from variables, plus {{qr}}
    which is inserted as-is (data URI).
    """
    rendered = html_source
    for key, val in variables.items():
        token = f"{{{{{key}}}}}"
        # Do not escape the QR data URI
        if key == "qr":
            rendered = rendered.replace(token, str(val))
        else:
            rendered = rendered.replace(token, html_mod.escape(str(val)))

    # Anything still unreplaced is a placeholder this credential has no value
    # for — a CSV column one row lacks, or a typo. It used to be printed
    # literally, so a certificate went out reading "{{cohort}}". Blank is the
    # only sane rendering of "we do not know this".
    rendered = _UNRESOLVED.sub("", rendered)

    pdf_buffer = BytesIO()
    pisa_status = pisa.CreatePDF(
        src=rendered, dest=pdf_buffer, encoding="UTF-8", link_callback=_pdf_link_callback
    )
    if pisa_status.err:
        logger.error(f"PDF generation failed: {pisa_status.log}")
        raise RuntimeError("Error generating certificate PDF")
    return pdf_buffer.getvalue()


# ── Legacy Renderers (Imported from index.py) ──────────────────────────────
#
# NOTE: The legacy renderers depend on many specific helper functions for
# signatures and appreciation branding. For brevity in the refactor, we
# will keep the old `_build_cert_pdf` in `api.index` for legacy routes, 
# or fully extract all 10+ helper functions. Since Phase 1 focuses on the 
# new multi-tenant paths, we provide this entrypoint and can migrate legacy
# entirely later if needed.
