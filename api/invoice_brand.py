"""Invoice brand colors — independent from certificate / IntelliForge branding."""

from __future__ import annotations

import os

INVOICE_BRAND_DEFAULTS: dict[str, str] = {
    "primary": "#1e293b",
    "accent": "#0284c7",
    "secondary": "#6366f1",
    "amount": "#4338ca",
    "frame": "#e2e8f0",
    "text": "#1a202c",
    "muted": "#64748b",
    "header_text": "#ffffff",
    "header_label": "#cbd5e1",
    "table_header_bg": "#f8fafc",
    "table_border": "#e2e8f0",
    "due_bg": "#f0f9ff",
}

_ENV_KEYS: dict[str, str] = {
    "primary": "INVOICE_COLOR_PRIMARY",
    "accent": "INVOICE_COLOR_ACCENT",
    "secondary": "INVOICE_COLOR_SECONDARY",
    "amount": "INVOICE_COLOR_AMOUNT",
    "frame": "INVOICE_COLOR_FRAME",
    "text": "INVOICE_COLOR_TEXT",
    "muted": "INVOICE_COLOR_MUTED",
    "header_text": "INVOICE_COLOR_HEADER_TEXT",
    "header_label": "INVOICE_COLOR_HEADER_LABEL",
    "table_header_bg": "INVOICE_COLOR_TABLE_HEADER_BG",
    "table_border": "INVOICE_COLOR_TABLE_BORDER",
    "due_bg": "INVOICE_COLOR_DUE_BG",
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
        "color_purple": c["amount"],
        "color_text": c["text"],
        "color_muted": c["muted"],
        "color_header_text": c["header_text"],
        "color_header_label": c["header_label"],
        "color_table_header_bg": c["table_header_bg"],
        "color_table_border": c["table_border"],
        "color_due_bg": c["due_bg"],
    }
