"""Branding assets and HTML helpers for sports appreciation certificates."""

from __future__ import annotations

import base64
from pathlib import Path

BRANDING_DIR = Path(__file__).resolve().parent.parent / "public" / "branding"

# Palette sampled from intelliforge-sdg-poster-v8.png
APPRECIATION_HEADER_BG = "#07070E"
APPRECIATION_SIDEBAR_COLOR = "#0A2818"
APPRECIATION_ACCENT_COLOR = "#F05B00"
APPRECIATION_SECONDARY_COLOR = "#FFBA08"
APPRECIATION_AI_COLOR = "#7B6FFF"
APPRECIATION_GREEN_ACCENT = "#138808"
APPRECIATION_TRICOLOR = ("#F05B00", "#FFFFFF", "#138808")


def branding_image_data_uri(filename: str) -> str:
    path = BRANDING_DIR / filename
    if not path.is_file():
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def appreciation_logo_urls(base_url: str) -> dict[str, str]:
    base = base_url.rstrip("/")
    return {
        "logo_left_url": f"{base}/branding/appreciation-header-left.png",
        "logo_right_url": f"{base}/branding/appreciation-header-right.png",
        "logo_if_url": f"{base}/branding/intelliforge-ai-logo.png",
        "logo_maidaan_url": f"{base}/branding/maidaan-academy-logo.png",
    }


def appreciation_pdf_header_block() -> str:
    left = branding_image_data_uri("appreciation-header-left.png")
    right = branding_image_data_uri("appreciation-header-right.png")
    if not left or not right:
        return ""
    return (
        '<table width="100%" cellspacing="0" cellpadding="0"><tr>'
        f'<td align="left" style="text-align:left;vertical-align:middle;">'
        f'<img src="{left}" height="34" alt="IntelliForge AI" /></td>'
        f'<td align="right" style="text-align:right;vertical-align:middle;">'
        f'<img src="{right}" height="34" alt="maidaan.academy" /></td>'
        "</tr></table>"
    )


def appreciation_pdf_sports_icons() -> str:
    rows = []
    for color in (APPRECIATION_ACCENT_COLOR, "#D1D5DB", APPRECIATION_GREEN_ACCENT) * 2:
        rows.append(
            f'<tr><td align="center" style="text-align:center;color:{color};'
            f'font-size:10pt;padding:3pt 0;">&#9679;</td></tr>'
        )
    return f"<table cellspacing='0' cellpadding='0'>{''.join(rows)}</table>"


def appreciation_pdf_tricolor_footer() -> str:
    cells = []
    for color in APPRECIATION_TRICOLOR:
        cells.append(
            f'<td style="background-color:{color};font-size:2pt;height:3pt;line-height:3pt;">&nbsp;</td>'
        )
    return (
        '<table width="100%" cellspacing="0" cellpadding="0"><tr>'
        + "".join(cells)
        + "</tr></table>"
    )
