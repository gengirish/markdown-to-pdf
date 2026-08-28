"""Building the variables a credential PDF renders with — the one implementation.

Bulk issuance (worker.py) and single issuance (routes/verify.py's PDF endpoint)
must never again build this dict two different ways. render_credential_pdf does
a dumb {{key}} string replace with whatever keys it is handed; it does not know
which placeholders a template actually contains, so a key missing here is a
placeholder left visible in the output.
"""

from __future__ import annotations

from typing import Any

from api.core.qr import generate_qr_data_uri
from api.models.credential import Credential
from api.models.organization import Organization


def build_render_variables(cred: Credential, org: Organization) -> dict[str, Any]:
    from api.core.config import CERTFORGE_WEB_URL

    verify_url = f"{CERTFORGE_WEB_URL}/verify/{cred.public_id}"

    # The bundled EB Garamond, exposed as placeholders so a template can use the
    # same display face the legacy certificates do. font_face is the @font-face
    # CSS and is injected raw; display_font is the family name to reference, and
    # falls back to a stack when the font could not be registered.
    from api.core.pdf_renderer import display_font_css, display_font_family

    return {
        "font_face": display_font_css(),
        "display_font": display_font_family(),
        "name": cred.recipient_name,
        "title": cred.title,
        "date": cred.issued_at.strftime("%B %d, %Y"),
        "credential_id": cred.public_id,
        "qr": generate_qr_data_uri(verify_url),
        "issuer_name": org.name,
        # Branding keys always resolve to something so a placeholder is never
        # left unreplaced in a rendered PDF.
        "logo_url": org.logo_url or "",
        "primary_color": org.primary_color or "#1e293b",
        "accent_color": org.accent_color or "#d4af37",
        "footer_text": org.footer_text or "Powered by CertForge · certforge.intelliforge.tech",
    }
