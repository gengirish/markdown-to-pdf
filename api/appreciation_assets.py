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
    # The 46pt underline lives in its own table: as a second row of the label
    # table it set the shared column width, wrapping "EVENT TECHNOLOGY BY"
    # onto two lines.
    rule = f"border-top:1px solid {accent};font-size:1pt;line-height:1pt;"
    return (
        f'<table width="100%" cellspacing="0" cellpadding="0" '
        f'style="background-color:{header_bg};">'
        f"<tr>"
        f'<td width="50%" style="padding:8pt 16pt 10pt;vertical-align:bottom;">'
        f'<table cellspacing="0" cellpadding="0"><tr>'
        f'<td style="{label}">Sponsored by</td></tr></table>'
        f'<table width="46" cellspacing="0" cellpadding="0"><tr>'
        f'<td style="{rule}">&nbsp;</td></tr></table>'
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
        f'<td align="right" style="{label}text-align:right;">Event technology by</td>'
        f"</tr></table>"
        f'<table width="46" align="right" cellspacing="0" cellpadding="0"><tr>'
        f'<td style="{rule}">&nbsp;</td></tr></table>'
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


def appreciation_header_stripe_html(
    *,
    accent: str = APPRECIATION_ACCENT_COLOR,
) -> str:
    """Bold tricolor energy bar below the sponsor header."""
    cells = []
    for color in APPRECIATION_TRICOLOR:
        cells.append(
            f'<td style="background-color:{color};height:5pt;font-size:1pt;line-height:5pt;">&nbsp;</td>'
        )
    return (
        '<table width="100%" cellspacing="0" cellpadding="0"><tr>'
        + "".join(cells)
        + "</tr></table>"
    )


def appreciation_sport_seal_html(
    *,
    accent: str = APPRECIATION_ACCENT_COLOR,
    secondary: str = APPRECIATION_SECONDARY_COLOR,
    sidebar_color: str = APPRECIATION_SIDEBAR_COLOR,
    size_pt: float = 30,
) -> str:
    """Medal-style seal (xhtml2pdf-safe table layout)."""
    inner = max(size_pt - 8, 18)
    return (
        f'<table cellspacing="0" cellpadding="0" align="center">'
        f'<tr><td align="center" style="text-align:center;width:{size_pt}pt;height:{size_pt}pt;'
        f"background-color:{sidebar_color};border:2pt solid {secondary};"
        f'font-size:{inner * 0.45}pt;color:{secondary};font-weight:bold;'
        f'vertical-align:middle;">&#9733;</td></tr>'
        f'<tr><td align="center" style="text-align:center;font-size:5pt;color:{accent};'
        f'letter-spacing:0.8pt;text-transform:uppercase;padding-top:3pt;font-weight:bold;">'
        f"Sports</td></tr></table>"
    )


def appreciation_host_strip_html(
    host_name: str,
    organizer: str = "",
    *,
    sidebar_color: str = APPRECIATION_SIDEBAR_COLOR,
    accent: str = APPRECIATION_ACCENT_COLOR,
    secondary: str = APPRECIATION_SECONDARY_COLOR,
    escape: bool = True,
) -> str:
    """Stadium-style venue banner — dark band, high-contrast athletic typography."""
    esc = html_mod.escape if escape else lambda x: x
    host = (host_name or APPRECIATION_HOST_NAME_DEFAULT).strip()
    org = (organizer or "").strip()
    tricolor = "".join(
        f'<td style="background-color:{c};width:33%;height:4pt;font-size:1pt;line-height:4pt;">&nbsp;</td>'
        for c in APPRECIATION_TRICOLOR
    )
    org_row = ""
    if org:
        org_row = (
            f'<table align="center" cellspacing="0" cellpadding="0" style="margin-top:7pt;">'
            f'<tr><td align="center" style="background-color:{accent};color:#ffffff;'
            f"font-size:6pt;font-weight:bold;letter-spacing:1pt;padding:3pt 16pt;"
            f'text-transform:uppercase;">Organized by: {esc(org)}</td></tr></table>'
        )
    return (
        f'<table width="100%" cellspacing="0" cellpadding="0" '
        f'style="background-color:{sidebar_color};">'
        f'<tr><td colspan="3" style="padding:0;">'
        f'<table width="100%" cellspacing="0" cellpadding="0"><tr>{tricolor}</tr></table>'
        f"</td></tr>"
        f'<tr><td width="15%" align="center" style="text-align:center;vertical-align:middle;">'
        f'<span style="color:{secondary};font-size:9pt;font-weight:bold;">&#9654;</span></td>'
        f'<td align="center" style="text-align:center;padding:11pt 12pt 10pt;vertical-align:middle;">'
        f'<div style="font-size:6pt;color:{secondary};letter-spacing:1.2pt;text-transform:uppercase;'
        f'font-weight:bold;">Venue &amp; Host Community</div>'
        f'<div style="font-size:13pt;font-weight:bold;color:#ffffff;letter-spacing:1.6pt;'
        f'margin-top:4pt;text-transform:uppercase;">{esc(host)}</div>'
        f'<table align="center" cellspacing="0" cellpadding="0" style="margin-top:6pt;"><tr>'
        f'<td style="background-color:{secondary};width:20pt;height:2pt;font-size:1pt;">&nbsp;</td>'
        f'<td style="width:6pt;">&nbsp;</td>'
        f'<td style="background-color:{accent};width:20pt;height:2pt;font-size:1pt;">&nbsp;</td>'
        f'<td style="width:6pt;">&nbsp;</td>'
        f'<td style="background-color:{APPRECIATION_GREEN_ACCENT};width:20pt;height:2pt;font-size:1pt;">&nbsp;</td>'
        f"</tr></table>"
        f"{org_row}"
        f"</td>"
        f'<td width="15%" align="center" style="text-align:center;vertical-align:middle;">'
        f'<span style="color:{secondary};font-size:9pt;font-weight:bold;">&#9664;</span></td>'
        f"</tr></table>"
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
    secondary: str = APPRECIATION_SECONDARY_COLOR,
    sidebar_color: str = APPRECIATION_SIDEBAR_COLOR,
    show_host: bool = False,
    escape: bool = True,
) -> str:
    """Event metadata — race-bib style card."""
    esc = html_mod.escape if escape else lambda x: x
    if not event_name and not (show_host and host_name):
        return "&nbsp;"
    parts = []
    if event_name:
        parts.append(
            f'<table cellspacing="0" cellpadding="0" align="right" '
            f'style="border:1.5pt solid {accent};border-top:3pt solid {secondary};'
            f'background-color:#fffbf5;padding:7pt 10pt;">'
            f'<tr><td style="font-size:6pt;color:{accent};text-transform:uppercase;'
            f'letter-spacing:1pt;font-weight:bold;padding-bottom:2pt;">&#9654; Event</td></tr>'
            f'<tr><td style="font-size:10pt;font-weight:bold;color:#1a202c;'
            f'letter-spacing:0.6pt;text-transform:uppercase;">{esc(event_name)}</td></tr>'
            f"</table>"
        )
    if show_host and host_name:
        parts.append(
            f'<div style="font-size:7.5pt;font-weight:bold;color:{sidebar_color};'
            f'letter-spacing:0.8pt;margin-top:4pt;text-transform:uppercase;">{esc(host_name)}</div>'
        )
    return "".join(parts)


def appreciation_pdf_accent_rail(
    *,
    accent: str = APPRECIATION_ACCENT_COLOR,
    secondary: str = APPRECIATION_SECONDARY_COLOR,
) -> str:
    """Vertical track-lane accent with athletic stripe segments."""
    segments = (
        (accent, 22),
        ("#E2E8F0", 4),
        (secondary, 18),
        ("#E2E8F0", 4),
        (APPRECIATION_GREEN_ACCENT, 22),
        ("#E2E8F0", 4),
        (accent, 14),
    )
    rows = []
    for color, height in segments:
        rows.append(
            f'<tr><td style="background-color:{color};width:5pt;height:{height}pt;'
            f'font-size:1pt;line-height:1pt;">&nbsp;</td></tr>'
        )
    return f"<table cellspacing='0' cellpadding='0'>{''.join(rows)}</table>"


def appreciation_pdf_sidebar_stripes(
    *,
    accent: str = APPRECIATION_ACCENT_COLOR,
    secondary: str = APPRECIATION_SECONDARY_COLOR,
) -> str:
    """Athletic stripe band for sidebar top."""
    pattern = (accent, secondary, APPRECIATION_GREEN_ACCENT, "#0D3320") * 2
    rows = []
    for color in pattern:
        rows.append(
            f'<tr><td style="background-color:{color};height:2pt;font-size:1pt;">&nbsp;</td></tr>'
        )
    return f"<table width='100%' cellspacing='0' cellpadding='0'>{''.join(rows)}</table>"


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
