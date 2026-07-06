"""Branding assets and HTML helpers for sports appreciation certificates."""

from __future__ import annotations

import html as html_mod
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


def _split_partner_org(partner_org: str) -> tuple[str, str]:
    if "." in partner_org:
        idx = partner_org.index(".")
        return partner_org[:idx], partner_org[idx:]
    return partner_org, ""


def appreciation_header_html(
    *,
    header_bg: str = APPRECIATION_HEADER_BG,
    accent: str = APPRECIATION_ACCENT_COLOR,
    secondary: str = APPRECIATION_SECONDARY_COLOR,
    ai_color: str = APPRECIATION_AI_COLOR,
    org_bold: str = "IntelliForge",
    org_light: str = "AI",
    partner_org: str = "maidaan.academy",
    escape: bool = True,
) -> str:
    """HTML/CSS header bar (xhtml2pdf-safe — no raster images)."""
    esc = html_mod.escape if escape else lambda x: x
    partner_name, partner_tld = _split_partner_org(partner_org)
    label = (
        f"font-size:5.5pt;color:{accent};letter-spacing:1.2pt;"
        f"text-transform:uppercase;font-weight:bold;"
    )
    rule = f"border-top:1px solid {accent};font-size:1pt;line-height:1pt;width:46pt;"
    return (
        f'<table width="100%" cellspacing="0" cellpadding="0" '
        f'style="background-color:{header_bg};">'
        f"<tr>"
        f'<td width="50%" style="padding:7pt 14pt 9pt;vertical-align:bottom;">'
        f'<table cellspacing="0" cellpadding="0"><tr>'
        f'<td style="{label}">Sponsored by</td></tr>'
        f'<tr><td style="{rule}">&nbsp;</td></tr></table>'
        f'<table cellspacing="0" cellpadding="0" style="margin-top:4pt;"><tr>'
        f'<td style="background-color:{ai_color};color:#ffffff;font-weight:bold;'
        f"font-size:9pt;width:15pt;height:15pt;text-align:center;"
        f'vertical-align:middle;">I</td>'
        f'<td style="background-color:{accent};color:#ffffff;font-weight:bold;'
        f"font-size:9pt;width:15pt;height:15pt;text-align:center;"
        f'vertical-align:middle;">F</td>'
        f'<td style="padding-left:6pt;vertical-align:middle;">'
        f'<div style="font-size:10pt;font-weight:bold;color:#ffffff;line-height:1.15;">'
        f"{esc(org_bold)} <span style=\"color:{ai_color};\">{esc(org_light)}</span>"
        f"</div></td></tr></table></td>"
        f'<td width="50%" align="right" style="padding:7pt 14pt 9pt;'
        f'vertical-align:bottom;text-align:right;">'
        f'<table cellspacing="0" cellpadding="0" align="right"><tr>'
        f'<td align="right" style="{label}text-align:right;">Event technology by</td></tr>'
        f'<tr><td align="right" style="{rule}">&nbsp;</td></tr></table>'
        f'<table cellspacing="0" cellpadding="0" align="right" style="margin-top:4pt;"><tr>'
        f'<td style="background-color:{secondary};color:#07070E;font-weight:bold;'
        f"font-size:9pt;width:15pt;height:15pt;text-align:center;"
        f'vertical-align:middle;">M</td>'
        f'<td style="padding-left:6pt;vertical-align:middle;text-align:left;">'
        f'<div style="font-size:10pt;font-weight:bold;color:#ffffff;line-height:1.15;">'
        f'{esc(partner_name)}<span style="color:{secondary};">{esc(partner_tld)}</span>'
        f"</div></td></tr></table></td></tr></table>"
    )


def appreciation_header_html_from_branding(branding: dict) -> str:
    return appreciation_header_html(
        header_bg=branding.get("appreciation_header_bg", APPRECIATION_HEADER_BG),
        accent=branding.get("appreciation_accent", APPRECIATION_ACCENT_COLOR),
        secondary=branding.get("appreciation_secondary_color", APPRECIATION_SECONDARY_COLOR),
        ai_color=branding.get("appreciation_ai_color", APPRECIATION_AI_COLOR),
        org_bold=branding.get("appreciation_org_bold", "IntelliForge"),
        org_light=branding.get("appreciation_org_light", "AI"),
        partner_org=branding.get("appreciation_partner_org", "maidaan.academy"),
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
