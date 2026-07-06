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
APPRECIATION_HOST_NAME_DEFAULT = "SOBHA DREAM GARDENS"
APPRECIATION_HOST_ORGANIZER_DEFAULT = "SDG RWA & SDG SPORTS COMMITTEE"


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
        f'<td width="50%" style="padding:8pt 16pt 10pt;vertical-align:bottom;">'
        f'<table cellspacing="0" cellpadding="0"><tr>'
        f'<td style="{label}">Sponsored by</td></tr>'
        f'<tr><td style="{rule}">&nbsp;</td></tr></table>'
        f'<table cellspacing="0" cellpadding="0" style="margin-top:5pt;"><tr>'
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
        f'<td width="50%" align="right" style="padding:8pt 16pt 10pt;'
        f'vertical-align:bottom;text-align:right;">'
        f'<table cellspacing="0" cellpadding="0" align="right"><tr>'
        f'<td align="right" style="{label}text-align:right;">Event technology by</td></tr>'
        f'<tr><td align="right" style="{rule}">&nbsp;</td></tr></table>'
        f'<table cellspacing="0" cellpadding="0" align="right" style="margin-top:5pt;"><tr>'
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


_PLACEHOLDER_VENUES = frozenset({
    "",
    "venue / store",
    "venue/store",
    "venue",
    "store",
    "sports event",
    "select a venue",
})


def resolve_appreciation_host_name(
    venue_name: str = "",
    sponsor_label: str = "",
    default_host: str = APPRECIATION_HOST_NAME_DEFAULT,
) -> str:
    """Pick venue/host line; ignore sponsor_label when it lists tech partners only."""
    venue = (venue_name or "").strip()
    sponsor = (sponsor_label or "").strip()
    if venue.lower() in _PLACEHOLDER_VENUES:
        venue = ""
    if sponsor:
        low = sponsor.lower()
        if "intelliforge" not in low and "maidaan" not in low:
            return sponsor
    if venue:
        return venue
    return default_host


def appreciation_host_strip_html(
    host_name: str,
    organizer: str = "",
    *,
    sidebar_color: str = APPRECIATION_SIDEBAR_COLOR,
    accent: str = APPRECIATION_ACCENT_COLOR,
    secondary: str = APPRECIATION_SECONDARY_COLOR,
    escape: bool = True,
) -> str:
    """Venue/host branding band — single hierarchy, no duplicate labels (xhtml2pdf-safe)."""
    esc = html_mod.escape if escape else lambda x: x
    host = (host_name or APPRECIATION_HOST_NAME_DEFAULT).strip()
    org = (organizer or "").strip()
    tricolor = "".join(
        f'<td style="background-color:{c};width:24pt;height:3pt;font-size:1pt;line-height:3pt;">&nbsp;</td>'
        for c in APPRECIATION_TRICOLOR
    )
    org_row = ""
    if org:
        org_row = (
            f'<table align="center" cellspacing="0" cellpadding="0" style="margin-top:6pt;">'
            f'<tr><td align="center" style="background-color:{sidebar_color};color:#ffffff;'
            f"font-size:6pt;font-weight:bold;letter-spacing:0.9pt;padding:3pt 14pt;"
            f'text-transform:uppercase;">Organized by: {esc(org)}</td></tr></table>'
        )
    return (
        f'<table width="100%" cellspacing="0" cellpadding="0" '
        f'style="background-color:#fafbfc;border-bottom:1px solid #e2e8f0;">'
        f'<tr><td align="center" style="text-align:center;padding:10pt 18pt 9pt;">'
        f'<table align="center" cellspacing="0" cellpadding="0"><tr>{tricolor}</tr></table>'
        f'<div style="font-size:6pt;color:#718096;letter-spacing:1pt;text-transform:uppercase;'
        f'margin-top:7pt;">Venue &amp; Host Community</div>'
        f'<div style="font-size:12pt;font-weight:bold;color:#1a202c;letter-spacing:1.4pt;'
        f'margin-top:3pt;text-transform:uppercase;">{esc(host)}</div>'
        f'<table align="center" cellspacing="0" cellpadding="0" style="margin-top:5pt;"><tr>'
        f'<td style="border-top:2pt solid {secondary};font-size:1pt;line-height:1pt;'
        f'width:36pt;">&nbsp;</td></tr></table>'
        f"{org_row}"
        f"</td></tr></table>"
    )


def appreciation_host_strip_from_branding(
    branding: dict,
    venue_name: str = "",
    sponsor_label: str = "",
) -> str:
    host = resolve_appreciation_host_name(
        venue_name,
        sponsor_label,
        branding.get("appreciation_host_name", APPRECIATION_HOST_NAME_DEFAULT),
    )
    return appreciation_host_strip_html(
        host,
        branding.get("appreciation_host_organizer", APPRECIATION_HOST_ORGANIZER_DEFAULT),
        sidebar_color=branding.get("appreciation_sidebar_color", APPRECIATION_SIDEBAR_COLOR),
        accent=branding.get("appreciation_accent", APPRECIATION_ACCENT_COLOR),
        secondary=branding.get("appreciation_secondary_color", APPRECIATION_SECONDARY_COLOR),
    )


def appreciation_event_footer_html(
    event_name: str,
    host_name: str = "",
    *,
    accent: str = APPRECIATION_ACCENT_COLOR,
    sidebar_color: str = APPRECIATION_SIDEBAR_COLOR,
    show_host: bool = False,
    escape: bool = True,
) -> str:
    """Event metadata block — host lives in the strip; event only by default."""
    esc = html_mod.escape if escape else lambda x: x
    if not event_name and not (show_host and host_name):
        return "&nbsp;"
    parts = []
    if event_name:
        parts.append(
            f'<div style="font-size:6.5pt;color:#718096;text-transform:uppercase;'
            f'letter-spacing:0.9pt;margin-bottom:3pt;text-align:right;">Event</div>'
        )
        parts.append(
            f'<div style="font-size:10pt;font-weight:bold;color:#1a202c;'
            f'letter-spacing:0.5pt;text-transform:uppercase;border-left:2pt solid {accent};'
            f'padding-left:8pt;text-align:left;display:inline-block;">{esc(event_name)}</div>'
        )
    if show_host and host_name:
        parts.append(
            f'<div style="font-size:7.5pt;font-weight:bold;color:{sidebar_color};'
            f'letter-spacing:0.8pt;margin-top:4pt;text-transform:uppercase;">{esc(host_name)}</div>'
        )
    return "".join(parts)


def appreciation_pdf_accent_rail() -> str:
    """Vertical tricolor accent (replaces decorative dot column)."""
    rows = []
    for color in APPRECIATION_TRICOLOR:
        rows.append(
            f'<tr><td style="background-color:{color};width:4pt;height:28pt;'
            f'font-size:1pt;line-height:1pt;">&nbsp;</td></tr>'
        )
    return f"<table cellspacing='0' cellpadding='0'>{''.join(rows)}</table>"


def appreciation_pdf_sports_icons() -> str:
    """Backward-compatible alias for accent rail."""
    return appreciation_pdf_accent_rail()


def appreciation_pdf_tricolor_footer() -> str:
    cells = []
    for color in APPRECIATION_TRICOLOR:
        cells.append(
            f'<td style="background-color:{color};font-size:2pt;height:4pt;line-height:4pt;">&nbsp;</td>'
        )
    return (
        '<table width="100%" cellspacing="0" cellpadding="0"><tr>'
        + "".join(cells)
        + "</tr></table>"
    )
