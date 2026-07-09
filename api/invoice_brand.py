"""Invoice brand colors — matched to participation certificate visual system."""

from __future__ import annotations

import os

# Same palette as participation certificate PDFs / public viewer
INVOICE_BRAND_DEFAULTS: dict[str, str] = {
    "frame": "#0f0f23",
    "primary": "#15155e",
    "accent": "#d4af37",
    "highlight": "#553c9a",
    "secondary": "#a0aec0",
    "text": "#2d3748",
    "muted": "#718096",
    "header_text": "#ffffff",
    "header_label": "#d4af37",
    "table_header_bg": "#f8fafc",
    "table_border": "#edf2f7",
    "due_bg": "#ffffff",
    "party_bg": "#ffffff",
    "footer_bg": "#f8fafc",
}

_ENV_KEYS: dict[str, str] = {
    "frame": "INVOICE_COLOR_FRAME",
    "primary": "INVOICE_COLOR_PRIMARY",
    "accent": "INVOICE_COLOR_ACCENT",
    "highlight": "INVOICE_COLOR_HIGHLIGHT",
    "secondary": "INVOICE_COLOR_SECONDARY",
    "text": "INVOICE_COLOR_TEXT",
    "muted": "INVOICE_COLOR_MUTED",
    "header_text": "INVOICE_COLOR_HEADER_TEXT",
    "header_label": "INVOICE_COLOR_HEADER_LABEL",
    "table_header_bg": "INVOICE_COLOR_TABLE_HEADER_BG",
    "table_border": "INVOICE_COLOR_TABLE_BORDER",
    "due_bg": "INVOICE_COLOR_DUE_BG",
    "party_bg": "INVOICE_COLOR_PARTY_BG",
    "footer_bg": "INVOICE_COLOR_FOOTER_BG",
}


def _sanitize_env(value: str) -> str:
    if not value:
        return ""
    v = value.strip()
    while v.endswith("\\r\\n"):
        v = v[:-4].rstrip()
    return v


def invoice_brand_colors() -> dict[str, str]:
    """Return invoice palette with optional INVOICE_COLOR_* env overrides."""
    colors = dict(INVOICE_BRAND_DEFAULTS)
    for key, env_name in _ENV_KEYS.items():
        override = _sanitize_env(os.environ.get(env_name, ""))
        if override:
            colors[key] = override
    return colors


def invoice_pdf_color_tokens() -> dict[str, str]:
    """Map brand colors to template placeholder names for xhtml2pdf HTML."""
    c = invoice_brand_colors()
    return {
        "color_frame": c["frame"],
        "color_header_bg": c["primary"],
        "color_gold": c["accent"],
        "color_indigo": c["secondary"],
        "color_purple": c["highlight"],
        "color_text": c["text"],
        "color_muted": c["muted"],
        "color_header_text": c["header_text"],
        "color_header_label": c["header_label"],
        "color_table_header_bg": c["table_header_bg"],
        "color_table_border": c["table_border"],
        "color_due_bg": c["due_bg"],
        "color_party_bg": c["party_bg"],
        "color_footer_bg": c["footer_bg"],
    }
